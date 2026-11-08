"""Техническая информация о раннерах в админке: как раннер развёрнут и как изолированы раннеры в кластере.

Три источника, и экран их не смешивает: конфигурация Студии (выжимка Helm и настройки установки из админки), отчёт
самого раннера (`/deployment`) и живое состояние кластера, прочитанное в пределах выданных Студии прав.
"""

from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.jobs.errors import RunnerNotFoundError
from hse_doc_studio.core.jobs.runners import IRunnerRepository, Runner, RunnerOwnerKind
from hse_doc_studio.core.runner_isolation import (
    ClusterTargets,
    DeclaredCluster,
    IClusterStateReader,
    InstallFromUiFacts,
    LiveClusterState,
    LiveDeployment,
    LookupStatus,
    ReinstallReason,
    RunnerOrigin,
    is_outdated,
    limits_supported,
    match_deployment,
    reinstall_reasons,
    runner_origin,
)
from hse_doc_studio.use_cases.admin.users import require_admin


@dataclass(frozen=True)
class RunnerIsolationSettings:
    """То, что Студия знает из своей конфигурации; `declared` пусто вне Helm."""

    declared: DeclaredCluster | None
    install: InstallFromUiFacts
    read_live: bool
    studio_version: str


@dataclass(frozen=True)
class RunnerDeploymentInfo:
    runner: Runner
    studio_version: str
    outdated: bool
    limits_supported: bool | None
    reinstall: tuple[ReinstallReason, ...]
    origin: RunnerOrigin | None
    live: LiveDeployment | None
    live_status: LookupStatus


@dataclass(frozen=True)
class ClusterIsolationInfo:
    declared: DeclaredCluster | None
    install: InstallFromUiFacts
    live: LiveClusterState


class RunnerDeploymentUC:
    def __init__(
        self, runners: IRunnerRepository, reader: IClusterStateReader, settings: RunnerIsolationSettings
    ) -> None:
        self._runners = runners
        self._reader = reader
        self._settings = settings

    async def execute(self, actor: Actor, runner_id: str) -> RunnerDeploymentInfo:
        require_admin(actor)
        runner = await self._runners.get(runner_id)
        # Личные раннеры людей это их машины: их развёртывание админке не показываем.
        if runner is None or runner.owner_kind is not RunnerOwnerKind.instance:
            raise RunnerNotFoundError(runner_id)
        settings = self._settings
        live: LiveDeployment | None = None
        status = LookupStatus.not_applicable
        if settings.install.enabled and runner.revoked_at is None:
            listing = await self._reader.runner_deployments()
            status = listing.status
            if listing.status is LookupStatus.ok:
                live = match_deployment(runner, listing.items)
                status = LookupStatus.ok if live is not None else LookupStatus.not_found
        return RunnerDeploymentInfo(
            runner=runner,
            studio_version=settings.studio_version,
            outdated=is_outdated(runner.version, settings.studio_version),
            limits_supported=limits_supported(runner.version),
            reinstall=reinstall_reasons(runner, live),
            origin=runner_origin(runner, live, settings.declared, settings.install.service_account),
            live=live,
            live_status=status,
        )


class RunnerIsolationUC:
    def __init__(self, reader: IClusterStateReader, settings: RunnerIsolationSettings) -> None:
        self._reader = reader
        self._settings = settings

    async def execute(self, actor: Actor) -> ClusterIsolationInfo:
        require_admin(actor)
        settings = self._settings
        declared = settings.declared
        live = LiveClusterState()
        if settings.read_live and declared is not None and declared.release_namespace:
            build_ns = declared.build.namespace or declared.release_namespace
            live = await self._reader.cluster_state(
                ClusterTargets(release_namespace=declared.release_namespace, build_namespace=build_ns)
            )
        return ClusterIsolationInfo(declared=declared, install=settings.install, live=live)
