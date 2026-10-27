"""Сессии и ambient-транзакция.

Репозиторий держит ``SessionProvider`` и на каждый вызов берёт сессию через ``use()``: живая
ambient-транзакция используется как есть, иначе открывается короткая своя. Закрытая транзакция
помечается флагом, поэтому фоновая задача, унаследовавшая контекст, не возьмёт мёртвую сессию.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@dataclass(eq=False)
class AmbientTransaction:
    session: AsyncSession
    closed: bool = False


_ambient: ContextVar[AmbientTransaction | None] = ContextVar("hse_db_ambient_transaction", default=None)


def live_ambient() -> AmbientTransaction | None:
    """Открытая ambient-транзакция текущего контекста; закрытая не считается."""
    tx = _ambient.get()
    return tx if tx is not None and not tx.closed else None


class SessionProvider:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    @asynccontextmanager
    async def begin(self) -> AsyncIterator[None]:
        """Внешняя граница транзакции; вложенный вызов присоединяется к живой внешней."""
        if live_ambient() is not None:
            yield
            return
        async with self._sessionmaker() as session, session.begin():
            tx = AmbientTransaction(session)
            token = _ambient.set(tx)
            try:
                yield
            finally:
                tx.closed = True
                _ambient.reset(token)

    @asynccontextmanager
    async def use(self) -> AsyncIterator[AsyncSession]:
        """Сессия для одного вызова репозитория: ambient, если жива, иначе своя транзакция на вызов."""
        tx = live_ambient()
        if tx is not None:
            yield tx.session
            return
        async with self._sessionmaker.begin() as session:
            yield session
