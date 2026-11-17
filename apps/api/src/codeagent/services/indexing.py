"""The indexing pipeline: materialize a commit, build the index, swap it in atomically.

    clone, sync or import -> mirror to S3 -> tracked files -> symbols, references, chunks
    -> embeddings -> one transaction (snapshot ready, repository points at it)

Idempotent: a duplicate message for a ready snapshot is a no-op, and a retry clears any
partial rows first. Readers never see a half-built index, because search and answers only
read a repository's current snapshot, which moves in the same transaction that completes
the new one.
"""

from __future__ import annotations

import shutil
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import anyio
import numpy as np

from codeagent.codeintel import languages
from codeagent.codeintel.archive import ArchiveLimits, detect_format, extract
from codeagent.codeintel.builder import IndexBuild, build_index
from codeagent.core import metrics
from codeagent.core.errors import AppError
from codeagent.core.logging import get_logger
from codeagent.integrations import git
from codeagent.integrations.queue import Job, JobType
from codeagent.integrations.storage import mirror_key
from codeagent.models import Repository, Snapshot
from codeagent.models.enums import IndexStatus, RepositorySource
from codeagent.repositories.index import IndexRepository
from codeagent.repositories.repos import ReposRepository, SnapshotRepository
from codeagent.services.container import Container
from codeagent.services.locks import repository_lock
from codeagent.services.worktree import restore_mirror, store_mirror

log = get_logger("codeagent.indexing")
EMBED_BATCH = 128
MAX_ATTEMPTS = 3


class IndexingError(AppError):
    code = "index_failed"


Row = dict[str, Any]


def _replace_tree(tree: Path, incoming: Path) -> None:
    """Make `tree` hold exactly the files in `incoming`, keeping its .git directory."""
    tree.mkdir(exist_ok=True)
    for entry in tree.iterdir():
        if entry.name == ".git":
            continue
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()
    for entry in incoming.iterdir():
        shutil.move(str(entry), tree / entry.name)


class IndexingService:
    def __init__(self, container: Container) -> None:
        self.c = container

    async def process(self, job: Job, *, final_attempt: bool = True) -> bool:
        """Index one snapshot. Returns False when the job should be retried later."""
        async with self.c.db.session() as session:
            snapshot = await SnapshotRepository(session).get_for_update(
                job.workspace_id, job.target_id
            )
            if snapshot is None or snapshot.status == IndexStatus.READY:
                return True  # deleted while queued, or a duplicate delivery
            repository = await ReposRepository(session).get(
                job.workspace_id, snapshot.repository_id
            )
            if repository is None:
                return True
            snapshot.status = IndexStatus.INDEXING
            snapshot.attempts += 1
            snapshot.error = None
            repository.status = (
                IndexStatus.INDEXING
                if repository.current_snapshot_id is None
                else repository.status
            )
            await session.commit()
            session.expunge_all()

        started = time.perf_counter()
        try:
            with anyio.fail_after(self.c.settings.job_timeout_s):
                build, head, mirror = await self._materialize_and_build(repository, snapshot)
                vectors = await self._embed(build)
        except (git.GitError, AppError) as exc:
            detail = exc.detail if isinstance(exc, git.GitError) else ""
            log.info(
                "index_failed",
                snapshot_id=str(snapshot.id),
                reason=exc.message,
                detail=detail[-500:],
            )
            await self._fail(snapshot, exc.message)
            return True
        except TimeoutError:
            await self._fail(snapshot, "Indexing took too long and was stopped.")
            return True
        except Exception:
            log.exception("index_error", snapshot_id=str(snapshot.id))
            if final_attempt:
                await self._fail(snapshot, "Indexing failed unexpectedly. Try syncing again.")
                return True
            await self._requeue(snapshot)
            return False

        async with self.c.db.session() as session:
            index = IndexRepository(session)
            current = await SnapshotRepository(session).get_for_update(
                job.workspace_id, snapshot.id
            )
            if current is None:
                return True
            await index.clear(snapshot.id)
            await index.write(*self._rows(snapshot, build, vectors))
            stats = build.stats()
            current.status = IndexStatus.READY
            current.commit_sha = head.sha
            current.branch = head.branch
            current.stats = stats | {"duration_ms": int((time.perf_counter() - started) * 1000)}
            current.warnings = build.warnings[:200]
            current.indexed_at = datetime.now(UTC)
            await ReposRepository(session).mark(
                snapshot.repository_id,
                status=IndexStatus.READY,
                error=None,
                current_snapshot_id=snapshot.id,
                mirror_key=mirror,
                default_branch=head.branch if head.branch != "HEAD" else repository.default_branch,
                languages=build.languages(),
                file_count=stats["indexed_files"],
                symbol_count=stats["symbols"],
                line_count=stats["lines"],
                size_bytes=stats["bytes"],
                last_indexed_at=current.indexed_at,
            )
            await SnapshotRepository(session).prune(
                snapshot.repository_id, self.c.settings.snapshot_retention, snapshot.id
            )
            await session.commit()

        for file in build.files:
            if file.content is not None:
                metrics.INDEXED_FILES.labels(file.language).inc()
        for symbol in build.symbols:
            metrics.INDEXED_SYMBOLS.labels(symbol.kind).inc()
        log.info(
            "indexed",
            repository=repository.slug,
            snapshot_id=str(snapshot.id),
            commit=head.sha[:12],
            files=stats["indexed_files"],
            symbols=stats["symbols"],
            chunks=stats["chunks"],
            seconds=round(time.perf_counter() - started, 2),
        )
        return True

    async def _materialize_and_build(
        self, repository: Repository, snapshot: Snapshot
    ) -> tuple[IndexBuild, git.Head, str]:
        settings = self.c.settings
        key = mirror_key(repository.workspace_id, repository.id)
        async with repository_lock(self.c.redis, repository.id):
            with git.scratch_dir("index") as scratch:
                root = Path(scratch)
                tree = root / "tree"
                if snapshot.origin == "upload":
                    await self._import_upload(repository, snapshot, root, tree)
                elif repository.source == RepositorySource.GIT and snapshot.origin == "clone":
                    url = git.validate_git_url(repository.git_url or "")
                    await git.ensure_public_host(
                        url, allow_private=settings.allow_private_git_hosts
                    )
                    await git.clone(
                        url, tree, branch=repository.default_branch, depth=settings.git_clone_depth,
                        timeout_s=settings.git_timeout_s,
                    )  # fmt: skip
                else:
                    await restore_mirror(self.c.storage, repository, tree)
                    if repository.source == RepositorySource.GIT:
                        url = git.validate_git_url(repository.git_url or "")
                        await git.ensure_public_host(
                            url, allow_private=settings.allow_private_git_hosts
                        )
                        branch = repository.default_branch or (await git.head(tree)).branch
                        await git.fetch_and_reset(
                            tree,
                            branch=branch,
                            depth=settings.git_clone_depth,
                            timeout_s=settings.git_timeout_s,
                        )
                head = await git.head(tree)
                await store_mirror(self.c.storage, repository, tree, key)
                sources = await anyio.to_thread.run_sync(
                    self._read_sources, tree, await git.tracked_files(tree)
                )
        build = await anyio.to_thread.run_sync(
            lambda: build_index(
                sources,
                max_file_bytes=settings.max_file_bytes,
                chunk_max_lines=settings.chunk_max_lines,
            )
        )
        if not build.files:
            raise IndexingError("The repository has no files to index.")
        return build, head, key

    async def _import_upload(
        self, repository: Repository, snapshot: Snapshot, root: Path, tree: Path
    ) -> None:
        settings = self.c.settings
        archive = root / "upload"
        await self.c.storage.get_file(snapshot.upload_key or "", archive)
        with archive.open("rb") as handle:
            head = handle.read(512)
        fmt = detect_format(snapshot.upload_name or "upload", head)
        incoming = root / "incoming"
        limits = ArchiveLimits(
            max_entries=settings.max_files * 2,
            max_total_bytes=settings.max_repo_mb * 1024 * 1024,
            max_file_bytes=min(settings.max_repo_mb, 100) * 1024 * 1024,
        )
        await anyio.to_thread.run_sync(extract, archive, incoming, fmt, limits)
        await anyio.Path(archive).unlink()
        if repository.mirror_key:
            # A new version of an archive repository: replace the tree, keep the history.
            await restore_mirror(self.c.storage, repository, tree)
            message = f"Update from {snapshot.upload_name}"
        else:
            message = f"Import {snapshot.upload_name}"
        await anyio.to_thread.run_sync(_replace_tree, tree, incoming)
        await git.commit_tree(tree, message)

    def _read_sources(self, tree: Path, paths: list[str]) -> list[tuple[str, bytes | None, int]]:
        settings = self.c.settings
        sources: list[tuple[str, bytes | None, int]] = []
        for path in paths:
            if languages.is_vendored(path):
                continue
            target = tree / path
            if target.is_symlink() or not target.is_file():
                continue
            size = target.stat().st_size
            # Over-limit files are listed (with their size) but their bytes are not read.
            data = target.read_bytes() if size <= settings.max_file_bytes else None
            sources.append((path, data, size))
            if len(sources) >= settings.max_files:
                break
        return sources

    async def _embed(self, build: IndexBuild) -> np.ndarray:
        texts = [chunk.embed_text for chunk in build.chunks]
        if not texts:
            return np.zeros((0, self.c.embedder.dim), dtype=np.float32)
        parts = [
            await self.c.embedder.embed_documents(texts[i : i + EMBED_BATCH])
            for i in range(0, len(texts), EMBED_BATCH)
        ]
        return np.concatenate(parts)

    @staticmethod
    def _rows(
        snapshot: Snapshot, build: IndexBuild, vectors: np.ndarray
    ) -> tuple[list[Row], list[Row], list[Row], list[Row]]:
        ws, sid = snapshot.workspace_id, snapshot.id
        files: list[Row] = [
            {
                "id": f.id,
                "workspace_id": ws,
                "snapshot_id": sid,
                "path": f.path,
                "language": f.language,
                "size_bytes": f.size_bytes,
                "line_count": f.line_count,
                "sha256": f.sha256,
                "is_test": f.is_test,
                "symbol_count": f.symbol_count,
                "content": f.content,
                "parse_error": f.parse_error,
            }
            for f in build.files
        ]
        symbols: list[Row] = [
            {
                "id": s.id,
                "workspace_id": ws,
                "snapshot_id": sid,
                "file_id": s.file_id,
                "parent_id": s.parent_id,
                "name": s.name,
                "qualified_name": s.qualified_name,
                "kind": s.kind,
                "start_line": s.start_line,
                "end_line": s.end_line,
                "signature": s.signature,
                "doc": s.doc,
                "exported": s.exported,
                "ref_count": s.ref_count,
            }
            for s in build.symbols
        ]
        refs: list[Row] = [
            {
                "id": r.id,
                "workspace_id": ws,
                "snapshot_id": sid,
                "file_id": r.file_id,
                "source_symbol_id": r.source_symbol_id,
                "target_symbol_id": r.target_symbol_id,
                "target_name": r.target_name,
                "qualifier": r.qualifier,
                "kind": r.kind,
                "line": r.line,
            }
            for r in build.refs
        ]
        chunks: list[Row] = [
            {
                "id": ch.id,
                "workspace_id": ws,
                "snapshot_id": sid,
                "file_id": ch.file_id,
                "symbol_id": ch.symbol_id,
                "start_line": ch.start_line,
                "end_line": ch.end_line,
                "content": ch.content,
                "terms": ch.terms,
                "token_count": ch.token_count,
                "embedding": vectors[i],
            }
            for i, ch in enumerate(build.chunks)
        ]
        return files, symbols, refs, chunks

    async def _fail(self, snapshot: Snapshot, message: str) -> None:
        metrics.JOBS.labels(JobType.INDEX_SNAPSHOT.value, "failed").inc()
        async with self.c.db.session() as session:
            await SnapshotRepository(session).mark(
                snapshot.id, status=IndexStatus.FAILED, error=message
            )
            repository = await ReposRepository(session).get(
                snapshot.workspace_id, snapshot.repository_id
            )
            if repository is not None and repository.current_snapshot_id is None:
                repository.status = IndexStatus.FAILED
                repository.error = message
            await session.commit()

    async def _requeue(self, snapshot: Snapshot) -> None:
        async with self.c.db.session() as session:
            await SnapshotRepository(session).mark(snapshot.id, status=IndexStatus.QUEUED)
            await session.commit()

    async def reap_stale(self) -> int:
        """Re-send snapshots stuck queued or indexing (a lost message or a crashed worker)."""
        cutoff = datetime.now(UTC) - timedelta(minutes=self.c.settings.stale_job_minutes)
        resend: list[Job] = []
        async with self.c.db.session() as session:
            stale = await SnapshotRepository(session).unfinished_before(cutoff)
            for snapshot in stale:
                if snapshot.attempts >= MAX_ATTEMPTS:
                    snapshot.status = IndexStatus.FAILED
                    snapshot.error = "Indexing did not finish after several attempts."
                else:
                    snapshot.status = IndexStatus.QUEUED
                    snapshot.updated_at = datetime.now(UTC)
                    resend.append(Job(JobType.INDEX_SNAPSHOT, snapshot.workspace_id, snapshot.id))
            await session.commit()
        for job in resend:
            await self.c.queue.enqueue(job)
        return len(stale)
