"""Подключённые Студии: приём сигнала присутствия и показ устройств по правам (docs/design/connected-devices.md).

Человек видит все свои устройства целиком. Другие участники проекта видят только «автор работает локально» и
только пока его Студия в сети: ни имени машины, ни версии, ни раннера, ни моделей. Админ установки не видит
ничего сверх обычного: отдельного маршрута для него нет.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

import structlog

from hse_doc_studio.core.access.actions import Action
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.access.policy import Decision, decide
from hse_doc_studio.core.access.repositories import IProjectAclRepository
from hse_doc_studio.core.devices.ai import ProviderRef, RunnerFacts, endpoint_state, overall_state
from hse_doc_studio.core.devices.entities import (
    ConnectedDevice,
    DeviceReport,
    Presence,
    PresenceConfig,
)
from hse_doc_studio.core.devices.protocols import IDeviceRepository, IPresenceRegistry
from hse_doc_studio.core.devices.views import (
    AccountDevices,
    AiView,
    DeviceView,
    EndpointView,
    ProjectStudios,
    ProjectSyncView,
    RunnerView,
    WorkingLocally,
)
from hse_doc_studio.core.enums import AIProviderType
from hse_doc_studio.core.identity.protocols import IUserRepository
from hse_doc_studio.core.jobs.admin import runner_status
from hse_doc_studio.core.jobs.routing import IPersonalRunnerSettings
from hse_doc_studio.core.jobs.runners import IRunnerRepository, Runner
from hse_doc_studio.core.jobs.wire import FEATURE_AI_RELAY
from hse_doc_studio.core.repositories import IAIProviderRepository

if TYPE_CHECKING:
    from hse_doc_studio.core.devices.people import ProjectPeople
    from hse_doc_studio.use_cases.devices.people import ProjectPeopleUC

logger = structlog.get_logger()

MAX_DEVICES_PER_USER = 20
_PURGE_EVERY = timedelta(hours=1)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class TooManyDevicesError(Exception):
    """У человека уже `MAX_DEVICES_PER_USER` устройств: лишнее удаляют на странице аккаунта."""


@dataclass(frozen=True)
class HeartbeatReceipt:
    interval_s: int
    online_window_s: int
    server_time: datetime
    persisted: bool


class RecordHeartbeatUC:
    def __init__(
        self,
        devices: IDeviceRepository,
        registry: IPresenceRegistry,
        config: PresenceConfig,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._devices = devices
        self._registry = registry
        self._config = config
        self._clock = clock
        self._purged_at: datetime | None = None

    async def execute(self, user_id: str, token_id: str | None, report: DeviceReport) -> HeartbeatReceipt:
        now = self._clock()
        due = self._registry.observe(user_id, report, now, self._config.persist_interval_s)
        if due:
            existing = await self._devices.get(user_id, report.device_id)
            if existing is None and len(await self._devices.list_for_user(user_id)) >= MAX_DEVICES_PER_USER:
                self._registry.forget(user_id, report.device_id)
                raise TooManyDevicesError
            await self._devices.upsert(
                ConnectedDevice(
                    user_id=user_id,
                    device_id=report.device_id,
                    first_seen_at=existing.first_seen_at if existing else now,
                    last_seen_at=now,
                    report=report,
                    token_id=token_id,
                )
            )
            await self._purge(now)
        return HeartbeatReceipt(self._config.interval_s, self._config.online_window_s, now, due)

    async def _purge(self, now: datetime) -> None:
        """Забытые устройства уходят сами: раз в час стираются те, что молчат дольше срока хранения."""
        if self._purged_at is not None and now - self._purged_at < _PURGE_EVERY:
            return
        self._purged_at = now
        horizon = now - timedelta(days=self._config.retention_days)
        try:
            removed = await self._devices.purge_older_than(horizon)
        except Exception:  # noqa: BLE001 — чистка вторична: сигнал уже записан
            logger.warning("devices purge failed", exc_info=True)
            return
        self._registry.prune(horizon)
        if removed:
            logger.info("stale devices purged", count=removed)


class DeviceViewBuilder:
    """Собирает вид устройств одного человека: время из памяти поверх БД, раннер и провайдеры из таблиц сервера."""

    def __init__(
        self,
        runners: IRunnerRepository,
        providers: IAIProviderRepository,
        settings: IPersonalRunnerSettings | None,
        registry: IPresenceRegistry,
        config: PresenceConfig,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._runners = runners
        self._providers = providers
        self._settings = settings
        self._registry = registry
        self._config = config
        self._clock = clock

    def last_seen(self, device: ConnectedDevice) -> datetime:
        fresh = self._registry.last_seen(device.user_id, device.device_id)
        return max(device.last_seen_at, fresh) if fresh is not None else device.last_seen_at

    def online(self, device: ConnectedDevice) -> bool:
        return self._config.online(self.last_seen(device), self._clock())

    async def build(
        self, owner_id: str, devices: list[ConnectedDevice], *, project_id: UUID | None = None
    ) -> list[DeviceView]:
        if not devices:
            return []
        now = self._clock()
        owned = {runner.id: runner for runner in await self._runners.list_owned(owner_id)}
        enabled = (await self._settings.current()).enabled if self._settings is not None else True
        providers = [p for p in await self._providers.list_all() if p.type is AIProviderType.runner]
        by_endpoint = {(p.runner_id, p.runner_endpoint): ProviderRef(p.id, p.name) for p in providers}
        return [self._one(device, owned, enabled, by_endpoint, now, project_id) for device in devices]

    def _one(  # noqa: PLR0913 — данные одного устройства из общих выборок
        self,
        device: ConnectedDevice,
        owned: dict[str, Runner],
        enabled: bool,
        providers: dict[tuple[str | None, str | None], ProviderRef],
        now: datetime,
        project_id: UUID | None,
    ) -> DeviceView:
        report = device.report
        seen = self.last_seen(device)
        online = self._config.online(seen, now)
        claimed = report.runner.runner_id if report.runner is not None else None
        runner = owned.get(claimed) if claimed else None
        facts = _facts(runner, now, enabled)
        reports = {e.name: e for e in report.endpoints}
        endpoints: list[EndpointView] = []
        if runner is not None and facts is not None:
            for declared in runner.ai_endpoints:
                known = reports.get(declared.name)
                ref = providers.get((runner.id, declared.name))
                state = endpoint_state(runner=facts, report=known, provider=ref)
                endpoints.append(
                    EndpointView(
                        name=declared.name,
                        flavor=declared.flavor.value,
                        reachable=known.reachable if known is not None else None,
                        models=known.models if known is not None else (),
                        provider_id=ref.id if ref is not None else None,
                        provider_name=ref.name if ref is not None else None,
                        state=state,
                    )
                )
        ai = AiView(
            state=overall_state(
                online=online,
                paired=runner is not None,
                runner=facts,
                endpoints=tuple(e.state for e in endpoints),
            ),
            endpoints=tuple(endpoints),
        )
        mine = next((p for p in report.projects if p.project_id == project_id), None) if project_id else None
        return DeviceView(
            id=device.device_id,
            name=report.name,
            version=report.version,
            os=report.os,
            presence=Presence.online if online else Presence.offline,
            last_seen_at=seen,
            activity=report.activity,
            projects_count=len(report.projects),
            runner=_runner_view(runner, facts, report) if runner is not None and facts is not None else None,
            ai=ai,
            project=None
            if mine is None
            else ProjectSyncView(mine.sync, mine.ahead, mine.behind, mine.last_sync_at, mine.auto_sync, mine.pdf),
            project_id=project_id if mine is not None else None,
        )


def _facts(runner: Runner | None, now: datetime, enabled: bool) -> RunnerFacts | None:
    if runner is None:
        return None
    status = runner_status(runner, now, personal_enabled=enabled)
    return RunnerFacts(
        status=status.value,
        declared=frozenset(e.name for e in runner.ai_endpoints),
        relay_feature=FEATURE_AI_RELAY in runner.features,
    )


def _runner_view(runner: Runner, facts: RunnerFacts, report: DeviceReport) -> RunnerView:
    running = report.runner.running_jobs if report.runner is not None else 0
    return RunnerView(
        id=runner.id,
        name=runner.name,
        state=facts.status,
        tags=tuple(sorted(runner.tags)),
        concurrency=runner.concurrency,
        running_jobs=running,
        busy=running >= runner.concurrency > 0,
    )


class ListAccountDevicesUC:
    def __init__(self, devices: IDeviceRepository, builder: DeviceViewBuilder, config: PresenceConfig) -> None:
        self._devices = devices
        self._builder = builder
        self._config = config

    async def execute(self, actor: Actor) -> AccountDevices:
        owner = _owner(actor)
        views = await self._builder.build(owner, await self._devices.list_for_user(owner))
        return AccountDevices(self._config.online_window_s, tuple(views))


class ForgetDeviceUC:
    def __init__(self, devices: IDeviceRepository, registry: IPresenceRegistry) -> None:
        self._devices = devices
        self._registry = registry

    async def execute(self, actor: Actor, device_id: str) -> bool:
        owner = _owner(actor)
        self._registry.forget(owner, device_id)
        return await self._devices.delete(owner, device_id)


class ProjectStudiosUC:
    """Студии у проекта: свои целиком, чужие одной строкой «работает локально» и только пока в сети."""

    def __init__(
        self,
        devices: IDeviceRepository,
        builder: DeviceViewBuilder,
        acl: IProjectAclRepository,
        users: IUserRepository,
        config: PresenceConfig,
    ) -> None:
        self._devices = devices
        self._builder = builder
        self._acl = acl
        self._users = users
        self._config = config

    async def execute(self, actor: Actor, project_id: UUID) -> ProjectStudios:
        owner = _owner(actor)
        reporting = await self._devices.list_for_project(project_id)
        mine = [d for d in reporting if d.user_id == owner]
        others = await self.people(actor, project_id, [d for d in reporting if d.user_id != owner])
        views = await self._builder.build(owner, mine, project_id=project_id)
        return ProjectStudios(self._config.online_window_s, tuple(views), others)

    async def people(
        self, viewer: Actor, project_id: UUID, devices: list[ConnectedDevice]
    ) -> tuple[WorkingLocally, ...]:
        """Люди с проектом в сети. Право участника проверяется заново на каждый показ: доступ мог закрыться."""
        online: dict[str, ConnectedDevice] = {}
        for device in devices:
            if device.user_id != viewer.id and self._builder.online(device):
                online.setdefault(device.user_id, device)
        found: list[WorkingLocally] = []
        for user_id in sorted(online):
            user = await self._users.get(user_id)
            if user is None:
                continue
            member = Actor.user(user.id, user.name, user.email)
            acl = await self._acl.load_for(member, project_id, include_links=False)
            if decide(member, Action.PROJECT_VIEW, acl) is Decision.allow:
                found.append(WorkingLocally(user_id=user.id, name=user.name))
        return tuple(found)


@dataclass(frozen=True)
class DevicesOverview:
    """Как облако видит эту Студию и кто ещё в проекте работает локально (ответ локальной Студии)."""

    online_window_s: int
    device: DeviceView | None
    others: tuple[WorkingLocally, ...] = ()
    # Все, кто сейчас в проекте (веб и Студия), с местом и ролью; None, пока право на исходники не открыто.
    people: ProjectPeople | None = None


class DevicesOverviewUC:
    def __init__(
        self,
        devices: IDeviceRepository,
        builder: DeviceViewBuilder,
        studios: ProjectStudiosUC,
        acl: IProjectAclRepository,
        config: PresenceConfig,
        people: ProjectPeopleUC | None = None,
    ) -> None:
        self._devices = devices
        self._builder = builder
        self._studios = studios
        self._acl = acl
        self._config = config
        self._people = people

    async def execute(
        self, actor: Actor, device_id: str, project_id: UUID | None, *, with_people: bool = False
    ) -> DevicesOverview:
        owner = _owner(actor)
        own = await self._devices.get(owner, device_id)
        views = await self._builder.build(owner, [own], project_id=project_id) if own is not None else []
        others: tuple[WorkingLocally, ...] = ()
        people: ProjectPeople | None = None
        if project_id is not None:
            acl = await self._acl.load_for(actor, project_id, include_links=False)
            if decide(actor, Action.GIT_FETCH, acl) is Decision.allow:
                reporting = await self._devices.list_for_project(project_id)
                others = await self._studios.people(actor, project_id, reporting)
                if with_people and self._people is not None:
                    people = await self._people.execute(actor, project_id, reporting)
        return DevicesOverview(self._config.online_window_s, views[0] if views else None, others, people)


def _owner(actor: Actor) -> str:
    if actor.id is None:
        raise PermissionError("device access requires a signed-in person")
    return actor.id


__all__ = [
    "AccountDevices",
    "DeviceViewBuilder",
    "DevicesOverview",
    "DevicesOverviewUC",
    "ForgetDeviceUC",
    "HeartbeatReceipt",
    "ListAccountDevicesUC",
    "ProjectStudiosUC",
    "RecordHeartbeatUC",
    "TooManyDevicesError",
]
