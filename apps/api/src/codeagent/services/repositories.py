"""Connecting repositories, their snapshots, and reading the index: files, code and symbols."""

from __future__ import annotations

import re
import secrets
import uuid
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlsplit

import orjson
from sqlalchemy.ext.asyncio import AsyncSession

from codeagent.codeintel.archive import detect_format, suffix_for
from codeagent.codeintel.highlight import highlight_lines
from codeagent.core.errors import (
    ConflictError,
    NotFoundError,
    PayloadTooLargeError,
    UnprocessableError,
)
from codeagent.core.ids import uuid7
from codeagent.core.logging import get_logger
from codeagent.integrations import git
from codeagent.integrations.queue import Job, JobType
from codeagent.integrations.storage import repository_prefix, upload_key
from codeagent.models import RepoFile, Repository, Snapshot, Workspace
from codeagent.models.enums import IndexStatus, RepositorySource
from codeagent.repositories.index import EdgeRow, FileEntry, IndexRepository, SymbolRow
from codeagent.repositories.repos import ReposRepository, SnapshotRepository
from codeagent.schemas.repositories import RepositorySettings
from codeagent.services import audit
from codeagent.services.container import Container
from codeagent.services.principal import Principal
from codeagent.services.workspaces import slugify

log = get_logger("codeagent.repositories")
_README = re.compile(r"^readme(\.(md|markdown|rst|txt))?$", re.IGNORECASE)
_ARCHIVE_SUFFIX = re.compile(r"(\.tar\.gz|\.tgz|\.tar|\.zip)$", re.IGNORECASE)
Lines = list[list[tuple[str, str]]]


@dataclass(frozen=True, slots=True)
class Blob:
    file: RepoFile
    lines: Lines
    outline: list[tuple[Any, int]]
    commit_sha: str | None


@dataclass(frozen=True, slots=True)
class SymbolDetail:
    symbol: SymbolRow
    code: Lines
    callers: list[EdgeRow]
    callees: list[EdgeRow]
    importers: list[EdgeRow]
    tests: list[EdgeRow]


def name_from_url(url: str) -> str:
    path = urlsplit(url).path.rstrip("/")
    return path.rsplit("/", 1)[-1].removesuffix(".git") or "repository"


def name_from_archive(filename: str) -> str:
    stem = _ARCHIVE_SUFFIX.sub("", PurePosixPath(filename.replace("\\", "/")).name)
    # GitHub archives are named <repo>-<branch>; keep the repository part.
    stem = re.sub(r"-(main|master|develop|trunk)$", "", stem)
    return stem.strip() or "repository"


class RepositoryService:
    def __init__(self, container: Container, session: AsyncSession) -> None:
        self.c = container
        self.session = session
        self.repos = ReposRepository(session)
        self.snapshots = SnapshotRepository(session)
        self.index = IndexRepository(session)

    async def _unique_slug(self, workspace_id: uuid.UUID, name: str) -> str:
        base = slugify(name)
        slug = base
        while await self.repos.slug_taken(workspace_id, slug):
            slug = f"{base}-{secrets.token_hex(2)}"
        return slug

    async def _create(
        self,
        workspace: Workspace,
        principal: Principal,
        *,
        name: str,
        description: str,
        source: RepositorySource,
        git_url: str | None = None,
        branch: str | None = None,
    ) -> Repository:
        repository = await self.repos.add(
            Repository(
                workspace_id=workspace.id,
                slug=await self._unique_slug(workspace.id, name),
                name=name.strip()[:120],
                description=description.strip(),
                source=source.value,
                git_url=git_url,
                default_branch=branch,
                status=IndexStatus.QUEUED,
                settings=RepositorySettings().model_dump(),
                created_by=principal.user_id,
            )
        )
        await audit.record(
            self.session,
            workspace_id=workspace.id,
            principal=principal,
            action="repository.connected",
            target_type="repository",
            target_id=repository.id,
            details={"name": repository.name, "source": source.value, "git_url": git_url},
        )
        return repository

    async def _queue_snapshot(self, repository: Repository, snapshot: Snapshot) -> None:
        await self.session.commit()
        # After the commit: the worker must be able to read the rows it is told about. If
        # this message is lost, the stale-job reaper re-sends it.
        await self.c.queue.enqueue(
            Job(JobType.INDEX_SNAPSHOT, repository.workspace_id, snapshot.id)
        )

    async def connect_git(
        self,
        workspace: Workspace,
        principal: Principal,
        *,
        git_url: str,
        branch: str | None,
        name: str | None,
        description: str,
    ) -> Repository:
        url = git.validate_git_url(git_url)
        branch = git.validate_branch(branch) if branch else None
        await git.ensure_public_host(url, allow_private=self.c.settings.allow_private_git_hosts)
        repository = await self._create(
            workspace,
            principal,
            name=name or name_from_url(url),
            description=description,
            source=RepositorySource.GIT,
            git_url=url,
            branch=branch,
        )
        snapshot = await self.snapshots.add(
            Snapshot(
                workspace_id=workspace.id,
                repository_id=repository.id,
                status=IndexStatus.QUEUED,
                origin="clone",
                branch=branch,
                created_by=principal.user_id,
            )
        )
        await self._queue_snapshot(repository, snapshot)
        return repository

    async def _store_upload(
        self,
        workspace: Workspace,
        repository: Repository,
        filename: str,
        data: bytes,
        principal: Principal,
    ) -> Snapshot:
        if len(data) > self.c.settings.max_archive_bytes:
            raise PayloadTooLargeError(
                f"Archives are limited to {self.c.settings.max_archive_mb} MB."
            )
        fmt = detect_format(filename, data[:512])
        snapshot_id = uuid7()
        key = upload_key(workspace.id, repository.id, snapshot_id, suffix_for(fmt))
        await self.c.storage.put(key, data, "application/octet-stream")
        return await self.snapshots.add(
            Snapshot(
                id=snapshot_id,
                workspace_id=workspace.id,
                repository_id=repository.id,
                status=IndexStatus.QUEUED,
                origin="upload",
                upload_key=key,
                upload_name=PurePosixPath(filename.replace("\\", "/")).name[:300],
                created_by=principal.user_id,
            )
        )

    async def connect_archive(
        self,
        workspace: Workspace,
        principal: Principal,
        *,
        filename: str,
        data: bytes,
        name: str | None,
        description: str,
    ) -> Repository:
        if not data:
            raise UnprocessableError("The archive is empty.", code="empty_archive")
        detect_format(filename, data[:512])
        repository = await self._create(
            workspace,
            principal,
            name=name or name_from_archive(filename),
            description=description,
            source=RepositorySource.ARCHIVE,
        )
        snapshot = await self._store_upload(workspace, repository, filename, data, principal)
        await self._queue_snapshot(repository, snapshot)
        return repository

    async def _ensure_idle(self, repository: Repository) -> None:
        if await self.snapshots.busy(repository.id):
            raise ConflictError(
                "The repository is already being indexed.", code="index_in_progress"
            )

    async def upload_version(
        self,
        workspace: Workspace,
        principal: Principal,
        repository: Repository,
        filename: str,
        data: bytes,
    ) -> Snapshot:
        if repository.source != RepositorySource.ARCHIVE:
            raise UnprocessableError("Repositories connected by URL are updated with sync.")
        await self._ensure_idle(repository)
        snapshot = await self._store_upload(workspace, repository, filename, data, principal)
        await audit.record(
            self.session,
            workspace_id=workspace.id,
            principal=principal,
            action="repository.uploaded",
            target_type="repository",
            target_id=repository.id,
            details={"filename": snapshot.upload_name},
        )
        await self._queue_snapshot(repository, snapshot)
        return snapshot

    async def sync(
        self, workspace: Workspace, principal: Principal, repository: Repository
    ) -> Snapshot:
        await self._ensure_idle(repository)
        snapshot = await self.snapshots.add(
            Snapshot(
                workspace_id=workspace.id,
                repository_id=repository.id,
                status=IndexStatus.QUEUED,
                origin="sync",
                branch=repository.default_branch,
                created_by=principal.user_id,
            )
        )
        await audit.record(
            self.session,
            workspace_id=workspace.id,
            principal=principal,
            action="repository.synced",
            target_type="repository",
            target_id=repository.id,
        )
        await self._queue_snapshot(repository, snapshot)
        return snapshot

    async def get(self, workspace_id: uuid.UUID, ref: str) -> Repository:
        repository = await self.repos.by_ref(workspace_id, ref)
        if repository is None:
            raise NotFoundError("Repository not found.")
        return repository

    async def page(
        self,
        workspace_id: uuid.UUID,
        *,
        query: str | None,
        status: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Repository], int]:
        return await self.repos.page(
            workspace_id, query=query, status=status, limit=limit, offset=offset
        )

    async def snapshot_history(self, repository: Repository, limit: int = 20) -> list[Snapshot]:
        return await self.snapshots.for_repository(
            repository.workspace_id, repository.id, limit=limit
        )

    async def current_snapshot(self, repository: Repository) -> Snapshot | None:
        if repository.current_snapshot_id is None:
            return None
        return await self.snapshots.get(repository.workspace_id, repository.current_snapshot_id)

    async def update(
        self,
        workspace: Workspace,
        principal: Principal,
        repository: Repository,
        *,
        name: str | None,
        description: str | None,
        settings: RepositorySettings | None,
    ) -> Repository:
        changed: dict[str, object] = {}
        if name is not None and name.strip() != repository.name:
            repository.name = name.strip()
            changed["name"] = repository.name
        if description is not None and description.strip() != repository.description:
            repository.description = description.strip()
            changed["description"] = True
        if settings is not None:
            repository.settings = settings.model_dump()
            changed["settings"] = repository.settings
        if changed:
            await audit.record(
                self.session,
                workspace_id=workspace.id,
                principal=principal,
                action="repository.updated",
                target_type="repository",
                target_id=repository.id,
                details=changed,
            )
            await self.session.commit()
        return repository

    async def delete(
        self, workspace: Workspace, principal: Principal, repository: Repository
    ) -> None:
        prefix = repository_prefix(workspace.id, repository.id)
        await self.session.delete(repository)
        await audit.record(
            self.session,
            workspace_id=workspace.id,
            principal=principal,
            action="repository.deleted",
            target_type="repository",
            target_id=repository.id,
            details={"name": repository.name},
        )
        await self.session.commit()
        try:
            await self.c.storage.delete_prefix(prefix)
        except Exception:
            log.warning("storage_delete_failed", repository_id=str(repository.id))

    def _require_index(self, repository: Repository) -> uuid.UUID:
        if repository.current_snapshot_id is None:
            raise NotFoundError("The repository has no index yet.", code="not_indexed")
        return repository.current_snapshot_id

    async def files(self, repository: Repository) -> tuple[uuid.UUID, list[FileEntry]]:
        snapshot_id = self._require_index(repository)
        key = f"tree:{snapshot_id}"
        try:
            cached = await self.c.redis.get(key)
        except Exception:
            cached = None
        if cached:
            return snapshot_id, [
                FileEntry(uuid.UUID(row[0]), *row[1:]) for row in orjson.loads(cached)
            ]
        entries = await self.index.files(snapshot_id)
        try:
            payload = [
                [
                    str(e.id),
                    e.path,
                    e.language,
                    e.size_bytes,
                    e.line_count,
                    e.is_test,
                    e.symbol_count,
                    e.indexed,
                ]
                for e in entries
            ]
            await self.c.redis.set(
                key, orjson.dumps(payload), ex=self.c.settings.highlight_cache_ttl_s or None
            )
        except Exception:
            log.warning("tree_cache_write_failed")
        return snapshot_id, entries

    async def _highlighted(self, file: RepoFile) -> Lines:
        if file.content is None:
            return []
        key = f"hl:{file.id}"
        try:
            cached = await self.c.redis.get(key)
        except Exception:
            cached = None
        if cached:
            return [[(css, text) for css, text in line] for line in orjson.loads(cached)]
        lines = highlight_lines(file.content, file.language, file.path)
        try:
            await self.c.redis.set(
                key, orjson.dumps(lines), ex=self.c.settings.highlight_cache_ttl_s or None
            )
        except Exception:
            log.warning("highlight_cache_write_failed")
        return lines

    async def blob(self, repository: Repository, path: str) -> Blob:
        snapshot_id = self._require_index(repository)
        file = await self.index.file_by_path(snapshot_id, path.strip("/"))
        if file is None:
            raise NotFoundError("File not found in the indexed snapshot.")
        symbols = await self.index.symbols_in_file(file.id)
        depth: dict[uuid.UUID, int] = {}
        outline = []
        for symbol in symbols:
            level = depth.get(symbol.parent_id, -1) + 1 if symbol.parent_id else 0
            depth[symbol.id] = level
            outline.append((symbol, level))
        snapshot = await self.snapshots.get(repository.workspace_id, snapshot_id)
        return Blob(
            file, await self._highlighted(file), outline, snapshot.commit_sha if snapshot else None
        )

    async def readme_path(self, repository: Repository) -> str | None:
        if repository.current_snapshot_id is None:
            return None
        _, entries = await self.files(repository)
        for entry in entries:
            if "/" not in entry.path and _README.match(entry.path):
                return entry.path
        return None

    async def symbol_detail(self, workspace_id: uuid.UUID, symbol_id: uuid.UUID) -> SymbolDetail:
        symbol = await self.index.symbol(workspace_id, symbol_id)
        if symbol is None:
            raise NotFoundError("Symbol not found.")
        file = await self.index.file(workspace_id, symbol.file_id)
        lines = await self._highlighted(file) if file is not None else []
        incoming = await self.index.incoming(symbol_id)
        callers = [
            edge for edge in incoming if edge.kind in {"call", "inherit"} and not edge.is_test
        ]
        importers = [edge for edge in incoming if edge.kind == "import"]
        tests = [edge for edge in incoming if edge.kind in {"call", "inherit"} and edge.is_test]
        return SymbolDetail(
            symbol=symbol,
            code=lines[symbol.start_line - 1 : symbol.end_line],
            callers=callers,
            callees=await self.index.outgoing(symbol_id),
            importers=importers,
            tests=tests,
        )
