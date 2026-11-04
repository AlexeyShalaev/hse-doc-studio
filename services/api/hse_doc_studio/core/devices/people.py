"""Люди, которые сейчас в проекте: веб-сессии и локальные Студии одним списком (docs/design/connected-devices.md, 15).

Сервер хранит только то, что нужно для аватаров в шапке: кто, в каком режиме и на каком документе проекта (не
глубже документа). Содержимого, путей и позиций курсора здесь нет: курсоры живут в комнате совместной правки.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from hse_doc_studio.core.access.entities import Role

# Документ проекта по идентификатору экземпляра `<база>--<автор>`; то же ограничение, что у сигнала Студии.
DOC_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
SESSION_ID_RE = re.compile(r"[A-Za-z0-9_-]{8,64}")
MAX_SESSIONS_PER_USER = 8
MAX_SESSIONS_PER_PROJECT = 300
MAX_SESSIONS_TOTAL = 5000
# Сколько показывать людей в ответе: остальных клиент всё равно сворачивает в «+N».
MAX_PEOPLE = 50


class Activity(StrEnum):
    """Что человек делает в проекте. `local` сервер выводит сам из сигнала Студии, веб-клиент его не присылает."""

    editing = "editing"
    viewing = "viewing"
    reviewing = "reviewing"
    building = "building"
    browsing = "browsing"
    local = "local"


REPORTABLE = frozenset(Activity) - {Activity.local}
# Режимы, которых вправе заявить только тот, кто может править: читатель и рецензент «смотрят».
NEEDS_WRITE = frozenset({Activity.editing})
WRITE_ROLES = frozenset({Role.owner, Role.editor})


class Channel(StrEnum):
    web = "web"
    studio = "studio"


@dataclass(frozen=True)
class WebSignal:
    """Сигнал одной вкладки: она же ключ (человек и сессия вкладки)."""

    session_id: str
    activity: Activity
    doc_id: str | None = None


@dataclass(frozen=True)
class WebSession:
    user_id: str
    name: str
    session_id: str
    activity: Activity
    doc_id: str | None
    seen_at: datetime


@dataclass(frozen=True)
class PersonOnline:
    user_id: str
    name: str
    initials: str
    color: str
    role: Role
    me: bool
    activity: Activity
    doc_id: str | None
    channels: tuple[Channel, ...]
    seen_at: datetime


@dataclass(frozen=True)
class ProjectPeople:
    interval_s: int
    online_window_s: int
    people: tuple[PersonOnline, ...]
    # Сколько человек онлайн всего; в `people` их не больше MAX_PEOPLE.
    total: int


def sanitize_doc(value: str | None) -> str | None:
    return value if value is not None and DOC_ID_RE.fullmatch(value) else None
