"""Облачные сборки локальной Студии: только локальный контейнер, на сервере этих зависимостей нет."""

from __future__ import annotations

import socket

from dishka import AnyOf, Provider, Scope, provide

from hse_doc_studio import __version__
from hse_doc_studio.api.config import settings
from hse_doc_studio.core.jobs.protocols import IJobDispatcher
from hse_doc_studio.core.paths import PathMapping
from hse_doc_studio.core.remote_runner import IRemoteRunnerSettingsStore, IRemoteRunnerSupervisor
from hse_doc_studio.core.repositories import ISettingsRepository
from hse_doc_studio.infra.compile.host_path_resolver import HostPathResolver
from hse_doc_studio.infra.remote_runner.environment import LocalRunnerEnvironment
from hse_doc_studio.infra.remote_runner.runner_session import runner_session_factory
from hse_doc_studio.infra.remote_runner.settings_store import JsonRemoteRunnerSettingsStore
from hse_doc_studio.infra.remote_runner.supervisor import RUNNER_DIR_NAME, RemoteRunnerSupervisor
from hse_doc_studio.infra.runner.pairing_client import RunnerPairingClient
from hse_doc_studio.use_cases.remote_runner.update_remote_runner import UpdateRemoteRunnerUC


class LocalRemoteRunnerProvider(Provider):
    scope = Scope.APP

    @provide
    def get_settings_store(self) -> IRemoteRunnerSettingsStore:
        return JsonRemoteRunnerSettingsStore(settings.data_dir.expanduser())

    @provide
    def get_supervisor(
        self,
        store: IRemoteRunnerSettingsStore,
        settings_repo: ISettingsRepository,
        dispatcher: IJobDispatcher,
        mapping: PathMapping,
    ) -> AnyOf[RemoteRunnerSupervisor, IRemoteRunnerSupervisor]:
        # Тот же том кэша TeX и то же соответствие путей, что у локальных сборок: в образе all-in-one
        # docker монтирует папку облачной сборки по пути хоста.
        sessions = runner_session_factory(
            cache_volume=settings.compile.cache_volume_name, host_paths=HostPathResolver(mapping)
        )
        return RemoteRunnerSupervisor(
            store,
            runner_dir=settings.data_dir.expanduser() / RUNNER_DIR_NAME,
            default_name=socket.gethostname(),
            pairing_client=lambda url: RunnerPairingClient(url, version=__version__),
            session_factory=sessions,
            environment=LocalRunnerEnvironment(settings_repo, dispatcher),
        )

    @provide(scope=Scope.REQUEST)
    def get_update_uc(self, supervisor: IRemoteRunnerSupervisor) -> UpdateRemoteRunnerUC:
        return UpdateRemoteRunnerUC(supervisor)
