"""Порты журнала писем для чтения в админке (docs/design/mail-log.md, 6.2): подписи людей и проектов строк."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class MailPerson:
    """Человек установки в строке журнала: получатель или тот, кто вызвал письмо."""

    id: str
    name: str
    email: str | None


class IMailLogNames(Protocol):
    """Имена для строк журнала одной выборкой на страницу: журнал хранит только id (L9, L11)."""

    async def people(self, user_ids: Collection[str]) -> dict[str, MailPerson]:
        """Люди установки по id; удалённого человека в ответе нет."""
        ...

    async def projects(self, project_ids: Collection[str]) -> dict[str, str]:
        """Названия проектов по id (строка uuid); удалённого насовсем проекта в ответе нет, проект в корзине есть."""
        ...
