"""Маршрут задачи: общие раннеры установки, личные раннеры владельца проекта или один конкретный раннер.

Маршрут решает сервер при постановке (`IJobRouter.decide`), а область исполнения (`RunnerScope`) пишет
очередь при выдаче по записи раннера. По области считаются квоты установки и решается, может ли выход
задачи попасть в кэш, разделяемый между проектами: раннер сам себе область не назначает.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from hse_doc_studio.core.jobs.enums import JobKind

if TYPE_CHECKING:
    from hse_doc_studio.core.jobs.queue import QueuedJob


class JobRoute(StrEnum):
    # Только общие раннеры установки.
    shared = "shared"
    # Сначала личные раннеры владельца проекта, после окна ожидания и общие.
    personal_first = "personal_first"
    # Только один конкретный раннер: так идёт ретрансляция ИИ.
    pinned = "pinned"


class RunnerScope(StrEnum):
    shared = "shared"
    personal = "personal"


class RouteReason(StrEnum):
    waiting_personal = "waiting_personal"
    personal = "personal"
    policy_shared = "policy_shared"
    org_project = "org_project"
    kind_not_allowed = "kind_not_allowed"
    disabled = "disabled"
    fallback_offline = "fallback_offline"
    fallback_busy = "fallback_busy"
    fallback_timeout = "fallback_timeout"
    fallback_lost = "fallback_lost"
    pinned = "pinned"


# Причины, которые выдача общему раннеру сохраняет: остальные после окна становятся `fallback_timeout`.
# `disabled` пишет выключение личных раннеров в установке: человеку важна именно эта причина.
KEPT_FALLBACK_REASONS = frozenset({RouteReason.fallback_offline, RouteReason.fallback_lost, RouteReason.disabled})


class ProjectBuildRunners(StrEnum):
    """Где идут сборки соавторов личного проекта; свои сборки владельца предпочитают его раннер всегда."""

    shared = "shared"
    owner = "owner"


@dataclass(frozen=True)
class ProjectRouteInfo:
    """Что о проекте нужно маршруту: владелец-человек, политика сборок соавторов и удалён ли он."""

    project_id: UUID
    owner_user_id: str | None
    owner_org_id: str | None
    build_runners: ProjectBuildRunners
    deleted: bool = False

    @property
    def is_personal(self) -> bool:
        return self.owner_user_id is not None


class IProjectRoutePolicy(Protocol):
    async def get(self, project_id: UUID) -> ProjectRouteInfo | None: ...

    async def set_build_runners(self, project_id: UUID, policy: ProjectBuildRunners) -> bool:
        """False, если проекта нет."""
        ...


PERSONAL_WAIT_MAX_S = 60
PERSONAL_MAX_PER_USER_LIMIT = 20


@dataclass(frozen=True)
class PersonalRunnerSettings:
    enabled: bool = True
    # Сколько задача `personal_first` ждёт личный раннер, прежде чем её могут взять общие.
    wait_s: int = 5
    # Сколько неотозванных личных раннеров может быть у одного человека.
    max_per_user: int = 5

    def __post_init__(self) -> None:
        if not 0 <= self.wait_s <= PERSONAL_WAIT_MAX_S:
            raise ValueError(f"wait_s must be within 0..{PERSONAL_WAIT_MAX_S}")
        if not 1 <= self.max_per_user <= PERSONAL_MAX_PER_USER_LIMIT:
            raise ValueError(f"max_per_user must be within 1..{PERSONAL_MAX_PER_USER_LIMIT}")


class IPersonalRunnerSettings(Protocol):
    async def current(self) -> PersonalRunnerSettings: ...


@dataclass(frozen=True)
class RouteDecision:
    route: JobRoute
    reason: RouteReason
    route_owner_id: str | None = None
    personal_until: datetime | None = None

    def __post_init__(self) -> None:
        personal = self.route is JobRoute.personal_first
        if personal != (self.route_owner_id is not None and self.personal_until is not None):
            raise ValueError("personal_first needs route_owner_id and personal_until, other routes none")

    @classmethod
    def shared(cls, reason: RouteReason) -> RouteDecision:
        return cls(route=JobRoute.shared, reason=reason)


class IPersonalRunnerLoad(Protocol):
    async def personal_load(self, owner_id: str, runner_ids: frozenset[UUID], now: datetime) -> int:
        """Сколько сборок уже занимают личные раннеры хозяина: идут на них и ждут их в окне ожидания."""
        ...


class IJobRouter(Protocol):
    async def decide(
        self, *, kind: JobKind, tags: frozenset[str], project_id: UUID, user_id: UUID
    ) -> RouteDecision: ...


def may_feed_shared_cache(job: QueuedJob) -> bool:
    """Только выход общего раннера может попасть в кэш, разделяемый между проектами."""
    return job.runner_scope is RunnerScope.shared


def counts_against_installation(job: QueuedJob) -> bool:
    """Тратит ли задача квоты установки (одновременность, длительность, будущий учёт минут)."""
    return job.runner_scope is RunnerScope.shared
