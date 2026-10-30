"""Облачные сборки локальной Студии: только локальный контейнер, на сервере этих зависимостей нет."""

from __future__ import annotations

import socket

from dishka import AnyOf, Provider, Scope, provide

from hse_doc_studio import __version__
from hse_doc_studio.api.config import settings
from hse_doc_studio.core.remote_runner import IRemoteRunnerSettingsStore, IRemoteRunnerSupervisor
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
        self, store: IRemoteRunnerSettingsStore
    ) -> AnyOf[RemoteRunnerSupervisor, IRemoteRunnerSupervisor]:
        return RemoteRunnerSupervisor(
            store,
            runner_dir=settings.data_dir.expanduser() / RUNNER_DIR_NAME,
            default_name=socket.gethostname(),
            pairing_client=lambda url: RunnerPairingClient(url, version=__version__),
            session_factory=None,
        )

    @provide(scope=Scope.REQUEST)
    def get_update_uc(self, supervisor: IRemoteRunnerSupervisor) -> UpdateRemoteRunnerUC:
        return UpdateRemoteRunnerUC(supervisor)
