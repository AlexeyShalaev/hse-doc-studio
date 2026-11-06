"""Доступность сборки по живым раннерам: те же правила, что у проверки перед постановкой сборки."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.jobs.availability import BUILD_TAGS, BuildAvailability
from hse_doc_studio.core.jobs.enums import JobKind
from hse_doc_studio.core.jobs.liveness import DEFAULT_RUNNER_LIVE_WINDOW_S, is_live_shared
from hse_doc_studio.core.jobs.routing import IJobRouter, JobRoute
from hse_doc_studio.core.jobs.runners import IRunnerRepository

logger = structlog.get_logger()

type ActorPayer = Callable[[Actor, UUID], Awaitable[UUID]]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class LocalBuildAvailability:
    """Локальный режим: собирает сама Студия, раннеры не нужны."""

    async def of(self, project_id: UUID, actor: Actor) -> BuildAvailability:  # noqa: ARG002
        return BuildAvailability.local()

    async def general(self) -> BuildAvailability:
        return BuildAvailability.local()


class RunnerBuildAvailability:
    """Теги общих живых раннеров плюс теги личных раннеров владельца, если маршрут их допускает.

    Для тега без общего раннера маршрут занятого личного раннера остаётся за ним (`personal_first`), поэтому
    такой тег обслуживается. `fallback_busy` бывает только при живом общем раннере с этим тегом.
    """

    def __init__(
        self,
        runners: IRunnerRepository,
        *,
        router: IJobRouter | None = None,
        payer: ActorPayer | None = None,
        runner_live_window_s: float = DEFAULT_RUNNER_LIVE_WINDOW_S,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._runners = runners
        self._router = router
        self._payer = payer
        self._live_window = timedelta(seconds=runner_live_window_s)
        self._clock = clock

    async def _shared(self) -> tuple[bool, set[str]]:
        now = self._clock()
        live = [r for r in await self._runners.list() if is_live_shared(r, now, self._live_window)]
        tags: set[str] = set()
        for runner in live:
            tags |= runner.tags & BUILD_TAGS
        return bool(live), tags

    async def general(self) -> BuildAvailability:
        any_live, tags = await self._shared()
        return BuildAvailability(cloud=True, any_runner=any_live, tags=frozenset(tags))

    async def of(self, project_id: UUID, actor: Actor) -> BuildAvailability:
        any_live, tags = await self._shared()
        personal = await self._personal_tags(project_id, actor, BUILD_TAGS - tags)
        return BuildAvailability(cloud=True, any_runner=any_live or bool(personal), tags=frozenset(tags | personal))

    async def _personal_tags(self, project_id: UUID, actor: Actor, missing: frozenset[str]) -> frozenset[str]:
        if self._router is None or not missing:
            return frozenset()
        try:
            user_id = await self._payer(actor, project_id) if self._payer is not None else UUID(str(actor.id))
        except Exception as exc:  # noqa: BLE001 — гостю без плательщика личные раннеры просто не в счёт
            logger.debug("build availability: no payer", project_id=str(project_id), exc=repr(exc))
            return frozenset()
        served: set[str] = set()
        for tag in sorted(missing):
            decision = await self._router.decide(
                kind=JobKind.compile, tags=frozenset({tag}), project_id=project_id, user_id=user_id
            )
            if decision.route is JobRoute.personal_first:
                served.add(tag)
        return frozenset(served)
