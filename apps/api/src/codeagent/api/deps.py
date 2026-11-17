"""Request dependencies: infrastructure, the caller, workspace access and rate limits."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, Path, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from codeagent.core.config import Settings
from codeagent.core.errors import ForbiddenError, RateLimitedError, UnauthorizedError
from codeagent.core.security import API_KEY_PREFIX
from codeagent.models import User, Workspace
from codeagent.models.enums import Role
from codeagent.services.api_keys import ApiKeyService
from codeagent.services.auth import SESSION_COOKIE, AuthService
from codeagent.services.container import Container
from codeagent.services.principal import Principal
from codeagent.services.workspaces import WorkspaceService, require_role

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


ContainerDep = Annotated[Container, Depends(get_container)]


async def get_session(container: ContainerDep) -> AsyncIterator[AsyncSession]:
    async with container.db.session() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _origin_allowed(request: Request, settings: Settings) -> bool:
    """CSRF defence for cookie sessions: unsafe methods must come from our own web app."""
    origin = request.headers.get("origin")
    if origin is None and (referer := request.headers.get("referer")):
        parts = urlsplit(referer)
        origin = f"{parts.scheme}://{parts.netloc}"
    allowed = {*settings.cors_origins, settings.web_url.rstrip("/")}
    return origin in allowed


async def get_principal(
    request: Request, container: ContainerDep, session: SessionDep
) -> Principal:
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        if token.startswith(f"{API_KEY_PREFIX}_"):
            return Principal(api_key=await ApiKeyService(container, session).resolve(token))
        user, claims = await AuthService(container, session).resolve(token)
        return Principal(user=user, session=claims)
    cookie = request.cookies.get(SESSION_COOKIE)
    if cookie:
        user, claims = await AuthService(container, session).resolve(cookie)
        if request.method not in _SAFE_METHODS and not _origin_allowed(request, container.settings):
            raise ForbiddenError("Cross-site request blocked.", code="csrf")
        return Principal(user=user, session=claims, via_cookie=True)
    raise UnauthorizedError()


PrincipalDep = Annotated[Principal, Depends(get_principal)]


def get_user(principal: PrincipalDep) -> User:
    if principal.user is None:
        raise ForbiddenError("This needs a signed-in person, not an API key.")
    return principal.user


UserDep = Annotated[User, Depends(get_user)]


@dataclass(frozen=True, slots=True)
class Access:
    """The caller's standing in one workspace."""

    workspace: Workspace
    role: Role
    principal: Principal

    def require(self, role: Role) -> None:
        require_role(self.role, role)


async def get_access(
    workspace: Annotated[str, Path(description="Workspace id or slug.", max_length=64)],
    principal: PrincipalDep,
    container: ContainerDep,
    session: SessionDep,
) -> Access:
    found, role = await WorkspaceService(container, session).resolve(principal, workspace)
    return Access(found, role, principal)


AccessDep = Annotated[Access, Depends(get_access)]


def rate_limit(bucket: str, setting: str) -> Callable[..., Awaitable[None]]:
    async def dependency(
        response: Response, principal: PrincipalDep, container: ContainerDep
    ) -> None:
        try:
            result = await container.limiter.hit(
                f"{bucket}:{principal.rate_key}", getattr(container.settings, setting)
            )
        except Exception:
            # Valkey down: serve the request rather than fail closed on a rate limit.
            return
        response.headers.update(result.headers())
        if not result.allowed:
            raise RateLimitedError(headers={"retry-after": str(result.reset_s), **result.headers()})

    return dependency


AskLimit = Depends(rate_limit("ask", "rate_limit_ask"))
SearchLimit = Depends(rate_limit("search", "rate_limit_search"))
TaskLimit = Depends(rate_limit("tasks", "rate_limit_tasks"))
RunLimit = Depends(rate_limit("runs", "rate_limit_runs"))
UploadLimit = Depends(rate_limit("upload", "rate_limit_upload"))


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"
