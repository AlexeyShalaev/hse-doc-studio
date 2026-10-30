"""Чтение очереди и раннеров для админки: статус раннера по последнему опросу, фильтры, сводка очереди.

Порядок и аренды остаются у `IJobQueue`; здесь только то, что нужно экранам админа и не нужно раннеру.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from hse_doc_studio.core.jobs.enums import JobKind, JobState
from hse_doc_studio.core.jobs.queue import QueuedJob
from hse_doc_studio.core.jobs.runners import RegistrationToken, Runner
from hse_doc_studio.core.listing import Found, Picked, PickerItem, SortKey, Window

# Долгий опрос раннера длится до 25 с: молчание дольше минуты уже подозрительно, дольше пяти минут означает потерю.
RUNNER_ONLINE_WITHIN = timedelta(seconds=60)
RUNNER_STALE_WITHIN = timedelta(minutes=5)


class RunnerStatus(StrEnum):
    online = "online"
    stale = "stale"
    offline = "offline"
    paused = "paused"
    revoked = "revoked"


def runner_status(runner: Runner, now: datetime) -> RunnerStatus:
    """Отзыв и пауза важнее давности опроса: на паузе раннер опрашивает, но работу не получает."""
    if runner.revoked_at is not None:
        return RunnerStatus.revoked
    if runner.paused:
        return RunnerStatus.paused
    if runner.last_seen_at is None:
        return RunnerStatus.offline
    silence = now - runner.last_seen_at
    if silence <= RUNNER_ONLINE_WITHIN:
        return RunnerStatus.online
    return RunnerStatus.stale if silence <= RUNNER_STALE_WITHIN else RunnerStatus.offline


# Порядок статусов в списке раннеров: работающие сверху, отозванные внизу.
RUNNER_STATUS_ORDER: tuple[RunnerStatus, ...] = (
    RunnerStatus.online,
    RunnerStatus.stale,
    RunnerStatus.offline,
    RunnerStatus.paused,
    RunnerStatus.revoked,
)
RUNNER_SORT_FIELDS = ("name", "status", "last_seen_at", "created_at", "version")
REGISTRATION_TOKEN_SORT_FIELDS = ("created_at", "expires_at", "label")
# Частей версии в сравнении; в каждой берутся ведущие цифры, как parseInt в интерфейсе.
VERSION_PARTS = 4
_VERSION_DIGITS = re.compile(r"^[0-9]{1,9}")


def version_key(version: str) -> tuple[int, ...]:
    """Ключ сравнения версий вида 0.3.0: по числам, а не по строкам; недостающие части равны нулю."""
    parts = version.split(".")
    key: list[int] = []
    for i in range(VERSION_PARTS):
        found = _VERSION_DIGITS.match(parts[i]) if i < len(parts) else None
        key.append(int(found.group()) if found else 0)
    return tuple(key)


class RegistrationTokenStatus(StrEnum):
    active = "active"
    expired = "expired"
    exhausted = "exhausted"
    revoked = "revoked"


def registration_token_status(token: RegistrationToken, now: datetime) -> RegistrationTokenStatus:
    """Отзыв важнее исчерпания, исчерпание важнее срока: так же считает интерфейс."""
    if token.revoked_at is not None:
        return RegistrationTokenStatus.revoked
    if token.uses >= token.max_uses:
        return RegistrationTokenStatus.exhausted
    if token.expires_at is not None and token.expires_at <= now:
        return RegistrationTokenStatus.expired
    return RegistrationTokenStatus.active


@dataclass(frozen=True)
class RunnerQuery:
    q: str | None = None
    statuses: frozenset[RunnerStatus] = frozenset()
    tag: str | None = None
    resource_class: str | None = None
    # Отстаёт от новейшей версии среди неотозванных раннеров.
    outdated: bool | None = None
    sort: SortKey = SortKey("status")
    window: Window = Window()


@dataclass(frozen=True)
class RegistrationTokenQuery:
    q: str | None = None
    statuses: frozenset[RegistrationTokenStatus] = frozenset()
    sort: SortKey = SortKey("created_at", descending=True)
    window: Window = Window()


@dataclass(frozen=True)
class RunnerSummary:
    online: int = 0
    paused: int = 0
    stale: int = 0
    offline: int = 0
    revoked: int = 0
    outdated: int = 0
    newest_version: str | None = None


class IRunnerAdminReader(Protocol):
    """Списки раннеров и токенов для админки: поиск, фильтры, порядок и окно применяет хранилище."""

    async def list_runners(self, query: RunnerQuery, now: datetime) -> Found[Runner]: ...

    async def summary(self, now: datetime) -> RunnerSummary: ...

    async def list_tokens(self, query: RegistrationTokenQuery, now: datetime) -> Found[RegistrationToken]: ...

    async def pick(self, q: str | None, limit: int, *, item_id: str | None = None) -> Picked[PickerItem]:
        """Раннеры для фильтра очереди: по имени, отозванные тоже (у них остались задачи).

        `item_id` находит один раннер по id: так фильтр из ссылки показывает имя.
        """
        ...


@dataclass(frozen=True)
class JobAdminFilter:
    states: frozenset[JobState] = frozenset()
    kinds: frozenset[JobKind] = frozenset()
    user_id: UUID | None = None
    # Ключ организации в очереди (`org_key`), а не id строки организации.
    org_id: UUID | None = None
    project_id: UUID | None = None
    runner_id: UUID | None = None
    # Время постановки: `queued_from` включительно, `queued_to` не включая.
    queued_from: datetime | None = None
    queued_to: datetime | None = None
    # Поиск: id задачи целиком или подстрока в имени проекта, имени и почте человека.
    q: str | None = None

    @property
    def empty(self) -> bool:
        return self == JobAdminFilter()

    @property
    def job_id(self) -> UUID | None:
        """`q` как id задачи (с дефисами или без): тогда ищется одна задача, а не подстрока."""
        if not self.q:
            return None
        try:
            return UUID(self.q.strip())
        except ValueError:
            return None


@dataclass(frozen=True)
class JobListing:
    """Задача с подписями для экрана: имена берутся соединением, у удалённых записей они `None`."""

    job: QueuedJob
    user_name: str | None = None
    user_email: str | None = None
    org_name: str | None = None
    project_name: str | None = None
    runner_name: str | None = None


@dataclass(frozen=True)
class JobAdminPage:
    items: tuple[JobListing, ...]
    # Курсор следующей страницы: `seq` последней записи, пока есть ещё.
    next_before_seq: int | None = None
    # Оценка числа задач по статистике таблицы; только без фильтров.
    total_estimate: int | None = None


@dataclass(frozen=True)
class QueueStats:
    by_state: dict[JobState, int] = field(default_factory=dict)
    queued_by_class: dict[int, int] = field(default_factory=dict)
    oldest_queued_at: datetime | None = None
    # Ожидание в очереди задач, начавшихся за последний час; None, если таких не было.
    wait_p50_s: float | None = None
    wait_p95_s: float | None = None


class IJobAdminReader(Protocol):
    async def list_jobs(self, flt: JobAdminFilter, *, before_seq: int | None, limit: int) -> JobAdminPage:
        """Новые записи первыми; `before_seq` продолжает список с места, где остановилась прошлая страница."""
        ...

    async def get(self, job_id: UUID) -> JobListing | None: ...

    async def stats(self, now: datetime) -> QueueStats: ...


class IAdminProjectPicker(Protocol):
    async def pick(self, q: str | None, limit: int, *, item_id: UUID | None = None) -> Picked[PickerItem]:
        """Проекты установки для фильтра очереди: по имени, без удалённых.

        `item_id` находит один проект по id, и удалённый тоже: у него остались задачи в очереди.
        """
        ...
