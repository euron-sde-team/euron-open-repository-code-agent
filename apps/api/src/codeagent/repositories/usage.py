from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Date, cast, func, select

from codeagent.models import UsageEvent
from codeagent.models.enums import UsageKind
from codeagent.repositories.base import Store


@dataclass(frozen=True, slots=True)
class DailyUsage:
    day: str
    questions: int
    searches: int


class UsageRepository(Store):
    async def add(self, event: UsageEvent) -> None:
        self.session.add(event)
        await self.session.flush()

    async def daily(self, workspace_id: uuid.UUID, since: datetime) -> list[DailyUsage]:
        day = cast(func.date_trunc("day", UsageEvent.created_at), Date)
        rows = await self.session.execute(
            select(
                day.label("day"),
                func.count().filter(UsageEvent.kind == UsageKind.ASK),
                func.count().filter(UsageEvent.kind == UsageKind.SEARCH),
            )
            .where(UsageEvent.workspace_id == workspace_id, UsageEvent.created_at >= since)
            .group_by(day)
            .order_by(day)
        )
        return [DailyUsage(d.isoformat(), int(q), int(s)) for d, q, s in rows.all()]

    async def totals(self, workspace_id: uuid.UUID, since: datetime) -> tuple[int, int, int, int]:
        """(questions, searches, model tokens, median answer latency in ms)."""
        asks = UsageEvent.kind == UsageKind.ASK
        row = (
            await self.session.execute(
                select(
                    func.count().filter(asks),
                    func.count().filter(UsageEvent.kind == UsageKind.SEARCH),
                    func.coalesce(
                        func.sum(UsageEvent.prompt_tokens + UsageEvent.completion_tokens), 0
                    ),
                    func.coalesce(
                        func.percentile_cont(0.5).within_group(UsageEvent.latency_ms).filter(asks),
                        0,
                    ),
                ).where(UsageEvent.workspace_id == workspace_id, UsageEvent.created_at >= since)
            )
        ).one()
        return int(row[0]), int(row[1]), int(row[2]), int(row[3])
