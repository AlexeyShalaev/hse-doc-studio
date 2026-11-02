"""Источники в Postgres: партиционированные журналы и таблицы с удалением пачками.

Один принцип: прогон идемпотентен, удаляет только старше границы, работает пачками с паузой и бюджетом времени и
ничего не делает при `cutoff=None` (срок хранения выключен).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Sequence
from datetime import timedelta
from typing import Any, cast

import structlog
from sqlalchemy import CursorResult, Result, text

from hse_doc_studio.core.lifecycle.ports import PurgeContext, PurgeResult, SourceSize
from hse_doc_studio.infra.db.session import SessionProvider

logger = structlog.get_logger(__name__)


def _affected(result: Result[Any]) -> int:
    return int(cast("CursorResult[Any]", result).rowcount)


_PARTITION_STATS = text(
    "SELECT coalesce(sum(pg_total_relation_size(c.oid)), 0)::bigint, "
    "coalesce(sum(greatest(c.reltuples, 0)), 0)::bigint, count(*)::int "
    "FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid WHERE i.inhparent = to_regclass(:t)"
)
_TABLE_STATS = text(
    "SELECT coalesce(sum(pg_total_relation_size(c.oid)), 0)::bigint, "
    "coalesce(sum(greatest(c.reltuples, 0)), 0)::bigint FROM pg_class c "
    "WHERE c.oid IN (SELECT to_regclass(t)::oid FROM unnest(CAST(:ts AS text[])) AS t)"
)


class TableMeasure:
    """Размер таблиц по каталогу Postgres: источники без своей очистки (их чистит собственная задача)."""

    def __init__(self, sessions: SessionProvider, key: str, tables: Sequence[str]) -> None:
        self.key = key
        self._sessions = sessions
        self._tables = list(tables)

    async def measure(self) -> SourceSize:
        if not self._tables:
            return SourceSize()
        async with self._sessions.use() as db:
            size, rows = (await db.execute(_TABLE_STATS, {"ts": self._tables})).one()
        return SourceSize(bytes=int(size), rows=int(rows))

    async def purge(self, ctx: PurgeContext) -> PurgeResult:
        return PurgeResult()


class PartitionedTableSource:
    """Журнал, разрезанный на месячные партиции: старые партиции отбрасываются целиком, без DELETE.

    Строки старше границы внутри партиций, которые граница пересекает (унаследованная таблица, DEFAULT), стираются
    пачками. Будущие партиции создаются заранее на каждом прогоне.
    """

    def __init__(
        self,
        sessions: SessionProvider,
        key: str,
        table: str,
        *,
        months_ahead: int,
        pause_s: float,
        batch_delete: str,
        batch_returns_count: bool = False,
    ) -> None:
        self.key = key
        self._sessions = sessions
        self._table = table
        self._months_ahead = months_ahead
        self._pause_s = pause_s
        # Для audit_log стирание идёт через функцию SECURITY DEFINER (прямой DELETE запрещён триггером): она
        # возвращает число стёртых строк скаляром, у обычного DELETE оно в rowcount.
        self._batch_sql = text(batch_delete)
        self._scalar = batch_returns_count

    async def measure(self) -> SourceSize:
        async with self._sessions.use() as db:
            size, rows, parts = (await db.execute(_PARTITION_STATS, {"t": self._table})).one()
        return SourceSize(bytes=int(size), rows=int(rows), partitions=int(parts))

    async def ensure_partitions(self) -> int:
        async with self._sessions.use() as db:
            created = (
                await db.execute(
                    text("SELECT lifecycle_ensure_partitions(:t, :n)"), {"t": self._table, "n": self._months_ahead}
                )
            ).scalar_one()
        return int(created)

    async def purge(self, ctx: PurgeContext) -> PurgeResult:
        created = await self.ensure_partitions()
        if created:
            logger.info("partitions created", table=self._table, count=created)
        if ctx.cutoff is None:
            return PurgeResult()
        async with self._sessions.use() as db:
            dropped = (
                await db.execute(
                    text("SELECT lifecycle_drop_partitions_before(:t, :c)"), {"t": self._table, "c": ctx.cutoff}
                )
            ).scalar_one()
        if dropped:
            logger.info("partitions dropped", table=self._table, partitions=list(dropped))
        removed = 0
        more = False
        while True:
            if time.monotonic() >= ctx.deadline:
                more = True
                break
            async with self._sessions.use() as db:
                result = await db.execute(self._batch_sql, {"cutoff": ctx.cutoff, "n": ctx.batch_size})
                count = int(result.scalar_one()) if self._scalar else _affected(result)
            removed += count
            if count < ctx.batch_size:
                break
            await asyncio.sleep(self._pause_s)
        return PurgeResult(removed=removed, partitions_dropped=len(dropped), more=more)


class DeleteBatchesSource:
    """Таблицы без партиций: DELETE пачками по готовым запросам `:cutoff`, `:n`.

    `fixed_age`: срок зашит в код (источник без настройки): граница считается от текущего момента, а не от политики.
    """

    def __init__(
        self,
        sessions: SessionProvider,
        key: str,
        tables: Sequence[str],
        statements: Sequence[str],
        *,
        pause_s: float,
        fixed_age: timedelta | None = None,
    ) -> None:
        self.key = key
        self._sessions = sessions
        self._measure = TableMeasure(sessions, key, tables)
        self._statements = [text(s) for s in statements]
        self._pause_s = pause_s
        self._fixed_age = fixed_age

    async def measure(self) -> SourceSize:
        return await self._measure.measure()

    async def purge(self, ctx: PurgeContext) -> PurgeResult:
        cutoff = ctx.now - self._fixed_age if self._fixed_age is not None else ctx.cutoff
        if cutoff is None:
            return PurgeResult()
        removed = 0
        more = False
        for statement in self._statements:
            while True:
                if time.monotonic() >= ctx.deadline:
                    return PurgeResult(removed=removed, more=True)
                async with self._sessions.use() as db:
                    count = _affected(await db.execute(statement, {"cutoff": cutoff, "n": ctx.batch_size}))
                removed += count
                if count < ctx.batch_size:
                    break
                await asyncio.sleep(self._pause_s)
        return PurgeResult(removed=removed, more=more)
