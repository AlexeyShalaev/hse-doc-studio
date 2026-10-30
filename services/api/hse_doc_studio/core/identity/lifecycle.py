"""Жизненный цикл данных человека: что мешает удалению, стирание личных данных, выгрузка по запросу."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class DeletionBlockers:
    """Чем человек ещё владеет в одиночку: удалить его, пока это не передано или не стёрто, нельзя."""

    projects: int = 0
    orgs: int = 0

    @property
    def any(self) -> bool:
        return self.projects > 0 or self.orgs > 0


@dataclass(frozen=True)
class ErasureReport:
    audit_anonymized: int
    api_tokens: int
    sessions: int
    settings: int


@dataclass(frozen=True)
class RetentionPolicy:
    """Сроки хранения установки в днях; `audit_days=0` значит «хранить журнал вечно»."""

    audit_days: int
    deleted_projects_days: int
    unused_blobs_days: int


DELETED_PREFIX = "deleted:"


def pseudonym_for(user_id: str) -> str:
    """Стабильная замена id в журнале: события одного удалённого человека остаются связанными, но не называют его."""
    return DELETED_PREFIX + hashlib.sha256(user_id.encode()).hexdigest()[:12]


class IUserLifecycle(Protocol):
    async def blockers(self, user_id: str) -> DeletionBlockers: ...

    async def erase(self, user_id: str, pseudonym: str) -> ErasureReport:
        """В ambient-транзакции вызывающего: обезличивает журнал, стирает секреты, токены, сессии, членства,
        настройки, письма, квоты, имя в записях сборок и сдач, личные роли агента и саму учётную запись.
        Проекты не трогает: их владелец сначала должен смениться."""
        ...

    async def export(self, user_id: str) -> Mapping[str, object]:
        """Всё, что установка хранит о человеке, без секретов и хешей."""
        ...
