"""Маршрут задачи между общими и личными раннерами: значения, настройки установки и правила кэша и квот.

Маршрут решает сервер при постановке (`IJobRouter`), область исполнения (`RunnerScope`) пишет сервер при
выдаче по записи раннера. Раннер ни то, ни другое изменить не может.
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
    shared = "shared"
    personal_first = "personal_first"
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


class ProjectBuildRunners(StrEnum):
    shared = "shared"
    owner = "owner"


@dataclass(frozen=True)
class PersonalRunnerSettings:
    enabled: bool = True
    wait_s: int = 5
    max_per_user: int = 5


class IPersonalRunnerSettings(Protocol):
    async def current(self) -> PersonalRunnerSettings: ...


@dataclass(frozen=True)
class RouteDecision:
    route: JobRoute
    reason: RouteReason
    route_owner_id: str | None = None
    personal_until: datetime | None = None


class IJobRouter(Protocol):
    async def decide(
        self, *, kind: JobKind, tags: frozenset[str], project_id: UUID, user_id: UUID
    ) -> RouteDecision: ...


def may_feed_shared_cache(job: QueuedJob) -> bool:
    """Только выход общего раннера может попасть в кэш, разделяемый между проектами."""
    return job.runner_scope is RunnerScope.shared


def counts_against_installation(job: QueuedJob) -> bool:
    return job.runner_scope is RunnerScope.shared
