"""Сессии и ambient-транзакция.

Репозиторий держит ``SessionProvider`` и на каждый вызов берёт сессию через ``use()``: живая
ambient-транзакция используется как есть, иначе открывается короткая своя; ``own()`` открывает свою
всегда, мимо ambient. Закрытая транзакция помечается флагом, поэтому фоновая задача, унаследовавшая
контекст, не возьмёт мёртвую сессию. Живую она тоже не должна брать: `AsyncSession` не делится между
задачами, поэтому фоновую работу отпускают через `core.uow.spawn_detached`, а побочные эффекты события
откладывают до коммита через `core.uow.after_commit` (их выполняет выход из ``begin()``).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hse_doc_studio.core.uow import TransactionScope, current_transaction, enter_transaction, leave_transaction


class AmbientTransaction(TransactionScope):
    """Транзакция `begin()` с её сессией; contextvar общий с `core.uow`."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__()
        self.session = session


def live_ambient() -> AmbientTransaction | None:
    """Открытая ambient-транзакция текущего контекста; закрытая не считается."""
    tx = current_transaction()
    return tx if isinstance(tx, AmbientTransaction) else None


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
            token = enter_transaction(tx)
            try:
                yield
            finally:
                tx.closed = True
                leave_transaction(token)
        # Сюда доходит только закоммиченная транзакция: исключение тела или коммита сюда не пускает.
        tx.committed()

    @asynccontextmanager
    async def use(self) -> AsyncIterator[AsyncSession]:
        """Сессия для одного вызова репозитория: ambient, если жива, иначе своя транзакция на вызов."""
        tx = live_ambient()
        if tx is not None:
            yield tx.session
            return
        async with self._sessionmaker.begin() as session:
            yield session

    @asynccontextmanager
    async def own(self) -> AsyncIterator[AsyncSession]:
        """Своя короткая транзакция даже при живой ambient: запись переживает откат вызывающего.

        Для фактов, которые случились независимо от исхода запроса (журнал писем: письмо уже ушло или не ушло).
        Транзакция идёт на отдельном соединении и ambient не видит, поэтому писать так можно только то, что не
        зависит от незакоммиченных строк вызывающего и не ждёт его блокировок.
        """
        async with self._sessionmaker.begin() as session:
            yield session
