"""Облачные сборки локальной Студии: только локальный контейнер, на сервере этих зависимостей нет."""

from __future__ import annotations

import socket

from dishka import AnyOf, Provider, Scope, provide

from hse_doc_studio import __version__
from hse_doc_studio.api.config import settings
from hse_doc_studio.core.fonts.repositories import IFontStore, ISystemFontProvider
from hse_doc_studio.core.jobs.protocols import IJobDispatcher
from hse_doc_studio.core.paths import PathMapping
from hse_doc_studio.core.remote_runner import IRemoteRunnerSettingsStore, IRemoteRunnerSupervisor
from hse_doc_studio.core.repositories import IAIProviderRepository, ISettingsRepository
from hse_doc_studio.infra.compile.host_path_resolver import HostPathResolver
from hse_doc_studio.infra.office.convert_manager import OfficeConvertManager
from hse_doc_studio.infra.remote_runner.ai_endpoints import LocalAiEndpointResolver
from hse_doc_studio.infra.remote_runner.environment import LocalRunnerEnvironment
from hse_doc_studio.infra.remote_runner.runner_session import SessionFonts, cloud_cache_volume, runner_session_factory
from hse_doc_studio.infra.remote_runner.settings_store import JsonRemoteRunnerSettingsStore
from hse_doc_studio.infra.remote_runner.supervisor import RUNNER_DIR_NAME, RemoteRunnerSupervisor
from hse_doc_studio.infra.runner.pairing_client import RunnerPairingClient
from hse_doc_studio.use_cases.fonts.adopt_host_fonts import AdoptHostFontsUC
from hse_doc_studio.use_cases.remote_runner.update_remote_runner import UpdateRemoteRunnerUC


def _session_fonts(system_fonts: ISystemFontProvider, font_store: IFontStore) -> SessionFonts:
    """Папка шрифтов Студии для облачных сборок: путь на хосте считается так же, как для локальных сборок."""
    data_dir = settings.data_dir.expanduser()
    host_data = settings.host_data_dir or str(data_dir)
    adopt = AdoptHostFontsUC(system_fonts, font_store)
    return SessionFonts(
        folder=data_dir / settings.fonts.dir_name,
        host_folder=host_data.replace("\\", "/").rstrip("/") + "/" + settings.fonts.dir_name,
        mount_target=settings.fonts.container_mount,
        ensure=adopt.execute,
    )


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
        providers: IAIProviderRepository,
        office: OfficeConvertManager,
        system_fonts: ISystemFontProvider,
        font_store: IFontStore,
    ) -> AnyOf[RemoteRunnerSupervisor, IRemoteRunnerSupervisor]:
        # То же соответствие путей, что у локальных сборок (в образе all-in-one docker монтирует папку облачной
        # сборки по пути хоста), но свой том кэша TeX: облачные документы не делят HOME с локальными проектами.
        sessions = runner_session_factory(
            cache_volume=cloud_cache_volume(settings.compile.cache_volume_name),
            host_paths=HostPathResolver(mapping),
            office=office,
            fonts=_session_fonts(system_fonts, font_store),
        )
        return RemoteRunnerSupervisor(
            store,
            runner_dir=settings.data_dir.expanduser() / RUNNER_DIR_NAME,
            default_name=socket.gethostname(),
            pairing_client=lambda url: RunnerPairingClient(url, version=__version__),
            session_factory=sessions,
            environment=LocalRunnerEnvironment(settings_repo, dispatcher),
            ai_endpoints=LocalAiEndpointResolver(providers),
        )

    @provide(scope=Scope.REQUEST)
    def get_update_uc(
        self, supervisor: IRemoteRunnerSupervisor, providers: IAIProviderRepository
    ) -> UpdateRemoteRunnerUC:
        return UpdateRemoteRunnerUC(supervisor, providers)
