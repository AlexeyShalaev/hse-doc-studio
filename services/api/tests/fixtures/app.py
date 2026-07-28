from __future__ import annotations

from pathlib import Path

import pytest_asyncio
from dishka import AsyncContainer, Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from fastapi import FastAPI, Request
from hse_doc_studio.api.config import settings as app_settings
from hse_doc_studio.api.routers.v1 import api_router
from hse_doc_studio.core.agent.protocols import IAgentProvider
from hse_doc_studio.core.ai_runtime import IHardwareProbe, IOllamaRegistry, IOllamaRuntime
from hse_doc_studio.core.compile.docker_diagnosis import DockerUnavailableReason
from hse_doc_studio.core.i18n import set_interface_language
from hse_doc_studio.core.repositories import (
    IAgentPersonaRepository,
    IAIProviderRepository,
    IChangeLogRepository,
    IChatRepository,
    ICompileRepository,
    IFileRepository,
    IFilesystemBrowser,
    IFormStateRepository,
    IPackSubmissionRepository,
    IProjectIndexRepository,
    IProjectRepository,
    ISettingsRepository,
    ISignatureRepository,
    ISigningIdentityRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.setup import (
    IDockerHealthProbe,
    IEnvironmentProbe,
    IMountProbe,
    ISelfContainerInfo,
    ISetupApplier,
    MountProbeResult,
    MountProbeStatus,
    SetupEnvironment,
)
from hse_doc_studio.core.update.entities import UpdateFeedProbe
from hse_doc_studio.core.update.repositories import (
    IReleaseNotesRepository,
    ISelfUpdateGateway,
    IUpdateCheckRepository,
    IUpdateFeedGateway,
)
from hse_doc_studio.infra.di.providers.services import DomainServiceProvider
from hse_doc_studio.infra.di.providers.use_cases import UseCaseProvider
from hse_doc_studio.infra.persistence.agent_persona import JsonAgentPersonaRepository
from hse_doc_studio.infra.persistence.ai_provider import JsonAIProviderRepository
from hse_doc_studio.infra.persistence.changelog import JsonChangeLogRepository
from hse_doc_studio.infra.persistence.chat import JsonChatRepository
from hse_doc_studio.infra.persistence.compile import JsonCompileRepository
from hse_doc_studio.infra.persistence.files import LocalFileRepository
from hse_doc_studio.infra.persistence.filesystem_browser import LocalFilesystemBrowser
from hse_doc_studio.infra.persistence.forms import JsonFormStateRepository
from hse_doc_studio.infra.persistence.project import JsonProjectRepository
from hse_doc_studio.infra.persistence.project_index import JsonProjectIndexRepository
from hse_doc_studio.infra.persistence.settings import JsonSettingsRepository
from hse_doc_studio.infra.persistence.signature import JsonSignatureRepository
from hse_doc_studio.infra.persistence.signing_identity import JsonSigningIdentityRepository
from hse_doc_studio.infra.persistence.submission import JsonPackSubmissionRepository
from hse_doc_studio.infra.persistence.update_check import JsonUpdateCheckRepository
from hse_doc_studio.infra.template.yaml_template_repository import YamlTemplateRepository
from hse_doc_studio.infra.update.release_notes_file import JsonReleaseNotesRepository
from httpx import ASGITransport, AsyncClient

# parents: [0]=fixtures/, [1]=tests/, [2]=service-root, [3]=services/, [4]=monorepo
_MONOREPO_ROOT = Path(__file__).resolve().parents[4]
_PACKS_DIR = _MONOREPO_ROOT / "packs"


class OfflineUpdateFeedGateway:
    """Default `IUpdateFeedGateway` in tests: nothing is reachable.

    The real gateway would call the GitHub Releases API, and no test may depend
    on the network. Tests that care about the answer pass their own fake via
    `create_test_container(update_feed=...)`; the real gateway's HTTP and parsing
    are covered in tests/unit/infra/update/test_feed.py.
    """

    async def probe(self) -> UpdateFeedProbe:
        return UpdateFeedProbe(reason="offline in tests")


class UnsupportedSelfUpdateGateway:
    """Default `ISelfUpdateGateway` in tests: this deployment can't replace itself.

    Matches reality — the suite doesn't run inside the all-in-one image — and
    guarantees no test can spawn a real updater container. Tests that exercise
    switching versions pass their own fake via
    `create_test_container(self_updater=...)`.
    """

    def __init__(self, *, can_update: bool = False, busy: bool = False, starts: bool = True) -> None:
        self.can_update = can_update
        self.busy = busy
        self.starts = starts
        self.started_versions: list[str] = []

    async def can_self_update(self) -> bool:
        return self.can_update

    def target_image(self, version: str) -> str:
        return f"ghcr.io/test/hse-doc-studio:{version}"

    def is_busy(self) -> bool:
        return self.busy

    async def start(self, target_version: str) -> bool:
        self.started_versions.append(target_version)
        return self.starts


class OfflineDockerHealthProbe:
    """Default `IDockerHealthProbe` в тестах: демон не отвечает.

    Настоящая проба вызывает `docker version` подпроцессом, поэтому её ответ
    зависел бы от того, поднят ли демон на машине, где идёт прогон. Тесты, которым
    нужен другой ответ, передают свой экземпляр через
    `create_test_container(docker_health=...)`.
    """

    def __init__(self, *, alive: bool = False, reason: DockerUnavailableReason | None = None) -> None:
        self.alive = alive
        self.reason = reason
        self.calls = 0

    async def check(self) -> tuple[bool, DockerUnavailableReason | None]:
        self.calls += 1
        return self.alive, self.reason


class UnavailableMountProbe:
    """Default `IMountProbe` в тестах: проверить папку нечем.

    Настоящая проба поднимает одноразовый контейнер с бинд-маунтом проверяемого
    пути — в тестах докер не запускается ни при каких условиях. Запоминает
    запрошенные пути: мастер настройки обязан отдать демону ровно то, что ввёл
    пользователь.
    """

    def __init__(self, result: MountProbeResult | None = None) -> None:
        self.result = result if result is not None else MountProbeResult(status=MountProbeStatus.docker_unavailable)
        self.probed: list[str] = []

    async def probe(self, host_path: str) -> MountProbeResult:
        self.probed.append(host_path)
        return self.result


class BlankEnvironmentProbe:
    """Default `IEnvironmentProbe` в тестах: про машину ничего не известно.

    Настоящий зонд зовёт `docker info` и `docker inspect` подпроцессами, то есть
    его ответ зависел бы от машины, на которой идёт прогон. Экран настройки обязан
    переживать пустой ответ — здесь это и проверяется по умолчанию.
    """

    def __init__(self, environment: SetupEnvironment | None = None) -> None:
        self.environment = environment if environment is not None else SetupEnvironment(engine=None, container=None)

    async def describe(self) -> SetupEnvironment:
        return self.environment


class PlainRunSelfInfo:
    """Default `ISelfContainerInfo` в тестах: контейнер поднят обычным `docker run`.

    Настоящая реализация читает метки собственного контейнера через докера.
    Тест, которому нужна compose-установка, передаёт свой экземпляр с именем
    проекта в `create_test_container(self_info=...)`.
    """

    def __init__(self, project: str | None = None) -> None:
        self.project = project

    async def compose_project(self) -> str | None:
        return self.project


class RecordingSetupApplier:
    """Default `ISetupApplier` в тестах: пересоздание контейнера только записывается.

    Настоящий применитель пересоздаёт контейнер приложения, то есть убивает
    процесс, из которого его позвали, — в тестах он обязан оставаться фейком.
    Список путей заодно доказывает, что до применения дошло ровно то, что ввёл
    пользователь, и что при отказе применение не начиналось вовсе.
    """

    def __init__(self, *, spawns: bool = True) -> None:
        self.spawns = spawns
        self.applied_paths: list[str] = []
        # Каталог шрифтов, если пользователь поправил автоопределение.
        self.applied_font_paths: list[str | None] = []

    async def apply(
        self,
        *,
        data_host_path: str,
        fonts_host_path: str | None = None,
        prefetch_tex_image: bool = True,
    ) -> bool:
        self.applied_paths.append(data_host_path)
        self.applied_font_paths.append(fonts_host_path)
        return self.spawns


def create_test_container(  # noqa: C901 — one @provide per repo; flat by design
    data_dir: Path,
    *,
    agent_provider: IAgentProvider | None = None,
    hardware_probe: IHardwareProbe | None = None,
    ollama_registry: IOllamaRegistry | None = None,
    ollama_runtime: IOllamaRuntime | None = None,
    update_feed: IUpdateFeedGateway | None = None,
    self_updater: ISelfUpdateGateway | None = None,
    docker_health: IDockerHealthProbe | None = None,
    self_info: ISelfContainerInfo | None = None,
    environment: IEnvironmentProbe | None = None,
    mount_probe: IMountProbe | None = None,
    setup_applier: ISetupApplier | None = None,
) -> AsyncContainer:
    # A handful of providers (font store, office-editor JWT secret, compile host
    # mounts, the agent loop's rules file) read the module-level `settings.data_dir`
    # singleton directly instead of taking data_dir via DI — repoint it at this
    # test's tmp_path so those code paths never touch the real, process-wide
    # data_dir (which on a dev machine holds real installed fonts etc.). Safe to
    # mutate unconditionally: each test calls this with its own fresh tmp_path
    # right before use, and tests run sequentially within one pytest process.
    app_settings.data_dir = data_dir
    app_settings.host_data_dir = None

    class TestRepositoryProvider(Provider):
        scope = Scope.APP

        def __init__(self, data_dir: Path) -> None:
            super().__init__()
            self._data_dir = data_dir

        @provide
        def get_project_repo(self) -> IProjectRepository:
            return JsonProjectRepository()

        @provide
        def get_project_index_repo(self) -> IProjectIndexRepository:
            return JsonProjectIndexRepository(self._data_dir)

        @provide
        def get_template_repo(self) -> ITemplateRepository:
            repo = YamlTemplateRepository(_PACKS_DIR)
            repo.load()
            return repo

        @provide
        def get_compile_repo(self) -> ICompileRepository:
            return JsonCompileRepository()

        @provide
        def get_signature_repo(self) -> ISignatureRepository:
            return JsonSignatureRepository()

        @provide
        def get_form_state_repo(self) -> IFormStateRepository:
            return JsonFormStateRepository()

        @provide
        def get_changelog_repo(self) -> IChangeLogRepository:
            return JsonChangeLogRepository()

        @provide
        def get_pack_submission_repo(self) -> IPackSubmissionRepository:
            return JsonPackSubmissionRepository()

        @provide
        def get_file_repo(self) -> IFileRepository:
            return LocalFileRepository()

        @provide
        def get_filesystem_browser(self) -> IFilesystemBrowser:
            return LocalFilesystemBrowser()

        @provide
        def get_settings_repo(self) -> ISettingsRepository:
            return JsonSettingsRepository(self._data_dir)

        @provide
        def get_ai_provider_repo(self) -> IAIProviderRepository:
            return JsonAIProviderRepository(self._data_dir)

        @provide
        def get_agent_persona_repo(self) -> IAgentPersonaRepository:
            return JsonAgentPersonaRepository(self._data_dir)

        @provide
        def get_chat_repo(self) -> IChatRepository:
            return JsonChatRepository()

        @provide
        def get_signing_identity_repo(self) -> ISigningIdentityRepository:
            return JsonSigningIdentityRepository(self._data_dir)

        @provide
        def get_update_check_repo(self) -> IUpdateCheckRepository:
            return JsonUpdateCheckRepository(self._data_dir)

        @provide
        def get_release_notes_repo(self) -> IReleaseNotesRepository:
            # Настоящий release-notes.json репозитория: тесты проверяют и то, что
            # реальные данные доезжают до API, а не только форму ответа.
            return JsonReleaseNotesRepository(app_settings.release_notes_file)

        @provide
        def get_update_feed_gateway(self) -> IUpdateFeedGateway:
            return update_feed if update_feed is not None else OfflineUpdateFeedGateway()

        @provide
        def get_self_update_gateway(self) -> ISelfUpdateGateway:
            return self_updater if self_updater is not None else UnsupportedSelfUpdateGateway()

        # Мастер первоначальной настройки — единственное место продукта, где вся
        # тройка зависимостей разговаривает с докером напрямую (проба демона,
        # проба папки хоста, пересоздание собственного контейнера). В тестах она
        # подменяется целиком: ни один прогон не имеет права ни спросить демона,
        # ни тем более пересоздать что-либо.

        @provide
        def get_docker_health_probe(self) -> IDockerHealthProbe:
            return docker_health if docker_health is not None else OfflineDockerHealthProbe()

        @provide
        def get_environment_probe(self) -> IEnvironmentProbe:
            return environment if environment is not None else BlankEnvironmentProbe()

        @provide
        def get_self_container_info(self) -> ISelfContainerInfo:
            return self_info if self_info is not None else PlainRunSelfInfo()

        @provide
        def get_mount_probe(self) -> IMountProbe:
            return mount_probe if mount_probe is not None else UnavailableMountProbe()

        @provide
        def get_setup_applier(self) -> ISetupApplier:
            return setup_applier if setup_applier is not None else RecordingSetupApplier()

    providers: list[Provider] = [
        TestRepositoryProvider(data_dir),
        DomainServiceProvider(),
        UseCaseProvider(),
        FastapiProvider(),
    ]
    if agent_provider is not None:
        # Real turns go through SdkAgentProvider (real OpenAI/Anthropic SDK calls) —
        # tests exercising the chat/agent HTTP surface override it with a fake so no
        # real network call happens, while everything else in the chain (router, DI,
        # use cases, JSON persistence) still runs for real.
        class _AgentProviderOverride(Provider):
            scope = Scope.APP

            @provide(override=True)
            def get_agent_provider(self) -> IAgentProvider:
                return agent_provider

        providers.append(_AgentProviderOverride())

    if hardware_probe is not None:
        # Real detection shells out to nvidia-smi/psutil — tests exercising the
        # ai-runtime HTTP surface override it with a fake so hardware readings
        # stay deterministic and never touch the actual host.
        class _HardwareProbeOverride(Provider):
            scope = Scope.APP

            @provide(override=True)
            def get_hardware_probe(self) -> IHardwareProbe:
                return hardware_probe

        providers.append(_HardwareProbeOverride())

    if ollama_registry is not None:
        # Real registry search scrapes ollama.com over the network — override
        # with a fake canned result set for tests.
        class _OllamaRegistryOverride(Provider):
            scope = Scope.APP

            @provide(override=True)
            def get_ollama_registry(self) -> IOllamaRegistry:
                return ollama_registry

        providers.append(_OllamaRegistryOverride())

    if ollama_runtime is not None:
        # Real runtime manages a Docker container and speaks to a real Ollama
        # HTTP API — tests override it with an in-memory fake. Downstream
        # dependents (IPullModelJobs' real PullModelJobManager) resolve against
        # this fake automatically since they depend on IOllamaRuntime via DI.
        class _OllamaRuntimeOverride(Provider):
            scope = Scope.APP

            @provide(override=True)
            def get_ollama_runtime(self) -> IOllamaRuntime:
                return ollama_runtime

        providers.append(_OllamaRuntimeOverride())

    return make_async_container(*providers)


def create_test_app(container: AsyncContainer) -> FastAPI:
    """Bare app around the real router — mirrors `api/entrypoint.create_app()`.

    The interface-language middleware is part of the HTTP contract (endpoints that
    answer in the user's language read it via `current_interface_language()`), so
    it belongs here too; without it a test could never exercise a localized
    response. CORS and the startup hooks stay out — neither affects a test client.
    """
    app = FastAPI()

    @app.middleware("http")
    async def _interface_language_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        set_interface_language(request.headers.get("X-Interface-Language"))
        return await call_next(request)

    app.include_router(api_router)
    setup_dishka(container, app)
    return app


@pytest_asyncio.fixture
async def test_app(tmp_path: Path) -> AsyncClient:
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    container = create_test_container(data_dir)
    app = create_test_app(container)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    await container.close()
