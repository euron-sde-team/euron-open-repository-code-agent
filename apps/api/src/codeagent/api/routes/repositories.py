"""Connect, index and browse repositories."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, UploadFile, status

from codeagent.api.deps import AccessDep, ContainerDep, SessionDep, UploadLimit
from codeagent.api.presenters import edge_out, repository_detail, repository_out, snapshot_out
from codeagent.core.errors import PayloadTooLargeError, UnprocessableError
from codeagent.models.enums import Role
from codeagent.schemas.repositories import (
    BlobOut,
    FileEntryOut,
    FileListOut,
    OutlineSymbol,
    RepositoryCreate,
    RepositoryDetail,
    RepositoryOut,
    RepositoryPage,
    RepositoryUpdate,
    SnapshotOut,
    SymbolDetail,
)
from codeagent.services.container import Container
from codeagent.services.repositories import RepositoryService

router = APIRouter(tags=["repositories"])
Maintainer = Role.MAINTAINER


async def _read_upload(file: UploadFile, container: Container) -> bytes:
    limit = container.settings.max_archive_bytes
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise PayloadTooLargeError(
            f"Archives are limited to {container.settings.max_archive_mb} MB."
        )
    if not file.filename:
        raise UnprocessableError("The upload needs a file name.")
    return data


@router.get("/workspaces/{workspace}/repositories", summary="Repositories, newest first")
async def list_repositories(
    access: AccessDep,
    container: ContainerDep,
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=100)] = None,
    status_filter: Annotated[str | None, Query(alias="status", max_length=16)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RepositoryPage:
    items, total = await RepositoryService(container, session).page(
        access.workspace.id, query=q, status=status_filter, limit=limit, offset=offset
    )
    return RepositoryPage(
        items=[repository_out(r) for r in items], total=total, limit=limit, offset=offset
    )


@router.post(
    "/workspaces/{workspace}/repositories",
    summary="Connect a repository from an HTTPS git URL",
    status_code=status.HTTP_201_CREATED,
    dependencies=[UploadLimit],
)
async def connect_repository(
    body: RepositoryCreate, access: AccessDep, container: ContainerDep, session: SessionDep
) -> RepositoryOut:
    access.require(Maintainer)
    repository = await RepositoryService(container, session).connect_git(
        access.workspace,
        access.principal,
        git_url=body.git_url,
        branch=body.branch,
        name=body.name,
        description=body.description,
    )
    return repository_out(repository)


@router.post(
    "/workspaces/{workspace}/repositories/upload",
    summary="Connect a repository from a .zip or .tar.gz archive",
    status_code=status.HTTP_201_CREATED,
    dependencies=[UploadLimit],
)
async def upload_repository(
    access: AccessDep,
    container: ContainerDep,
    session: SessionDep,
    file: Annotated[UploadFile, File(description="A .zip, .tar.gz or .tgz archive.")],
    name: Annotated[str | None, Form(max_length=120)] = None,
    description: Annotated[str, Form(max_length=1000)] = "",
) -> RepositoryOut:
    access.require(Maintainer)
    data = await _read_upload(file, container)
    repository = await RepositoryService(container, session).connect_archive(
        access.workspace,
        access.principal,
        filename=file.filename or "archive",
        data=data,
        name=name,
        description=description,
    )
    return repository_out(repository)


@router.get("/workspaces/{workspace}/repositories/{repo}", summary="A repository and its index")
async def get_repository(
    repo: str, access: AccessDep, container: ContainerDep, session: SessionDep
) -> RepositoryDetail:
    service = RepositoryService(container, session)
    repository = await service.get(access.workspace.id, repo)
    history = await service.snapshot_history(repository, limit=1)
    return repository_detail(
        repository,
        await service.current_snapshot(repository),
        history[0] if history else None,
        await service.readme_path(repository),
    )


@router.patch("/workspaces/{workspace}/repositories/{repo}", summary="Rename or change settings")
async def update_repository(
    repo: str,
    body: RepositoryUpdate,
    access: AccessDep,
    container: ContainerDep,
    session: SessionDep,
) -> RepositoryDetail:
    access.require(Maintainer)
    service = RepositoryService(container, session)
    repository = await service.get(access.workspace.id, repo)
    repository = await service.update(
        access.workspace,
        access.principal,
        repository,
        name=body.name,
        description=body.description,
        settings=body.settings,
    )
    history = await service.snapshot_history(repository, limit=1)
    return repository_detail(
        repository,
        await service.current_snapshot(repository),
        history[0] if history else None,
        await service.readme_path(repository),
    )


@router.delete(
    "/workspaces/{workspace}/repositories/{repo}",
    summary="Delete a repository, its index and its stored files",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_repository(
    repo: str, access: AccessDep, container: ContainerDep, session: SessionDep
) -> None:
    access.require(Maintainer)
    service = RepositoryService(container, session)
    repository = await service.get(access.workspace.id, repo)
    await service.delete(access.workspace, access.principal, repository)


@router.post(
    "/workspaces/{workspace}/repositories/{repo}/sync",
    summary="Fetch the latest commit and index it",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[UploadLimit],
)
async def sync_repository(
    repo: str, access: AccessDep, container: ContainerDep, session: SessionDep
) -> SnapshotOut:
    access.require(Maintainer)
    service = RepositoryService(container, session)
    repository = await service.get(access.workspace.id, repo)
    snapshot = await service.sync(access.workspace, access.principal, repository)
    return SnapshotOut.model_validate(snapshot)


@router.post(
    "/workspaces/{workspace}/repositories/{repo}/upload",
    summary="Upload a new version of an archive repository",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[UploadLimit],
)
async def upload_version(
    repo: str,
    access: AccessDep,
    container: ContainerDep,
    session: SessionDep,
    file: Annotated[UploadFile, File(description="A .zip, .tar.gz or .tgz archive.")],
) -> SnapshotOut:
    access.require(Maintainer)
    service = RepositoryService(container, session)
    repository = await service.get(access.workspace.id, repo)
    data = await _read_upload(file, container)
    snapshot = await service.upload_version(
        access.workspace, access.principal, repository, file.filename or "archive", data
    )
    return SnapshotOut.model_validate(snapshot)


@router.get("/workspaces/{workspace}/repositories/{repo}/snapshots", summary="Index history")
async def list_snapshots(
    repo: str, access: AccessDep, container: ContainerDep, session: SessionDep
) -> list[SnapshotOut]:
    service = RepositoryService(container, session)
    repository = await service.get(access.workspace.id, repo)
    return [out for s in await service.snapshot_history(repository) if (out := snapshot_out(s))]


@router.get("/workspaces/{workspace}/repositories/{repo}/files", summary="Every indexed file")
async def list_files(
    repo: str, access: AccessDep, container: ContainerDep, session: SessionDep
) -> FileListOut:
    service = RepositoryService(container, session)
    repository = await service.get(access.workspace.id, repo)
    snapshot_id, entries = await service.files(repository)
    snapshot = await service.current_snapshot(repository)
    return FileListOut(
        snapshot_id=snapshot_id,
        commit_sha=snapshot.commit_sha if snapshot else None,
        files=[
            FileEntryOut(
                path=e.path,
                language=e.language,
                size_bytes=e.size_bytes,
                line_count=e.line_count,
                is_test=e.is_test,
                symbol_count=e.symbol_count,
                indexed=e.indexed,
            )
            for e in entries
        ],
    )


@router.get(
    "/workspaces/{workspace}/repositories/{repo}/blob/{path:path}",
    summary="A file with syntax highlighting and its outline",
)
async def get_blob(
    repo: str, path: str, access: AccessDep, container: ContainerDep, session: SessionDep
) -> BlobOut:
    service = RepositoryService(container, session)
    repository = await service.get(access.workspace.id, repo)
    blob = await service.blob(repository, path)
    file = blob.file
    return BlobOut(
        path=file.path,
        language=file.language,
        size_bytes=file.size_bytes,
        line_count=file.line_count,
        is_test=file.is_test,
        indexed=file.content is not None,
        parse_error=file.parse_error,
        commit_sha=blob.commit_sha,
        lines=blob.lines,
        outline=[
            OutlineSymbol(
                id=symbol.id,
                name=symbol.name,
                qualified_name=symbol.qualified_name,
                kind=symbol.kind,
                start_line=symbol.start_line,
                end_line=symbol.end_line,
                signature=symbol.signature,
                doc=symbol.doc,
                depth=depth,
                ref_count=symbol.ref_count,
            )
            for symbol, depth in blob.outline
        ],
    )


@router.get(
    "/workspaces/{workspace}/symbols/{symbol_id}",
    summary="A symbol with its code, callers, callees and tests",
)
async def get_symbol(
    symbol_id: uuid.UUID, access: AccessDep, container: ContainerDep, session: SessionDep
) -> SymbolDetail:
    detail = await RepositoryService(container, session).symbol_detail(
        access.workspace.id, symbol_id
    )
    symbol = detail.symbol
    return SymbolDetail(
        id=symbol.id,
        name=symbol.name,
        qualified_name=symbol.qualified_name,
        kind=symbol.kind,
        path=symbol.path,
        language=symbol.language,
        start_line=symbol.start_line,
        end_line=symbol.end_line,
        signature=symbol.signature,
        doc=symbol.doc,
        ref_count=symbol.ref_count,
        code=detail.code,
        callers=[edge_out(e) for e in detail.callers],
        callees=[edge_out(e) for e in detail.callees],
        importers=[edge_out(e) for e in detail.importers],
        tests=[edge_out(e) for e in detail.tests],
    )
