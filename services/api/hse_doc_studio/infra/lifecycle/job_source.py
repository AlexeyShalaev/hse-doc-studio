"""Адаптер уборки задач: строки и логи терминальных задач по сроку хранения, выходы без владельца в S3."""

from __future__ import annotations

from datetime import datetime

from hse_doc_studio.core.lifecycle.ports import ExpiredCount, PurgeContext, PurgeResult, SourceSize
from hse_doc_studio.infra.jobs.retention import JobRetention
from hse_doc_studio.infra.lifecycle.sql_sources import TableMeasure


class JobsSource:
    key = "jobs"

    def __init__(self, retention: JobRetention, measure: TableMeasure) -> None:
        self._retention = retention
        self._measure = measure

    async def measure(self) -> SourceSize:
        return await self._measure.measure()

    async def purge(self, ctx: PurgeContext) -> PurgeResult:
        keep = None if ctx.cutoff is None else ctx.now - ctx.cutoff
        report = await self._retention.run(ctx.now, retention=keep)
        return PurgeResult(removed=report.rows + len(report.output_prefixes))

    async def count_expired(self, now: datetime, cutoff: datetime | None, cap: int) -> ExpiredCount:
        """Только строки задач: выходы без владельца в хранилище идут по своему порогу и в счёт не входят."""
        if cutoff is None:
            return ExpiredCount(0)
        return ExpiredCount(await self._retention.count_rows_before(cutoff, cap), cutoff)
