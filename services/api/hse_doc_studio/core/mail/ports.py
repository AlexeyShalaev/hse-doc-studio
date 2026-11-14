"""Порты журнала писем (docs/design/mail-log.md): подписи людей и проектов строк (6.2), актуальность повтора (14.2)."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from typing import Protocol

from hse_doc_studio.core.mail.journal import MailLogEntry, ResendBlock


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


class IMailRelevance(Protocol):
    """Актуальность письма для повтора по его объекту (docs/design/mail-log.md, 14.2, V5): получатель, проект,
    приглашение, запрос, передача, маршрут. Общие правила по самой строке (`resend_block`) сюда не входят."""

    async def check(self, entry: MailLogEntry) -> ResendBlock | None:
        """None, если письмо всё ещё актуально, иначе причина."""
        ...
