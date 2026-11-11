"""Источники в Postgres: партиционированные журналы и таблицы с удалением пачками.

Один принцип: прогон идемпотентен, удаляет только старше границы, работает пачками с паузой и бюджетом времени и
ничего не делает при `cutoff=None` (срок хранения выключен).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any, cast

import structlog
from sqlalchemy import CursorResult, Executable, Result, text
from sqlalchemy.exc import SQLAlchemyError

from hse_doc_studio.core.lifecycle.ports import ExpiredCount, PurgeContext, PurgeResult, SourceSize
from hse_doc_studio.infra.db.session import SessionProvider

logger = structlog.get_logger(__name__)

# Предпросмотр «Освободить место» не должен тормозить базу: запрос счёта дольше этого обрывается, а на экране
# «не удалось посчитать» (storage-cleanup.md, 5.4).
COUNT_TIMEOUT_MS = 3000


def _affected(result: Result[Any]) -> int:
    return int(cast("CursorResult[Any]", result).rowcount)


def count_sql(table: str, condition: str) -> str:
    """Счёт с потолком `:limit`: дальше потолка строки не перебираются. Имена и условия только из констант."""
    return f"SELECT count(*) FROM (SELECT 1 FROM {table} WHERE {condition} LIMIT :limit) AS expired"  # noqa: S608


async def count_capped(
    sessions: SessionProvider, statements: Sequence[Executable], params: Mapping[str, object], cap: int
) -> int | None:
    """Сумма счётов запросов с потолком `cap + 1`, каждый под `statement_timeout`; None, если запрос не прошёл.

    Своя короткая транзакция на запрос: `SET LOCAL` не переживает её, а оборванный таймаутом запрос не портит
    чужую транзакцию.
    """
    total = 0
    for statement in statements:
        try:
            async with sessions.use() as db:
                await db.execute(text(f"SET LOCAL statement_timeout = {COUNT_TIMEOUT_MS}"))
                total += int((await db.execute(statement, {**params, "limit": cap + 1})).scalar_one())
        except SQLAlchemyError:
            logger.warning("lifecycle_count_failed", exc_info=True)
            return None
        if total > cap:
            return cap + 1
    return total


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

    async def count_expired(self, now: datetime, cutoff: datetime | None, cap: int) -> ExpiredCount:
        return ExpiredCount(None)


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
        time_column: str = "at",
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
        self._count = text(count_sql(table, f"{time_column} < :cutoff"))

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

    async def count_expired(self, now: datetime, cutoff: datetime | None, cap: int) -> ExpiredCount:
        if cutoff is None:
            return ExpiredCount(0)
        return ExpiredCount(await count_capped(self._sessions, [self._count], {"cutoff": cutoff}, cap), cutoff)


class DeleteBatchesSource:
    """Таблицы без партиций: DELETE пачками по готовым запросам `:cutoff`, `:n`.

    `counts`: запросы счёта тех же условий (`:cutoff`, `:limit`) для предпросмотра, по одному на запрос удаления.
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
        counts: Sequence[str] = (),
        fixed_age: timedelta | None = None,
    ) -> None:
        self.key = key
        self._sessions = sessions
        self._measure = TableMeasure(sessions, key, tables)
        self._statements = [text(s) for s in statements]
        self._counts = [text(s) for s in counts]
        self._pause_s = pause_s
        self._fixed_age = fixed_age

    def _cutoff(self, now: datetime, cutoff: datetime | None) -> datetime | None:
        return now - self._fixed_age if self._fixed_age is not None else cutoff

    async def measure(self) -> SourceSize:
        return await self._measure.measure()

    async def count_expired(self, now: datetime, cutoff: datetime | None, cap: int) -> ExpiredCount:
        border = self._cutoff(now, cutoff)
        if border is None:
            return ExpiredCount(0)
        if not self._counts:
            return ExpiredCount(None, border)
        return ExpiredCount(await count_capped(self._sessions, self._counts, {"cutoff": border}, cap), border)

    async def purge(self, ctx: PurgeContext) -> PurgeResult:
        cutoff = self._cutoff(ctx.now, ctx.cutoff)
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
