"""Где идут сборки проекта: политика сборок соавторов и раннеры владельца, видимые участникам по имени и состоянию.

Права на чтение и правку проверяет гард маршрута (просмотр проекта и настройки проекта). Соавтор о раннерах
владельца узнаёт только имя и состояние: ни IP, ни версии, ни тегов.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from hse_doc_studio.core.access.checker import ProjectForbiddenError
from hse_doc_studio.core.access.entities import Actor, Role
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.protocols import IAuditLog
from hse_doc_studio.core.jobs.admin import RunnerStatus, runner_status
from hse_doc_studio.core.jobs.routing import (
    IPersonalRunnerSettings,
    IProjectRoutePolicy,
    ProjectBuildRunners,
    ProjectRouteInfo,
    RouteReason,
)
from hse_doc_studio.core.jobs.runners import IRunnerRepository
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.jobs.queue_service import JobQueueService


def _utc_now() -> datetime:
    return datetime.now(UTC)


class MyBuilds(StrEnum):
    personal_first = "personal_first"
    shared = "shared"


@dataclass(frozen=True)
class OwnerRunnerChip:
    name: str
    state: RunnerStatus


@dataclass(frozen=True)
class ProjectBuildRunnersView:
    policy: ProjectBuildRunners
    editable: bool
    personal_project: bool
    personal_runners_enabled: bool
    my_builds: MyBuilds
    wait_s: int
    owner_runners: tuple[OwnerRunnerChip, ...]


class ProjectBuildRunnersService:
    def __init__(  # noqa: PLR0913
        self,
        projects: IProjectRoutePolicy,
        runners: IRunnerRepository,
        settings: IPersonalRunnerSettings,
        audit: IAuditLog,
        uow: IUnitOfWork,
        queue: JobQueueService | None = None,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._projects = projects
        self._runners = runners
        self._settings = settings
        self._audit = audit
        self._uow = uow
        self._queue = queue
        self._clock = clock

    async def view(self, actor: Actor, project_id: UUID) -> ProjectBuildRunnersView:
        info = await self._project(project_id)
        settings = await self._settings.current()
        now = self._clock()
        chips: tuple[OwnerRunnerChip, ...] = ()
        if info.owner_user_id is not None:
            chips = tuple(
                OwnerRunnerChip(runner.name, runner_status(runner, now, personal_enabled=settings.enabled))
                for runner in await self._runners.list_owned(info.owner_user_id)
                if runner.revoked_at is None
            )
        is_owner = info.owner_user_id is not None and actor.id == info.owner_user_id
        may_go_personal = (
            settings.enabled
            and info.is_personal
            and (is_owner or info.build_runners is ProjectBuildRunners.owner)
            and any(chip.state is RunnerStatus.online for chip in chips)
        )
        return ProjectBuildRunnersView(
            policy=info.build_runners,
            editable=is_owner,
            personal_project=info.is_personal,
            personal_runners_enabled=settings.enabled,
            my_builds=MyBuilds.personal_first if may_go_personal else MyBuilds.shared,
            wait_s=settings.wait_s,
            owner_runners=chips,
        )

    async def set_policy(self, actor: Actor, project_id: UUID, policy: ProjectBuildRunners) -> ProjectBuildRunnersView:
        info = await self._project(project_id)
        if not info.is_personal:
            raise IdentityError(IdentityErrorCode.project_not_personal)
        if actor.id != info.owner_user_id:
            raise ProjectForbiddenError(required_role=Role.owner)
        if policy is not info.build_runners:
            async with self._uow.begin():
                await self._projects.set_build_runners(project_id, policy)
                await self._audit.record(
                    "project.build_runners_update",
                    actor_id=actor.id,
                    target=str(project_id),
                    details={"policy": policy.value},
                )
            if policy is ProjectBuildRunners.shared and self._queue is not None:
                # Сборки соавторов, ждущие раннер владельца, сразу уходят на общие; свои сборки владельца ждут дальше.
                await self._queue.expire_personal_wait(
                    project_id=project_id, reason=RouteReason.policy_shared, coauthors_only=True
                )
        return await self.view(actor, project_id)

    async def _project(self, project_id: UUID) -> ProjectRouteInfo:
        info = await self._projects.get(project_id)
        if info is None or info.deleted:
            raise IdentityError(IdentityErrorCode.not_found)
        return info
