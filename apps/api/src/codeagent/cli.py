"""Operator command line.

codeagent migrate
codeagent user create --email you@example.com --name "You" --admin
codeagent reindex <workspace> <repository>
codeagent reap
codeagent openapi --out docs/api/openapi.json
codeagent demo seed
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Annotated

import typer

from codeagent.core.config import get_settings
from codeagent.core.logging import configure_logging
from codeagent.services.auth import temporary_password

app = typer.Typer(no_args_is_help=True, help="Euron CodeAgent command line.", add_completion=False)
user_app = typer.Typer(no_args_is_help=True, help="Manage accounts.")
demo_app = typer.Typer(no_args_is_help=True, help="Demo data for local stacks.")
app.add_typer(user_app, name="user")
app.add_typer(demo_app, name="demo")


@app.callback()
def _setup() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, "console")


@app.command()
def migrate() -> None:
    """Apply pending database migrations."""
    from codeagent.db.migrate import migrate as run

    asyncio.run(run(get_settings()))
    typer.echo("migrations applied")


def user_password(password: str | None, *, interactive: bool) -> tuple[str, bool]:
    """The password for a new account, and whether it was generated.

    Given on the command line, asked for at a terminal, or generated when there is no
    terminal (the command also runs as a one-off container task, where nobody can answer a
    prompt). A generated password is printed once and meant to be changed at first sign-in.
    """
    if password:
        return password, False
    if interactive:
        return typer.prompt("Password", hide_input=True, confirmation_prompt=True), False
    return temporary_password(), True


@user_app.command("create")
def create_user(
    email: Annotated[str, typer.Option(help="Sign-in email.")],
    name: Annotated[str, typer.Option(help="Display name.")],
    password: Annotated[
        str | None,
        typer.Option(
            hide_input=True,
            help="Omit it to be asked, or to get a generated one when there is no terminal.",
        ),
    ] = None,
    admin: Annotated[bool, typer.Option(help="Instance administrator.")] = False,
) -> None:
    """Create an account."""
    from codeagent.db.session import Database
    from codeagent.services.users import create_user as create

    secret, generated = user_password(password, interactive=sys.stdin.isatty())

    async def run() -> None:
        db = Database(get_settings())
        try:
            async with db.session() as session:
                user = await create(
                    session, email=email, name=name, password=secret, is_admin=admin
                )
                typer.echo(f"created {user.email} ({user.id})")
        finally:
            await db.dispose()

    asyncio.run(run())
    if generated:
        typer.echo(f"temporary password: {secret}")
        typer.echo("Sign in and change it under Settings, Account.")


@app.command()
def reindex(
    workspace: Annotated[str, typer.Argument(help="Workspace slug.")],
    repository: Annotated[str, typer.Argument(help="Repository id or slug.")],
) -> None:
    """Queue a fresh index of a repository for the running worker to pick up."""

    async def run() -> str:
        from codeagent.core.errors import NotFoundError
        from codeagent.repositories.workspaces import WorkspaceRepository
        from codeagent.services.container import build_container
        from codeagent.services.principal import Principal
        from codeagent.services.repositories import RepositoryService

        container = build_container(get_settings())
        try:
            async with container.db.session() as session:
                found = await WorkspaceRepository(session).by_slug(workspace.lower())
                if found is None:
                    raise NotFoundError("Workspace not found.")
                service = RepositoryService(container, session)
                repo = await service.get(found.id, repository)
                snapshot = await service.sync(found, Principal(), repo)
                return str(snapshot.id)
        finally:
            await container.close()

    typer.echo(f"queued snapshot {asyncio.run(run())}")


@app.command()
def reap() -> None:
    """Resend work stuck in queued or running once (the worker does this on a schedule)."""

    async def run() -> dict[str, int]:
        from codeagent.services.container import build_container
        from codeagent.services.jobs import Maintenance

        container = build_container(get_settings())
        try:
            return await Maintenance(container).run_once()
        finally:
            await container.close()

    typer.echo(json.dumps(asyncio.run(run()), indent=2))


@app.command()
def openapi(
    out: Annotated[Path, typer.Option(help="Where to write the OpenAPI document.")] = Path(
        "openapi.json"
    ),
) -> None:
    """Export the OpenAPI document generated from the routes."""
    from codeagent.main import create_app

    schema = create_app().openapi()
    out.write_text(json.dumps(schema, indent=2, sort_keys=False) + "\n")
    typer.echo(f"wrote {out}")


@demo_app.command("seed")
def demo_seed(
    password: Annotated[
        str | None,
        typer.Option(envvar="DEMO_PASSWORD", help="Password for every demo account."),
    ] = None,
) -> None:
    """Seed a workspace with sample repositories, answers, tasks, patches and test runs."""
    from codeagent.demo.seed import run

    settings = get_settings()
    if settings.is_production:
        raise typer.BadParameter("refusing to seed demo data with APP_ENV=production")
    secret = password or (
        settings.demo_password.get_secret_value() if settings.demo_password else None
    )
    if not secret:
        raise typer.BadParameter("set DEMO_PASSWORD or pass --password")
    summary = asyncio.run(run(settings, password=secret))
    if not summary.created:
        typer.echo("demo data is already present (make down removes it)")
        return
    typer.echo(f"\nSeeded workspace {summary.workspace}. Sign in as:")
    for email, role, name in summary.people:
        typer.echo(f"  {email:<34} {role:<10} {name}")
    typer.echo(f"  password for all: {summary.password}")
    typer.echo(f"\nA developer API key for CI (shown once):\n  {summary.api_key}")


if __name__ == "__main__":
    app()
