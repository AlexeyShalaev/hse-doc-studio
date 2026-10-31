"""Уборка учёта: старые периоды счётчиков и журнал вызовов шлюза старше срока хранения."""

from __future__ import annotations

from datetime import timedelta

from hse_doc_studio.core.ai_gateway.usage import IAiUsageLog
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.quotas.kinds import COUNTER_RETENTION_DAYS
from hse_doc_studio.core.quotas.protocols import IUsageCounters


class QuotaHousekeeping:
    def __init__(
        self, counters: IUsageCounters, usage: IAiUsageLog, *, usage_retention_days: int, clock: Clock = utc_now
    ) -> None:
        self._counters = counters
        self._usage = usage
        self._usage_retention = timedelta(days=usage_retention_days)
        self._clock = clock

    async def run(self) -> tuple[int, int]:
        """(стёртых строк счётчиков, стёртых записей журнала)."""
        now = self._clock()
        counters = await self._counters.prune((now - timedelta(days=COUNTER_RETENTION_DAYS)).date())
        calls = await self._usage.prune(now - self._usage_retention)
        return counters, calls
