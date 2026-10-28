"""Что нужно сценарию, чтобы вести жизненный цикл проекта на общем сервере."""

from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.projects.locator import IProjectLocator
from hse_doc_studio.core.projects.volume import IProjectVolume
from hse_doc_studio.core.uow import IUnitOfWork


@dataclass(frozen=True)
class ServerProjectStorage:
    """Том, каталог и граница транзакции: папку выделяет сервер, а не пользователь.

    Сценарии получают связку только в серверном режиме; в локальном вместо неё прежний реестр папок.
    """

    volume: IProjectVolume
    locator: IProjectLocator
    uow: IUnitOfWork
