"""Symbol, text and semantic search over the current index."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from codeagent.api.deps import AccessDep, ContainerDep, SearchLimit, SessionDep
from codeagent.schemas.search import (
    FileMatchOut,
    LineMatchOut,
    SemanticHitOut,
    SemanticSearchOut,
    SymbolHitOut,
    SymbolSearchOut,
    TextSearchOut,
)
from codeagent.services.repositories import RepositoryService
from codeagent.services.search import SearchService

router = APIRouter(tags=["search"], dependencies=[SearchLimit])
Query1 = Annotated[str, Query(min_length=1, max_length=300, description="What to look for.")]
RepoParam = Annotated[str | None, Query(alias="repository", max_length=64)]


async def _repository_id(
    ref: str | None, access: AccessDep, container: ContainerDep, session: SessionDep
) -> uuid.UUID | None:
    if not ref:
        return None
    return (await RepositoryService(container, session).get(access.workspace.id, ref)).id


@router.get("/workspaces/{workspace}/search/symbols", summary="Find definitions by name")
async def search_symbols(
    q: Query1,
    access: AccessDep,
    container: ContainerDep,
    session: SessionDep,
    repository: RepoParam = None,
    kind: Annotated[str | None, Query(max_length=16)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> SymbolSearchOut:
    repository_id = await _repository_id(repository, access, container, session)
    hits, took = await SearchService(container, session).symbols(
        access.workspace,
        access.principal,
        q,
        repository_id=repository_id,
        kind=kind,
        limit=limit,
    )
    return SymbolSearchOut(
        query=q,
        hits=[
            SymbolHitOut(
                id=hit.id,
                repository=slug,
                name=hit.name,
                qualified_name=hit.qualified_name,
                kind=hit.kind,
                path=hit.path,
                language=hit.language,
                start_line=hit.start_line,
                end_line=hit.end_line,
                signature=hit.signature,
                doc=hit.doc,
                ref_count=hit.ref_count,
                is_test=hit.is_test,
            )
            for hit, slug in hits
        ],
        took_ms=took,
    )


@router.get("/workspaces/{workspace}/search/text", summary="Find lines, literally or by regex")
async def search_text(
    q: Query1,
    access: AccessDep,
    container: ContainerDep,
    session: SessionDep,
    regex: bool = False,
    case_sensitive: bool = False,
    repository: RepoParam = None,
    path: Annotated[
        str | None, Query(max_length=200, description="Path glob, e.g. src/**/*.py")
    ] = None,
    language: Annotated[str | None, Query(max_length=40)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 200,
) -> TextSearchOut:
    repository_id = await _repository_id(repository, access, container, session)
    files, count, truncated, took = await SearchService(container, session).text(
        access.workspace,
        access.principal,
        q,
        regex=regex,
        case_sensitive=case_sensitive,
        repository_id=repository_id,
        path=path,
        language=language,
        limit=limit,
    )
    return TextSearchOut(
        query=q,
        regex=regex,
        files=[
            FileMatchOut(
                repository=f.repository,
                path=f.path,
                language=f.language,
                matches=[
                    LineMatchOut(line=line, text=text, ranges=ranges)
                    for line, text, ranges in f.matches
                ],
            )
            for f in files
        ],
        match_count=count,
        truncated=truncated,
        took_ms=took,
    )


@router.get("/workspaces/{workspace}/search/semantic", summary="Find code by what it does")
async def search_semantic(
    q: Query1,
    access: AccessDep,
    container: ContainerDep,
    session: SessionDep,
    repository: RepoParam = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> SemanticSearchOut:
    repository_id = await _repository_id(repository, access, container, session)
    hits, took = await SearchService(container, session).semantic(
        access.workspace,
        access.principal,
        q,
        repository_id=repository_id,
        limit=limit,
    )
    return SemanticSearchOut(
        query=q,
        hits=[
            SemanticHitOut(
                repository=source.repository,
                path=source.path,
                language=source.language,
                start_line=source.start_line,
                end_line=source.end_line,
                symbol=source.qualified_name or source.symbol_name,
                kind=source.symbol_kind,
                snippet=source.snippet(),
                score=round(source.score, 4),
                vector_score=scores[0],
                keyword_score=scores[1],
            )
            for source, scores in hits
        ],
        took_ms=took,
    )
