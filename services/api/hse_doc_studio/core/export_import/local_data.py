"""Данные пользователя из каталога локальной Студии (`data_dir`), которые можно перенести на сервер."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from hse_doc_studio.core.entities import AIProvider


class NotTransferred(StrEnum):
    """Что лежит в каталоге, но этим переносом не едет: пользователь заводит это на сервере заново."""

    git_credentials = "git_credentials"
    signing_identities = "signing_identities"
    agent_personas = "agent_personas"


@dataclass(frozen=True)
class LocalUserData:
    settings: dict[str, Any] = field(default_factory=dict)
    ai_providers: tuple[AIProvider, ...] = ()
    not_transferred: tuple[NotTransferred, ...] = ()
    # Записи, которые не удалось прочитать: имя файла или записи, без содержимого.
    unreadable: tuple[str, ...] = ()


class ILocalDataReader(Protocol):
    def read(self, data_dir: Path) -> LocalUserData:
        """Читает каталог локальной Студии, ничего в нём не меняя; нет каталога или файла значит пусто."""
        ...
