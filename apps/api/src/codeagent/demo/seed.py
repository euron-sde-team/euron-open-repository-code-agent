"""Demo data: a workspace that looks lived in, built through the real services.

Three sample repositories are uploaded and indexed by the worker, questions are answered
from the index, tasks are run by the agent and reviewed (one fixed, one renamed and
applied, one rejected, one failed), and tests run in the sandbox. Nothing is hand-written
into the tables except the dates of historical activity, spread over the last two weeks so
the dashboard has a shape.
"""

from __future__ import annotations

import asyncio
import io
import time
import uuid
import zipfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from codeagent.core.config import Settings
from codeagent.core.logging import get_logger
from codeagent.db.migrate import migrate
from codeagent.integrations.queue import InlineQueue
from codeagent.models import Patch, Repository, Task, User, Workspace
from codeagent.models.enums import IndexStatus, PatchStatus, Role, RunStatus, TaskStatus
from codeagent.repositories.repos import ReposRepository
from codeagent.repositories.tasks import PatchRepository, TaskRepository
from codeagent.repositories.test_runs import TestRunRepository
from codeagent.repositories.users import UserRepository
from codeagent.repositories.workspaces import WorkspaceRepository
from codeagent.schemas.repositories import RepositorySettings
from codeagent.schemas.workspaces import WorkspaceSettings
from codeagent.services.api_keys import ApiKeyService
from codeagent.services.ask import AskService
from codeagent.services.container import Container, build_container
from codeagent.services.jobs import JobDispatcher
from codeagent.services.principal import Principal
from codeagent.services.repositories import RepositoryService
from codeagent.services.review import ReviewService
from codeagent.services.search import SearchService
from codeagent.services.tasks import TaskService
from codeagent.services.test_runs import TestRunService
from codeagent.services.users import create_user
from codeagent.services.workspaces import WorkspaceService

log = get_logger("codeagent.demo")
WORKSPACE_SLUG = "northwind-engineering"
REPOS_DIR = Path(__file__).parent / "repos"
WAIT_S = 240

PEOPLE = (
    ("priya.raman@example.com", "Priya Raman", Role.OWNER),
    ("marcus.lee@example.com", "Marcus Lee", Role.MAINTAINER),
    ("sofia.alvarez@example.com", "Sofia Alvarez", Role.DEVELOPER),
    ("tom.becker@example.com", "Tom Becker", Role.VIEWER),
)

QUESTIONS = (
    ("ledgerkit", "Where is the tax for an invoice calculated?"),
    ("ledgerkit", "What does apply_discount do and which tests cover it?"),
    ("ledgerkit", "How are invoices exported to CSV?"),
    ("ratelimit", "How does the limiter decide whether a request is allowed?"),
    ("checkout-web", "Where is the cart total computed?"),
)

SEARCHES = (
    ("symbols", "discount"),
    ("symbols", "Invoice"),
    ("text", "Decimal"),
    ("text", "TODO"),
    ("semantic", "round money to cents"),
    ("semantic", "limit requests per client"),
    ("symbols", "cart"),
)


@dataclass(slots=True)
class DemoSummary:
    created: bool
    workspace: str = WORKSPACE_SLUG
    password: str = ""
    people: list[tuple[str, str, str]] = field(default_factory=list)
    api_key: str = ""


def _zip_repository(name: str) -> bytes:
    root = REPOS_DIR / name
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                archive.write(path, f"{name}/{path.relative_to(root).as_posix()}")
    return buffer.getvalue()


async def _wait(check: Callable[[], Awaitable[bool]], what: str) -> None:
    deadline = time.monotonic() + WAIT_S
    while not await check():
        if time.monotonic() > deadline:
            raise TimeoutError(f"timed out waiting for {what}; is the worker running?")
        await asyncio.sleep(0.5)


class Seeder:
    def __init__(self, container: Container, password: str) -> None:
        self.c = container
        self.password = password
        self.workspace: Workspace
        self.users: dict[Role, User] = {}
        self.repos: dict[str, Repository] = {}

    def principal(self, role: Role) -> Principal:
        return Principal(user=self.users[role])

    async def _poll(self, what: str, probe: Callable[[AsyncSession], Awaitable[bool]]) -> None:
        async def check() -> bool:
            async with self.c.db.session() as session:
                return await probe(session)

        await _wait(check, what)

    async def people(self) -> None:
        async with self.c.db.session() as session:
            users = UserRepository(session)
            for email, name, role in PEOPLE:
                user = await users.by_email(email) or await create_user(
                    session,
                    email=email,
                    name=name,
                    password=self.password,
                    is_admin=role == Role.OWNER,
                )
                self.users[role] = user
            owner = self.principal(Role.OWNER)
            service = WorkspaceService(self.c, session)
            self.workspace = await service.create(
                owner,
                "Northwind Engineering",
                "Billing, rate limiting and checkout services for the Northwind storefront.",
            )
            await service.update(
                self.workspace,
                owner,
                name=None,
                description=None,
                settings=WorkspaceSettings(require_independent_review=True),
            )
            for role in (Role.MAINTAINER, Role.DEVELOPER, Role.VIEWER):
                await service.add_member(self.workspace, owner, self.users[role].email, None, role)

    async def repositories(self) -> None:
        maintainer = self.principal(Role.MAINTAINER)
        descriptions = {
            "ledgerkit": "Exact money arithmetic for invoices: tax, discounts and export.",
            "ratelimit": "A token-bucket rate limiter with pluggable stores.",
            "checkout-web": "The storefront cart and pricing logic, in TypeScript.",
        }
        for name in ("ledgerkit", "ratelimit", "checkout-web"):
            async with self.c.db.session() as session:
                repository = await RepositoryService(self.c, session).connect_archive(
                    self.workspace,
                    maintainer,
                    filename=f"{name}.zip",
                    data=_zip_repository(name),
                    name=name,
                    description=descriptions[name],
                )
                self.repos[name] = repository

        async def all_indexed(session: AsyncSession) -> bool:
            rows = [
                await ReposRepository(session).get(self.workspace.id, r.id)
                for r in self.repos.values()
            ]
            if any(r is not None and r.status == IndexStatus.FAILED for r in rows):
                raise RuntimeError("a demo repository failed to index")
            return all(r is not None and r.status == IndexStatus.READY for r in rows)

        await self._poll("the demo repositories to be indexed", all_indexed)
        for name in ("ratelimit", "checkout-web"):
            # The sandbox runs Python tests; these two are browsed, searched and asked about.
            async with self.c.db.session() as session:
                service = RepositoryService(self.c, session)
                await service.update(
                    self.workspace,
                    maintainer,
                    await service.get(self.workspace.id, name),
                    name=None,
                    description=None,
                    settings=RepositorySettings(test_command=None),
                )

    async def test_runs(self, count: int = 4) -> None:
        developer = self.principal(Role.DEVELOPER)
        for _ in range(count):
            async with self.c.db.session() as session:
                repository = await RepositoryService(self.c, session).get(
                    self.workspace.id, "ledgerkit"
                )
                run = await TestRunService(self.c, session).start(
                    self.workspace, developer, repository
                )
            await self._poll("a test run", self._run_done(run.id))

    def _run_done(self, run_id: uuid.UUID) -> Callable[[AsyncSession], Awaitable[bool]]:
        async def probe(session: AsyncSession) -> bool:
            run = await TestRunRepository(session).get(self.workspace.id, run_id)
            return run is not None and RunStatus(run.status).finished

        return probe

    async def conversations(self) -> None:
        for index, (repo, question) in enumerate(QUESTIONS):
            role = (Role.DEVELOPER, Role.VIEWER, Role.MAINTAINER)[index % 3]
            principal = self.principal(role)
            async with self.c.db.session() as session:
                service = AskService(self.c, session)
                conversation = await service.create_conversation(
                    self.workspace, principal, None, repo
                )
                async for _event in service.ask(
                    self.workspace, principal, question, conversation=conversation
                ):
                    pass
        # A follow-up that leans on the previous turn.
        principal = self.principal(Role.DEVELOPER)
        async with self.c.db.session() as session:
            service = AskService(self.c, session)
            conversation = await service.create_conversation(
                self.workspace, principal, None, "ledgerkit"
            )
            for question in (
                "What does calc_tax do?",
                "And where is it called from?",
            ):
                async for _event in service.ask(
                    self.workspace, principal, question, conversation=conversation
                ):
                    pass

    async def searches(self) -> None:
        for round_ in range(3):
            for mode, query in SEARCHES:
                principal = self.principal((Role.DEVELOPER, Role.MAINTAINER, Role.VIEWER)[round_])
                async with self.c.db.session() as session:
                    search = SearchService(self.c, session)
                    if mode == "symbols":
                        await search.symbols(
                            self.workspace,
                            principal,
                            query,
                            repository_id=None,
                            kind=None,
                            limit=20,
                        )
                    elif mode == "text":
                        await search.text(
                            self.workspace,
                            principal,
                            query,
                            regex=False,
                            case_sensitive=False,
                            repository_id=None,
                            path=None,
                            language=None,
                            limit=100,
                        )
                    else:
                        await search.semantic(
                            self.workspace, principal, query, repository_id=None, limit=8
                        )

    async def _task(self, role: Role, repo: str, title: str, description: str) -> Task:
        principal = self.principal(role)
        async with self.c.db.session() as session:
            repository = await RepositoryService(self.c, session).get(self.workspace.id, repo)
            task = await TaskService(self.c, session).create(
                self.workspace, principal, repository, title, description
            )

        async def settled(session: AsyncSession) -> bool:
            current = await TaskRepository(session).get(self.workspace.id, task.id)
            return current is not None and current.status not in {
                TaskStatus.QUEUED,
                TaskStatus.RUNNING,
            }

        await self._poll(f"task #{task.number}", settled)
        return task

    async def _latest_patch(self, task: Task) -> Patch:
        async with self.c.db.session() as session:
            patch = await PatchRepository(session).latest(task.id)
            if patch is None:
                raise RuntimeError(f"task #{task.number} produced no patch")
            session.expunge(patch)
            return patch

    async def tasks(self) -> None:
        maintainer = self.principal(Role.MAINTAINER)
        owner = self.principal(Role.OWNER)

        # 1. The failing test: fixed by a verified mutation, waiting for review.
        fix = await self._task(
            Role.DEVELOPER,
            "ledgerkit",
            "Fix the failing pricing test",
            "test_discount_applies_at_threshold fails: an order of exactly 1,000 should get the "
            "discount. Fix the failing test.",
        )
        patch = await self._latest_patch(fix)
        async with self.c.db.session() as session:
            await ReviewService(self.c, session).add_comment(
                self.workspace,
                maintainer,
                patch,
                body="Boundary fix looks right. Can we also cover the 1,000.01 case?",
                path="ledgerkit/pricing.py",
                line=24,
                side="new",
            )

        # 2. A rename, approved by the owner (independent review) and applied to a branch.
        rename = await self._task(
            Role.DEVELOPER,
            "ledgerkit",
            "Rename apply_discount to apply_threshold_discount",
            "rename `apply_discount` to `apply_threshold_discount`, it is easy to confuse with "
            "volume_discount.",
        )
        patch = await self._latest_patch(rename)
        async with self.c.db.session() as session:
            service = ReviewService(self.c, session)
            current = await service.get(self.workspace.id, patch.id)
            await service.approve(self.workspace, owner, current, "Mechanical rename, tests green.")
            await service.apply(self.workspace, owner, current, None)

        async def applied(session: AsyncSession) -> bool:
            found = await PatchRepository(session).get(self.workspace.id, patch.id)
            return found is not None and found.status == PatchStatus.APPLIED

        await self._poll("the rename to be applied", applied)

        # 3. A helper added with tests, rejected with a reason.
        helper = await self._task(
            Role.DEVELOPER,
            "ledgerkit",
            "Add a clamp helper",
            "add `clamp` to ledgerkit/money.py",
        )
        patch = await self._latest_patch(helper)
        async with self.c.db.session() as session:
            service = ReviewService(self.c, session)
            current = await service.get(self.workspace.id, patch.id)
            await service.reject(
                self.workspace,
                maintainer,
                current,
                "Money has no use for clamp; use Money.allocate for splits instead.",
            )

        # 4. A second proposal waiting for review.
        await self._task(
            Role.MAINTAINER,
            "ledgerkit",
            "Add a safe_divide helper",
            "add `safe_divide` to ledgerkit/pricing.py",
        )

        # 5. A request the offline planner cannot do: failed, with guidance.
        await self._task(
            Role.DEVELOPER,
            "checkout-web",
            "Make the cart summary show savings",
            "Show how much the customer saved next to the total in the cart summary.",
        )

    async def back_date(self) -> None:
        """Spread the history over the last two weeks so the charts have a shape."""
        now = datetime.now(UTC)
        async with self.c.db.session() as session:
            for table, column in (("usage_events", "created_at"), ("test_runs", "created_at")):
                rows = (
                    await session.execute(
                        text(f"SELECT id FROM {table} WHERE workspace_id = :w ORDER BY id"),  # noqa: S608
                        {"w": self.workspace.id},
                    )
                ).all()
                for position, (row_id,) in enumerate(rows):
                    # The last few rows stay "today"; older ones fan out backwards.
                    if len(rows) - position <= 3:
                        continue
                    days = 1 + (position * 13) // max(1, len(rows) - 3)
                    stamp = now - timedelta(days=min(days, 13), hours=position % 7)
                    await session.execute(
                        text(f"UPDATE {table} SET {column} = :ts WHERE id = :id"),  # noqa: S608
                        {"ts": stamp, "id": row_id},
                    )
            await session.commit()

    async def key(self) -> str:
        async with self.c.db.session() as session:
            _, plaintext = await ApiKeyService(self.c, session).create(
                self.workspace, self.principal(Role.OWNER), "CI search and ask", "developer", None
            )
        return plaintext


async def run(settings: Settings, *, password: str) -> DemoSummary:
    await migrate(settings)
    container = build_container(settings)
    if isinstance(container.queue, InlineQueue):
        container.queue.bind(JobDispatcher(container).handle)
    try:
        async with container.db.session() as session:
            if await WorkspaceRepository(session).by_slug(WORKSPACE_SLUG):
                return DemoSummary(created=False)
        seeder = Seeder(container, password)
        await seeder.people()
        await seeder.repositories()
        await seeder.test_runs()
        await seeder.conversations()
        await seeder.searches()
        await seeder.tasks()
        await seeder.back_date()
        key = await seeder.key()
        if isinstance(container.queue, InlineQueue):
            await container.queue.drain()
        return DemoSummary(
            created=True,
            password=password,
            people=[(email, role.value, name) for email, name, role in PEOPLE],
            api_key=key,
        )
    finally:
        await container.close()
