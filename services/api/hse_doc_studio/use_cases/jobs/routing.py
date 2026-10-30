"""Маршрут задачи при постановке: личные раннеры владельца проекта или общие раннеры установки.

Порядок шагов закреплён спецификацией: выключено в установке, вид не разрешён, проект организации,
политика проекта для соавтора, раннеры в сети с нужными тегами, ёмкость. Свой раннер никогда не собирает
проекты, где его хозяин не владелец, даже если он там соавтор: решение принимается по владельцу проекта.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from hse_doc_studio.core.jobs.admin import RunnerStatus, runner_status
from hse_doc_studio.core.jobs.enums import JobKind
from hse_doc_studio.core.jobs.registry import job_kind_spec
from hse_doc_studio.core.jobs.routing import (
    IPersonalRunnerLoad,
    IPersonalRunnerSettings,
    IProjectRoutePolicy,
    JobRoute,
    ProjectBuildRunners,
    RouteDecision,
    RouteReason,
)
from hse_doc_studio.core.jobs.runners import IRunnerRepository, Runner


def _utc_now() -> datetime:
    return datetime.now(UTC)


class JobRouter:
    def __init__(
        self,
        settings: IPersonalRunnerSettings,
        projects: IProjectRoutePolicy,
        runners: IRunnerRepository,
        load: IPersonalRunnerLoad,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._settings = settings
        self._projects = projects
        self._runners = runners
        self._load = load
        self._clock = clock

    async def decide(  # noqa: PLR0911 — шаги и их порядок закреплены спецификацией
        self, *, kind: JobKind, tags: frozenset[str], project_id: UUID, user_id: UUID
    ) -> RouteDecision:
        settings = await self._settings.current()
        if not settings.enabled:
            return RouteDecision.shared(RouteReason.disabled)
        if not job_kind_spec(kind).policy.personal_runner_allowed:
            return RouteDecision.shared(RouteReason.kind_not_allowed)
        project = await self._projects.get(project_id)
        if project is None or project.deleted or project.owner_user_id is None:
            return RouteDecision.shared(RouteReason.org_project)
        owner = project.owner_user_id
        if str(user_id) != owner and project.build_runners is not ProjectBuildRunners.owner:
            return RouteDecision.shared(RouteReason.policy_shared)
        now = self._clock()
        candidates = await self.online_runners(owner, tags, now)
        if not candidates:
            return RouteDecision.shared(RouteReason.fallback_offline)
        capacity = sum(runner.concurrency for runner in candidates)
        load = await self._load.personal_load(owner, frozenset(UUID(runner.id) for runner in candidates), now)
        if load >= capacity:
            # «Собрать всё»: первая сборка ждёт свой раннер, остальные сразу идут на общие, а не стоят по окну.
            return RouteDecision.shared(RouteReason.fallback_busy)
        return RouteDecision(
            route=JobRoute.personal_first,
            reason=RouteReason.waiting_personal,
            route_owner_id=owner,
            personal_until=now + timedelta(seconds=settings.wait_s),
        )

    async def online_runners(self, owner_id: str, tags: frozenset[str], now: datetime | None = None) -> list[Runner]:
        """Личные раннеры хозяина в сети (ровно `online`), не на паузе и с нужными тегами."""
        moment = now or self._clock()
        return [
            runner
            for runner in await self._runners.list_owned(owner_id)
            if runner_status(runner, moment) is RunnerStatus.online and tags <= runner.tags
        ]
