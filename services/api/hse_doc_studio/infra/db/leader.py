"""Лидерство через advisory-лок Postgres.

Лок живёт на отдельном соединении: пока оно открыто, второй экземпляр лок не получит. Обрыв
соединения освобождает лок на стороне Postgres, поэтому ``is_held`` проверяет соединение запросом.
"""

from __future__ import annotations

import asyncio
import contextlib

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

BACKGROUND_LEADER_LOCK_KEY = 0x48534D32  # "HSM2"
LEADER_OP_TIMEOUT_S = 5.0  # проверка лока не должна подвисать вместе с отрезанной базой


class PgAdvisoryLeaderLock:
    def __init__(self, engine: AsyncEngine, key: int = BACKGROUND_LEADER_LOCK_KEY) -> None:
        self._engine = engine
        self._key = key
        self._conn: AsyncConnection | None = None

    async def acquire(self) -> bool:
        if self._conn is not None:
            return await self.is_held()
        conn = await asyncio.wait_for(self._engine.connect(), LEADER_OP_TIMEOUT_S)
        try:
            got = (
                await asyncio.wait_for(
                    conn.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": self._key}), LEADER_OP_TIMEOUT_S
                )
            ).scalar_one()
        except BaseException:
            await conn.close()
            raise
        if not got:
            await conn.close()
            return False
        self._conn = conn
        return True

    async def is_held(self) -> bool:
        conn = self._conn
        if conn is None:
            return False
        try:
            await asyncio.wait_for(conn.execute(text("SELECT 1")), LEADER_OP_TIMEOUT_S)
        except Exception:
            self._conn = None
            await _invalidate_quietly(conn)
            return False
        return True

    async def release(self) -> None:
        conn, self._conn = self._conn, None
        if conn is None:
            return
        try:
            await conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": self._key})
        finally:
            await _close_quietly(conn)


async def _close_quietly(conn: AsyncConnection) -> None:
    with contextlib.suppress(Exception):  # соединение уже оборвано, лок снят самим Postgres
        await conn.close()


async def _invalidate_quietly(conn: AsyncConnection) -> None:
    # сессия могла пережить сбой: сбрасываем её, чтобы лок не остался на соединении в пуле
    with contextlib.suppress(Exception):
        await conn.invalidate()
    await _close_quietly(conn)
