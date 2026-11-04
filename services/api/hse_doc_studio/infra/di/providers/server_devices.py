"""Подключённые Студии на сервере: присутствие, видимость устройств по правам (docs/design/connected-devices.md)."""

from __future__ import annotations

from dishka import Provider, Scope, provide

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.access.repositories import IProjectAclRepository
from hse_doc_studio.core.devices.entities import PresenceConfig
from hse_doc_studio.core.devices.protocols import IDeviceRepository, IPresenceRegistry
from hse_doc_studio.core.identity.protocols import IUserRepository
from hse_doc_studio.core.jobs.routing import IPersonalRunnerSettings
from hse_doc_studio.core.jobs.runners import IRunnerRepository
from hse_doc_studio.core.repositories import IAIProviderRepository
from hse_doc_studio.infra.db.repositories.devices import PostgresDeviceRepository
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.devices.registry import PresenceRegistry
from hse_doc_studio.use_cases.devices.service import (
    DevicesOverviewUC,
    DeviceViewBuilder,
    ForgetDeviceUC,
    ListAccountDevicesUC,
    ProjectStudiosUC,
    RecordHeartbeatUC,
)


class ServerDevicesProvider(Provider):
    scope = Scope.APP

    @provide
    def get_presence_config(self) -> PresenceConfig:
        cfg = settings.devices
        return PresenceConfig(
            interval_s=cfg.interval_s,
            online_window_s=max(cfg.online_window_s, 3 * cfg.interval_s),
            persist_interval_s=cfg.persist_interval_s,
            retention_days=cfg.retention_days,
        )

    @provide
    def get_registry(self) -> IPresenceRegistry:
        return PresenceRegistry()

    @provide
    def get_device_repository(self, sessions: SessionProvider) -> IDeviceRepository:
        return PostgresDeviceRepository(sessions)

    @provide(scope=Scope.REQUEST)
    def get_heartbeat(
        self, devices: IDeviceRepository, registry: IPresenceRegistry, config: PresenceConfig
    ) -> RecordHeartbeatUC:
        return RecordHeartbeatUC(devices, registry, config)

    @provide(scope=Scope.REQUEST)
    def get_builder(
        self,
        runners: IRunnerRepository,
        providers: IAIProviderRepository,
        personal: IPersonalRunnerSettings,
        registry: IPresenceRegistry,
        config: PresenceConfig,
    ) -> DeviceViewBuilder:
        return DeviceViewBuilder(runners, providers, personal, registry, config)

    @provide(scope=Scope.REQUEST)
    def get_list_account(
        self, devices: IDeviceRepository, builder: DeviceViewBuilder, config: PresenceConfig
    ) -> ListAccountDevicesUC:
        return ListAccountDevicesUC(devices, builder, config)

    @provide(scope=Scope.REQUEST)
    def get_forget(self, devices: IDeviceRepository, registry: IPresenceRegistry) -> ForgetDeviceUC:
        return ForgetDeviceUC(devices, registry)

    @provide(scope=Scope.REQUEST)
    def get_project_studios(  # noqa: PLR0913 — порты одного сценария
        self,
        devices: IDeviceRepository,
        builder: DeviceViewBuilder,
        acl: IProjectAclRepository,
        users: IUserRepository,
        config: PresenceConfig,
    ) -> ProjectStudiosUC:
        return ProjectStudiosUC(devices, builder, acl, users, config)

    @provide(scope=Scope.REQUEST)
    def get_overview(  # noqa: PLR0913 — порты одного сценария
        self,
        devices: IDeviceRepository,
        builder: DeviceViewBuilder,
        studios: ProjectStudiosUC,
        acl: IProjectAclRepository,
        config: PresenceConfig,
    ) -> DevicesOverviewUC:
        return DevicesOverviewUC(devices, builder, studios, acl, config)
