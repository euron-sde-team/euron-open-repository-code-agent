"""Code search: symbols, text (literal or regular expression) and semantic."""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field

from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from codeagent.ai.sources import CodeSource
from codeagent.core import metrics
from codeagent.core.errors import UnprocessableError
from codeagent.models import UsageEvent, Workspace
from codeagent.models.enums import UsageKind
from codeagent.repositories.repos import SearchScope
from codeagent.repositories.search import SearchRepository, SymbolHit, like_escape
from codeagent.repositories.usage import UsageRepository
from codeagent.services.container import Container
from codeagent.services.principal import Principal
from codeagent.services.retrieval import RetrievalService

MAX_REGEX = 200
# A group repeated by a quantifier that itself contains a quantifier, `(a+)+` or `(\w*)*`:
# the classic shape of catastrophic backtracking.
_NESTED_QUANTIFIER = re.compile(r"\([^()]*[+*][^()]*\)\s*[+*{]")
_KINDS = frozenset(
    {"class", "function", "method", "constant", "interface", "type", "enum", "struct"}
)


@dataclass(slots=True)
class FileMatches:
    repository: str
    path: str
    language: str
    matches: list[tuple[int, str, list[tuple[int, int]]]] = field(default_factory=list)


def glob_to_like(glob: str) -> str:
    """`src/**/*.py` -> `src/%/%.py` (LIKE); a plain fragment matches anywhere in the path."""
    escaped = like_escape(glob.strip())
    if not any(ch in glob for ch in "*?"):
        return f"%{escaped}%"
    return escaped.replace("**", "%").replace("*", "%").replace("?", "_")


def validate_regex(pattern: str) -> None:
    if len(pattern) > MAX_REGEX:
        raise UnprocessableError(f"Regular expressions are limited to {MAX_REGEX} characters.")
    if _NESTED_QUANTIFIER.search(pattern):
        raise UnprocessableError(
            "Nested quantifiers like (a+)+ are not allowed: they can take exponential time.",
            code="unsafe_regex",
        )
    try:
        re.compile(pattern)
    except re.error as exc:
        raise UnprocessableError(
            f"Invalid regular expression: {exc}.", code="invalid_regex"
        ) from exc


def match_ranges(
    line: str, needle: str, *, regex: bool, case_sensitive: bool
) -> list[tuple[int, int]]:
    if regex:
        try:
            compiled = re.compile(needle, 0 if case_sensitive else re.IGNORECASE)
        except re.error:
            return []
        return [(m.start(), m.end()) for m in compiled.finditer(line) if m.end() > m.start()][:20]
    haystack, target = (line, needle) if case_sensitive else (line.lower(), needle.lower())
    ranges: list[tuple[int, int]] = []
    start = haystack.find(target)
    while start >= 0 and len(ranges) < 20:
        ranges.append((start, start + len(target)))
        start = haystack.find(target, start + max(1, len(target)))
    return ranges


class SearchService:
    def __init__(self, container: Container, session: AsyncSession) -> None:
        self.c = container
        self.session = session
        self.search = SearchRepository(session)
        self.retrieval = RetrievalService(container, session)

    async def _scopes(
        self, workspace: Workspace, repository_id: uuid.UUID | None
    ) -> list[SearchScope]:
        return await self.retrieval.scopes(workspace.id, [repository_id] if repository_id else None)

    async def _record(
        self, workspace: Workspace, principal: Principal, engine: str, took_ms: int
    ) -> None:
        await UsageRepository(self.session).add(
            UsageEvent(
                workspace_id=workspace.id,
                user_id=principal.user_id,
                api_key_id=principal.api_key_id,
                kind=UsageKind.SEARCH,
                engine=engine,
                latency_ms=took_ms,
            )
        )
        await self.session.commit()

    async def symbols(
        self,
        workspace: Workspace,
        principal: Principal,
        query: str,
        *,
        repository_id: uuid.UUID | None,
        kind: str | None,
        limit: int,
    ) -> tuple[list[tuple[SymbolHit, str]], int]:
        started = time.perf_counter()
        if kind and kind not in _KINDS:
            raise UnprocessableError(f"Unknown symbol kind {kind!r}.")
        scopes = await self._scopes(workspace, repository_id)
        by_snapshot = {scope.snapshot_id: scope for scope in scopes}
        hits = await self.search.symbols(list(by_snapshot), query, kind, limit) if scopes else []
        took = int((time.perf_counter() - started) * 1000)
        metrics.SEARCHES.labels("symbols").inc()
        metrics.SEARCH_DURATION.labels("symbols").observe(took / 1000)
        await self._record(workspace, principal, "symbols", took)
        return [(hit, by_snapshot[hit.snapshot_id].slug) for hit in hits], took

    async def text(
        self,
        workspace: Workspace,
        principal: Principal,
        query: str,
        *,
        regex: bool,
        case_sensitive: bool,
        repository_id: uuid.UUID | None,
        path: str | None,
        language: str | None,
        limit: int,
    ) -> tuple[list[FileMatches], int, bool, int]:
        started = time.perf_counter()
        if regex:
            validate_regex(query)
        elif len(query.strip()) < 2:
            raise UnprocessableError("Search for at least two characters.")
        scopes = await self._scopes(workspace, repository_id)
        by_snapshot = {scope.snapshot_id: scope for scope in scopes}
        hits = []
        if scopes:
            try:
                hits = await self.search.text(
                    list(by_snapshot),
                    query,
                    regex=regex,
                    case_sensitive=case_sensitive,
                    language=language,
                    path_like=glob_to_like(path) if path else None,
                    timeout_ms=self.c.settings.search_timeout_ms,
                    max_lines=limit,
                )
            except DBAPIError as exc:
                await self.session.rollback()
                if "canceling statement" in str(exc.orig) or "timeout" in str(exc.orig).lower():
                    raise UnprocessableError(
                        "The search took too long. Narrow it with a path or a more specific "
                        "pattern.",
                        code="search_timeout",
                    ) from exc
                raise UnprocessableError(
                    "The search pattern was rejected.", code="invalid_regex"
                ) from exc
        files: dict[uuid.UUID, FileMatches] = {}
        for hit in hits:
            entry = files.setdefault(
                hit.file_id, FileMatches(by_snapshot[hit.snapshot_id].slug, hit.path, hit.language)
            )
            entry.matches.append(
                (
                    hit.line,
                    hit.text,
                    match_ranges(hit.text, query, regex=regex, case_sensitive=case_sensitive),
                )
            )
        took = int((time.perf_counter() - started) * 1000)
        metrics.SEARCHES.labels("text").inc()
        metrics.SEARCH_DURATION.labels("text").observe(took / 1000)
        await self._record(workspace, principal, "text", took)
        return list(files.values()), len(hits), len(hits) >= limit, took

    async def semantic(
        self,
        workspace: Workspace,
        principal: Principal,
        query: str,
        *,
        repository_id: uuid.UUID | None,
        limit: int,
    ) -> tuple[list[tuple[CodeSource, tuple[float | None, float | None]]], int]:
        started = time.perf_counter()
        scopes = await self._scopes(workspace, repository_id)
        sources, scores = await self.retrieval.chunks(workspace.id, scopes, query, limit=limit)
        took = int((time.perf_counter() - started) * 1000)
        metrics.SEARCHES.labels("semantic").inc()
        await self._record(workspace, principal, "semantic", took)
        return [
            (s, scores.get(s.chunk_id, (None, None)) if s.chunk_id else (None, None))
            for s in sources
        ], took
