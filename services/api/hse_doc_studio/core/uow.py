"""Порт границы транзакции для записи в несколько таблиц и то, что код без доступа к БД знает о ней.

Открытую транзакцию (ambient, `infra/db/session.py`) держит contextvar этого модуля. Отсюда use_cases, не
импортируя infra, откладывают побочный эффект до коммита (`after_commit`) и отпускают фоновую задачу, которая не
унаследует чужую транзакцию (`spawn_detached`).
"""

from __future__ import annotations

import asyncio
import contextvars
from collections.abc import Callable, Coroutine
from contextlib import AbstractAsyncContextManager
from contextvars import ContextVar, Token
from typing import Any, Protocol

import structlog

logger = structlog.get_logger(__name__)


class IUnitOfWork(Protocol):
    """Только открывает и закрывает границу транзакции, репозитории не создаёт и не прячет.

    Вложенный ``begin()`` присоединяется к внешней транзакции. Коммит происходит выходом из внешнего
    блока, исключение откатывает всё. Побочные эффекты вне БД (файлы, S3, письма) делают после блока
    или откладывают через `after_commit`.
    """

    def begin(self) -> AbstractAsyncContextManager[None]: ...


class TransactionScope:
    """Открытая транзакция глазами кода без БД: жива ли она и что сделать после её коммита.

    Закрытая (коммит или откат) помечается `closed`: задача, унаследовавшая контекст, её уже не видит.
    """

    def __init__(self) -> None:
        self.closed = False
        self._after_commit: list[Callable[[], object]] = []

    def defer(self, action: Callable[[], object]) -> None:
        self._after_commit.append(action)

    def committed(self) -> None:
        """Коммит прошёл: отложенные действия по порядку. Сбой одного не мешает остальным и не отменяет коммит."""
        actions, self._after_commit = self._after_commit, []
        for action in actions:
            try:
                action()
            except Exception:
                logger.exception("after_commit_action_failed")


_current: ContextVar[TransactionScope | None] = ContextVar("hse_db_ambient_transaction", default=None)


def current_transaction() -> TransactionScope | None:
    """Открытая транзакция текущего контекста; закрытая не считается."""
    scope = _current.get()
    return scope if scope is not None and not scope.closed else None


def enter_transaction(scope: TransactionScope) -> Token[TransactionScope | None]:
    """Сделать транзакцию текущей (реализация `IUnitOfWork`); вернуть прежнюю через `leave_transaction`."""
    return _current.set(scope)


def leave_transaction(token: Token[TransactionScope | None]) -> None:
    _current.reset(token)


def after_commit(action: Callable[[], object]) -> None:
    """Выполнить `action` после коммита открытой транзакции; при откате не выполнять вовсе.

    Без открытой транзакции выполняется сразу: запись вызывающего уже закоммичена своей короткой транзакцией.
    `action` синхронный; долгую работу он отпускает задачей через `spawn_detached`.
    """
    scope = current_transaction()
    if scope is None:
        action()
        return
    scope.defer(action)


def spawn_detached[T](coro: Coroutine[Any, Any, T], *, name: str | None = None) -> asyncio.Task[T]:
    """Фоновая задача, отпущенная из запроса или сценария: без его транзакции, с остальным контекстом.

    `asyncio.create_task` копирует контекст целиком, и задача, начатая внутри транзакции, взяла бы её сессию, пока
    вызывающий ещё работает с ней (asyncpg: «another operation is in progress»). Здесь копия без транзакции:
    задача ходит в БД своими короткими транзакциями. Актор, язык, `request_id` и имя фоновой задачи остаются,
    по ним журнал писем пишет, кто вызвал письмо.
    """
    context = contextvars.copy_context()
    context.run(_current.set, None)
    return asyncio.get_running_loop().create_task(coro, name=name, context=context)
