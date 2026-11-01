"""Порт границы транзакции для записи в несколько таблиц."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Protocol


class IUnitOfWork(Protocol):
    """Только открывает и закрывает границу транзакции, репозитории не создаёт и не прячет.

    Вложенный ``begin()`` присоединяется к внешней транзакции. Коммит происходит выходом из внешнего
    блока, исключение откатывает всё. Побочные эффекты вне БД (файлы, S3, письма) делают после блока.
    """

    def begin(self) -> AbstractAsyncContextManager[None]: ...
