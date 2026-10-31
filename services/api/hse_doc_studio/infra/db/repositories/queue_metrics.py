"""Метрики общего пула для автомасштабирования: ждущие и идущие задачи, живые общие раннеры и их слоты."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, func, or_, select

from hse_doc_studio.core.jobs.admin import RUNNER_ONLINE_WITHIN
from hse_doc_studio.core.jobs.autoscale import QueueMetrics
from hse_doc_studio.core.jobs.enums import JobState
from hse_doc_studio.core.jobs.routing import JobRoute, RunnerScope
from hse_doc_studio.infra.db.orm.jobs import JobRow, RunnerRow
from hse_doc_studio.infra.db.session import SessionProvider


class SqlQueueMetricsReader:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def read(self, now: datetime) -> QueueMetrics:
        # Общему пулу нужны задачи общего маршрута и те, чьё окно ожидания личного раннера уже истекло.
        for_shared = or_(
            JobRow.route == JobRoute.shared.value,
            and_(JobRow.route == JobRoute.personal_first.value, JobRow.personal_until <= now),
        )
        queued_stmt = select(func.count(), func.min(JobRow.queued_at)).where(
            JobRow.state == JobState.queued.value, for_shared
        )
        running_stmt = select(func.count()).where(
            JobRow.state == JobState.running.value, JobRow.runner_scope == RunnerScope.shared.value
        )
        runners_stmt = select(func.count(), func.coalesce(func.sum(RunnerRow.concurrency), 0)).where(
            RunnerRow.owner_kind == "instance",
            RunnerRow.revoked_at.is_(None),
            RunnerRow.paused.is_(False),
            RunnerRow.last_seen_at >= now - RUNNER_ONLINE_WITHIN,
            # Раннер, сказавший «ухожу», до следующего опроса в пул не входит.
            or_(RunnerRow.offline_at.is_(None), RunnerRow.offline_at < RunnerRow.last_seen_at),
        )
        async with self._sessions.use() as session:
            queued, oldest = (await session.execute(queued_stmt)).one()
            running = (await session.execute(running_stmt)).scalar_one()
            online, slots = (await session.execute(runners_stmt)).one()
        wait = max(0.0, (now - oldest).total_seconds()) if oldest is not None else 0.0
        return QueueMetrics(int(queued), wait, int(running), int(online), int(slots))
