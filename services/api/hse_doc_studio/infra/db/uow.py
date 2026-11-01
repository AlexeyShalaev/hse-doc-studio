"""Реализация IUnitOfWork поверх ambient-транзакции."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager

from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.infra.db.session import SessionProvider


class SqlUnitOfWork(IUnitOfWork):
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    def begin(self) -> AbstractAsyncContextManager[None]:
        return self._sessions.begin()
