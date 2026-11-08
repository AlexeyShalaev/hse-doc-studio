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
from hse_doc_studio.core.jobs.liveness import DEFAULT_RUNNER_LIVE_WINDOW_S, is_live_shared
from hse_doc_studio.core.jobs.registry import job_kind_spec
from hse_doc_studio.core.jobs.routing import (
    IPersonalRunnerLoad,
    IPersonalRunnerSettings,
    IProjectRoutePolicy,
    JobRoute,
    PersonalRunnerSettings,
    ProjectBuildRunners,
    RouteDecision,
    RouteReason,
)
from hse_doc_studio.core.jobs.runners import IRunnerRepository, Runner


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _is_user(owner_id: str, user_id: UUID) -> bool:
    """Владелец проекта хранится строкой `users.id` (uuid4 hex без дефисов), автор задачи приходит UUID.

    Сравнение строк `str(user_id) == owner_id` никогда не совпадало бы: `str(UUID)` пишется с дефисами.
    Не-UUID владелец (чужой формат id) автором задачи быть не может.
    """
    try:
        return UUID(owner_id) == user_id
    except ValueError:
        return False


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

    async def decide(self, *, kind: JobKind, tags: frozenset[str], project_id: UUID, user_id: UUID) -> RouteDecision:
        settings = await self._settings.current()
        owner, refusal = await self._owner_or_refusal(settings, kind=kind, project_id=project_id, user_id=user_id)
        if owner is None:
            return RouteDecision.shared(refusal)
        now = self._clock()
        candidates = await self.online_runners(owner, tags, now)
        if not candidates:
            return RouteDecision.shared(RouteReason.fallback_offline)
        capacity = sum(runner.concurrency for runner in candidates)
        load = await self._load.personal_load(owner, frozenset(UUID(runner.id) for runner in candidates), now)
        if load >= capacity and await self.has_live_shared(tags, now):
            # «Собрать всё»: первая сборка ждёт свой раннер, остальные сразу идут на общие, а не стоят по окну.
            # Без живого общего раннера с нужными тегами уходить некуда: задача остаётся за личным раннером
            # (его выдача окно не проверяет) и ждёт слот, а не зависает в очереди общих.
            return RouteDecision.shared(RouteReason.fallback_busy)
        return RouteDecision(
            route=JobRoute.personal_first,
            reason=RouteReason.waiting_personal,
            route_owner_id=owner,
            personal_until=now + timedelta(seconds=settings.wait_s),
        )

    async def personal_owner(self, *, kind: JobKind, project_id: UUID, user_id: UUID) -> str | None:
        """Чьи личные раннеры вообще могут взять эту задачу (без оглядки на их состояние); `None`: только общие."""
        owner, _ = await self._owner_or_refusal(
            await self._settings.current(), kind=kind, project_id=project_id, user_id=user_id
        )
        return owner

    async def _owner_or_refusal(
        self, settings: PersonalRunnerSettings, *, kind: JobKind, project_id: UUID, user_id: UUID
    ) -> tuple[str | None, RouteReason]:
        """Шаги спецификации до проверки раннеров: владелец проекта или причина, почему только общие."""
        if not settings.enabled:
            return None, RouteReason.disabled
        if not job_kind_spec(kind).policy.personal_runner_allowed:
            return None, RouteReason.kind_not_allowed
        project = await self._projects.get(project_id)
        if project is None or project.deleted or project.owner_user_id is None:
            return None, RouteReason.org_project
        owner = project.owner_user_id
        if not _is_user(owner, user_id) and project.build_runners is not ProjectBuildRunners.owner:
            return None, RouteReason.policy_shared
        return owner, RouteReason.personal

    async def has_live_shared(self, tags: frozenset[str], now: datetime | None = None) -> bool:
        """Есть ли живой общий раннер с нужными тегами, который подберёт задачу из общей очереди."""
        moment = now or self._clock()
        window = timedelta(seconds=DEFAULT_RUNNER_LIVE_WINDOW_S)
        return any(
            tags <= runner.tags and is_live_shared(runner, moment, window) for runner in await self._runners.list()
        )

    async def online_runners(self, owner_id: str, tags: frozenset[str], now: datetime | None = None) -> list[Runner]:
        """Личные раннеры хозяина в сети (ровно `online`), не на паузе и с нужными тегами."""
        moment = now or self._clock()
        return [
            runner
            for runner in await self._runners.list_owned(owner_id)
            if runner_status(runner, moment) is RunnerStatus.online and tags <= runner.tags
        ]
