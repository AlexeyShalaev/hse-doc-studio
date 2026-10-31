"""Postgres: журнал вызовов ИИ-шлюза и сводка по провайдерам."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import case, delete, func, select

from hse_doc_studio.core.ai_gateway.usage import AiUsageRecord, ProviderUsageSummary
from hse_doc_studio.infra.db.orm.quotas import AiUsageRow
from hse_doc_studio.infra.db.session import SessionProvider


class SqlAiUsageLog:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def record(self, item: AiUsageRecord) -> None:
        row = AiUsageRow(
            id=item.id,
            at=item.at,
            user_id=item.user_id,
            org_id=item.org_id,
            project_id=item.project_id,
            provider_id=item.provider_id,
            provider_owner=item.provider_owner,
            model=item.model,
            operation=item.operation.value,
            input_tokens=item.input_tokens,
            output_tokens=item.output_tokens,
            outcome=item.outcome.value,
            error_code=item.error_code,
            duration_ms=item.duration_ms,
            counted=item.counted,
        )
        async with self._sessions.use() as session:
            session.add(row)
            await session.flush()

    async def summary(self, since: datetime) -> list[ProviderUsageSummary]:
        stmt = (
            select(
                AiUsageRow.provider_id,
                func.count(),
                func.coalesce(func.sum(case((AiUsageRow.outcome == "error", 1), else_=0)), 0),
                func.coalesce(func.sum(case((AiUsageRow.outcome == "denied", 1), else_=0)), 0),
                func.coalesce(func.sum(AiUsageRow.input_tokens), 0),
                func.coalesce(func.sum(AiUsageRow.output_tokens), 0),
            )
            .where(AiUsageRow.at >= since)
            .group_by(AiUsageRow.provider_id)
        )
        async with self._sessions.use() as session:
            rows = (await session.execute(stmt)).all()
        return [ProviderUsageSummary(r[0], int(r[1]), int(r[2]), int(r[3]), int(r[4]), int(r[5])) for r in rows]

    async def prune(self, before: datetime) -> int:
        async with self._sessions.use() as session:
            result = await session.execute(delete(AiUsageRow).where(AiUsageRow.at < before))
            return int(result.rowcount or 0)  # type: ignore[attr-defined]
