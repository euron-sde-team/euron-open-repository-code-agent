"""Sign-in, first-run setup, the current person and who is calling."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from codeagent.api.deps import ContainerDep, PrincipalDep, SessionDep, UserDep, client_ip
from codeagent.core.errors import RateLimitedError
from codeagent.models import User
from codeagent.schemas.auth import (
    LoginRequest,
    MeOut,
    PasswordChange,
    ProfileUpdate,
    SessionOut,
    SignupRequest,
    UserOut,
    WorkspaceSummaryOut,
)
from codeagent.services.auth import SESSION_COOKIE, AuthService
from codeagent.services.container import Container
from codeagent.services.workspaces import WorkspaceService

router = APIRouter(tags=["auth"])


def _set_cookie(response: Response, container: Container, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=container.settings.session_ttl_hours * 3600,
        httponly=True,
        secure=container.settings.cookie_secure,
        samesite="lax",
        domain=container.settings.cookie_domain,
        path="/",
    )


async def _login_rate_limit(request: Request, response: Response, container: ContainerDep) -> None:
    result = await container.limiter.hit(
        f"login:{client_ip(request)}", container.settings.rate_limit_login
    )
    response.headers.update(result.headers())
    if not result.allowed:
        raise RateLimitedError("Too many sign-in attempts. Wait a minute and try again.")


@router.post("/auth/login", summary="Sign in", dependencies=[Depends(_login_rate_limit)])
async def login(
    body: LoginRequest, response: Response, container: ContainerDep, session: SessionDep
) -> SessionOut:
    user, token, claims = await AuthService(container, session).login(body.email, body.password)
    _set_cookie(response, container, token)
    return SessionOut(user=UserOut.model_validate(user), token=token, expires_at=claims.expires_at)


@router.post(
    "/auth/signup",
    summary="Create an account (the first one on a deployment becomes its admin)",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_login_rate_limit)],
)
async def signup(
    body: SignupRequest, response: Response, container: ContainerDep, session: SessionDep
) -> SessionOut:
    auth = AuthService(container, session)
    user = await auth.signup(body.email, body.name, body.password)
    token, claims = auth.issue(user)
    _set_cookie(response, container, token)
    return SessionOut(user=UserOut.model_validate(user), token=token, expires_at=claims.expires_at)


@router.post("/auth/logout", summary="Sign out", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    principal: PrincipalDep, response: Response, container: ContainerDep, session: SessionDep
) -> None:
    if principal.session is not None:
        await AuthService(container, session).logout(principal.session)
    response.delete_cookie(SESSION_COOKIE, path="/", domain=container.settings.cookie_domain)


async def workspace_summaries(
    user: User, container: Container, session: AsyncSession
) -> list[WorkspaceSummaryOut]:
    return [
        WorkspaceSummaryOut(
            id=s.workspace.id,
            slug=s.workspace.slug,
            name=s.workspace.name,
            role=s.role,
            repository_count=s.repository_count,
            member_count=s.member_count,
        )
        for s in await WorkspaceService(container, session).list_for(user)
    ]


@router.get("/auth/me", summary="The signed-in person and their workspaces")
async def me(user: UserDep, container: ContainerDep, session: SessionDep) -> MeOut:
    return MeOut(
        user=UserOut.model_validate(user),
        workspaces=await workspace_summaries(user, container, session),
    )


@router.patch("/auth/me", summary="Update your profile")
async def update_me(
    body: ProfileUpdate, user: UserDep, container: ContainerDep, session: SessionDep
) -> UserOut:
    return UserOut.model_validate(
        await AuthService(container, session).update_profile(user, body.name)
    )


@router.post("/auth/password", summary="Change your password (signs out every other session)")
async def change_password(
    body: PasswordChange,
    user: UserDep,
    response: Response,
    container: ContainerDep,
    session: SessionDep,
) -> SessionOut:
    token, claims = await AuthService(container, session).change_password(
        user, body.current_password, body.new_password
    )
    _set_cookie(response, container, token)
    return SessionOut(user=UserOut.model_validate(user), token=token, expires_at=claims.expires_at)
