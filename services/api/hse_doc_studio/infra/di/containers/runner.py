"""Контейнер процесса раннера: HTTP-клиент протокола, рабочие папки и обработчики без репозиториев и базы."""

from __future__ import annotations

import logging
import os
import shutil
from collections.abc import AsyncIterator, Callable, Sequence
from functools import partial
from urllib.parse import urlsplit, urlunsplit

import httpx
from dishka import AsyncContainer, Provider, Scope, make_async_container, provide

from hse_doc_studio import __version__
from hse_doc_studio.core.jobs.enums import JobKind
from hse_doc_studio.core.jobs.outputs import IJobOutputs
from hse_doc_studio.core.jobs.relay import RELAY_TAG
from hse_doc_studio.core.jobs.runners import DeclaredAiEndpoint, RunnerHostKind
from hse_doc_studio.core.language_check import ILanguageCheckService
from hse_doc_studio.core.office import IOfficeConvertService
from hse_doc_studio.infra.checks.runner import CheckRunner
from hse_doc_studio.infra.compile.backend import BuildBackend
from hse_doc_studio.infra.compile.concurrency import CompileConcurrencyLimiter
from hse_doc_studio.infra.compile.docker_compile_executor import DockerCompileExecutor, sweep_build_containers
from hse_doc_studio.infra.compile.docker_image_manager import DockerImageManager
from hse_doc_studio.infra.compile.host_path_resolver import HostPathResolver, PathNotInContainerMountError
from hse_doc_studio.infra.compile.k8s.api import IKubeApi, KubeApiError
from hse_doc_studio.infra.compile.k8s.client import KubernetesApiClient, TokenSource
from hse_doc_studio.infra.compile.k8s.config import instance_label
from hse_doc_studio.infra.compile.k8s.executor import KubernetesBuildEnvironment, KubernetesTexExecutor
from hse_doc_studio.infra.docker.cli import docker_binary
from hse_doc_studio.infra.jobs.embedded_runner import EmbeddedCompileRunner
from hse_doc_studio.infra.jobs.handler_registry import JobHandlerRegistry
from hse_doc_studio.infra.jobs.office_convert import OfficeConvertHandler
from hse_doc_studio.infra.jobs.outputs import LocalJobOutputs
from hse_doc_studio.infra.jobs.pack_handler import PackHandler
from hse_doc_studio.infra.runner.capabilities import detect_tags
from hse_doc_studio.infra.runner.client import RunnerClient
from hse_doc_studio.infra.runner.compile_executor import CompileJobExecutor, RoutingJobExecutor
from hse_doc_studio.infra.runner.config import BuildExecutorKind, RunnerConfig
from hse_doc_studio.infra.runner.deployment import collect_deployment
from hse_doc_studio.infra.runner.disk import RunnerDiskService, build_runner_disk_service
from hse_doc_studio.infra.runner.handler_executor import HandlerJobExecutor, JobBlobFetcher
from hse_doc_studio.infra.runner.identity import RunnerIdentityStore
from hse_doc_studio.infra.runner.language_check import NoLanguageCheck
from hse_doc_studio.infra.runner.loop import IRunnerLoopObserver, RunnerLoop, RunnerLoopConfig
from hse_doc_studio.infra.runner.office import GotenbergConverter, NoOfficeConverter
from hse_doc_studio.infra.runner.relay_executor import AiEndpoint, AiRelayExecutor
from hse_doc_studio.infra.runner.settings import RunnerSettingsRepository
from hse_doc_studio.infra.runner.verify import EphemeralVerifyHandler
from hse_doc_studio.infra.runner.workspace import BlobCache, RunnerWorkspaces

logger = logging.getLogger(__name__)


class RunnerConfigError(ValueError):
    """Раннеру нечем представиться серверу: нет ни токена регистрации, ни токена раннера, ни сохранённой личности."""


class RunnerProvider(Provider):
    scope = Scope.APP

    def __init__(  # noqa: PLR0913
        self,
        config: RunnerConfig,
        transport: httpx.AsyncBaseTransport | None = None,
        office_transport: httpx.AsyncBaseTransport | None = None,
        host_paths: HostPathResolver | None = None,
        *,
        ai_endpoints: Sequence[AiEndpoint] | None = None,
        observer: IRunnerLoopObserver | None = None,
        gate: Callable[[], bool] | None = None,
        ai_transport: httpx.AsyncBaseTransport | None = None,
        kube_api: IKubeApi | None = None,
        office_converter: IOfficeConvertService | None = None,
    ) -> None:
        super().__init__()
        self._office_converter = office_converter
        self._kube_api = kube_api
        self._config = config
        self._transport = transport
        self._office_transport = office_transport
        self._host_paths = host_paths
        self._ai_endpoints = ai_endpoints
        self._observer = observer
        self._gate = gate
        self._ai_transport = ai_transport

    @provide
    def get_config(self) -> RunnerConfig:
        return self._config

    @provide
    async def get_client(self, config: RunnerConfig) -> AsyncIterator[RunnerClient]:
        store = RunnerIdentityStore(config.data_dir)
        identity = store.load(config.api_url)
        if config.runner_token is None and config.token is None and identity is None:
            raise RunnerConfigError(
                "нужен HSE_RUNNER__TOKEN (токен регистрации) или HSE_RUNNER__RUNNER_TOKEN (токен раннера)"
            )
        client = RunnerClient(
            config.api_url,
            config.token.get_secret_value() if config.token is not None else "",
            version=__version__,
            transport=self._transport,
            on_registered=lambda registered: store.save(config.api_url, registered),
        )
        if config.runner_token is not None:
            # Токен после смены на сайте важнее сохранённой личности: старый уже не годится.
            client.restore(identity.runner_id if identity is not None else "", config.runner_token.get_secret_value())
        elif identity is not None:
            client.restore(identity.runner_id, identity.runner_token)
        yield client
        await client.aclose()

    @provide
    def get_fetcher(self, client: RunnerClient) -> JobBlobFetcher:
        return JobBlobFetcher(client)

    @provide
    def get_cache(self, config: RunnerConfig, fetcher: JobBlobFetcher) -> BlobCache:
        return BlobCache(config.data_dir, fetcher)

    @provide
    def get_workspaces(self, config: RunnerConfig, cache: BlobCache) -> RunnerWorkspaces:
        return RunnerWorkspaces(config.data_dir, cache, config.workspaces_max_bytes)

    @provide
    def get_disk_service(
        self, config: RunnerConfig, cache: BlobCache, workspaces: RunnerWorkspaces
    ) -> RunnerDiskService:
        # Диск раннера (docs/design/storage-cleanup.md, 6.3): Docker-часть только у консольного раннера с docker.
        return build_runner_disk_service(config, cache, workspaces)

    @provide
    def get_outputs(self) -> IJobOutputs:
        return LocalJobOutputs()

    @provide
    def get_handlers(self, config: RunnerConfig) -> JobHandlerRegistry:
        registry = JobHandlerRegistry()
        registry.register(JobKind.verify_detached, EphemeralVerifyHandler())
        registry.register(JobKind.pack_submission, PackHandler())
        if self._office_converter is not None:
            registry.register(JobKind.office_convert, OfficeConvertHandler(self._office_converter))
        elif config.office_url:
            registry.register(
                JobKind.office_convert,
                OfficeConvertHandler(
                    GotenbergConverter(config.office_url, config.office_timeout_s, self._office_transport)
                ),
            )
        return registry

    @provide
    def get_executor(  # noqa: PLR0913
        self,
        config: RunnerConfig,
        workspaces: RunnerWorkspaces,
        cache: BlobCache,
        fetcher: JobBlobFetcher,
        handlers: JobHandlerRegistry,
        outputs: IJobOutputs,
    ) -> HandlerJobExecutor:
        return HandlerJobExecutor(
            workspaces=workspaces,
            cache=cache,
            fetcher=fetcher,
            handlers=handlers,
            outputs=outputs,
            cache_max_bytes=config.cache_max_bytes,
        )

    @provide
    def get_office_converter(self, config: RunnerConfig) -> IOfficeConvertService:
        if self._office_converter is not None:
            return self._office_converter
        if not config.office_url:
            return NoOfficeConverter()
        return GotenbergConverter(config.office_url, config.office_timeout_s, self._office_transport)

    @provide
    async def get_build_backend(self, config: RunnerConfig) -> AsyncIterator[BuildBackend]:
        if config.executor is BuildExecutorKind.docker:
            resolver = self._host_paths or HostPathResolver()
            yield BuildBackend(
                executor=DockerCompileExecutor(
                    resolver,
                    image=config.tex_image,
                    cache_volume_name=config.tex_cache_volume,
                    idle_timeout_s=config.tex_idle_timeout_s,
                    limits=config.executor_limits(),
                    fonts_dir=config.fonts_dir,
                    fonts_host_dir=_fonts_host_dir(config, resolver),
                    fonts_mount_target=config.fonts_mount_target,
                ),
                environment=DockerImageManager(),
                sweep=sweep_build_containers,
                tex_available=shutil.which(docker_binary()) is not None,
                name="docker",
            )
            return
        api = self._kube_api
        if api is None:
            try:
                api = KubernetesApiClient(
                    config.k8s.resolved_api_url(), TokenSource(config.k8s.token_file), config.k8s.ca_file
                )
            except KubeApiError as exc:
                raise RunnerConfigError(str(exc)) from exc
        executor = KubernetesTexExecutor(
            api,
            config.k8s,
            image=config.tex_image,
            instance=instance_label(config.k8s.owner_pod_uid, config.name),
            idle_timeout_s=config.tex_idle_timeout_s,
        )
        logger.info("build executor: kubernetes, namespace %s", executor.namespace)
        yield BuildBackend(
            executor=executor,
            environment=KubernetesBuildEnvironment(),
            sweep=executor.sweep,
            tex_available=True,
            name="kubernetes",
        )
        await api.aclose()

    @provide
    def get_compile_runner(  # noqa: PLR0913
        self,
        config: RunnerConfig,
        office_convert: IOfficeConvertService,
        outputs: IJobOutputs,
        backend: BuildBackend,
    ) -> EmbeddedCompileRunner:
        # Те же исполнитель и тело сборки, что у встроенного раннера; отличаются настройки, изоляция и слоты.
        async def image() -> str:
            return config.tex_image

        lt_manager: ILanguageCheckService = NoLanguageCheck()
        return EmbeddedCompileRunner(
            executor=backend.executor,
            image_manager=backend.environment,
            office_convert=office_convert,
            check_runner=CheckRunner(lt_manager=lt_manager, lt_client=httpx.Client()),
            lt_manager=lt_manager,
            settings_repo=RunnerSettingsRepository(config),
            capacity_probe=None,
            limiter=CompileConcurrencyLimiter(),
            outputs=outputs,
            resolve_image=image,
            resolve_lt_image=image,
            resolve_office_image=image,
        )

    @provide
    def get_compile_executor(  # noqa: PLR0913
        self,
        config: RunnerConfig,
        workspaces: RunnerWorkspaces,
        cache: BlobCache,
        fetcher: JobBlobFetcher,
        runner: EmbeddedCompileRunner,
    ) -> CompileJobExecutor:
        return CompileJobExecutor(
            workspaces=workspaces, cache=cache, fetcher=fetcher, runner=runner, cache_max_bytes=config.cache_max_bytes
        )

    @provide
    def get_relay_executor(self, config: RunnerConfig, client: RunnerClient) -> AiRelayExecutor:
        endpoints = self._ai_endpoints if self._ai_endpoints is not None else endpoints_of(config)
        return AiRelayExecutor(
            client, endpoints, max_response_bytes=config.relay_max_response_bytes, transport=self._ai_transport
        )

    @provide
    def get_loop(
        self,
        config: RunnerConfig,
        client: RunnerClient,
        executor: HandlerJobExecutor,
        compile_executor: CompileJobExecutor,
        relay: AiRelayExecutor,
        backend: BuildBackend,
    ) -> RunnerLoop:
        endpoints = self._ai_endpoints if self._ai_endpoints is not None else endpoints_of(config)
        declared = tuple(DeclaredAiEndpoint(endpoint.name, endpoint.flavor) for endpoint in endpoints)
        relay_on = bool(declared) and config.ai_concurrency > 0
        tags = config.explicit_tags() or detect_tags(
            office_url=config.office_url,
            tex_available=backend.tex_available,
            ai_relay=relay_on,
        )
        if declared:
            # Адреса объявлены без ключей: имена и вид, URL остаётся у раннера.
            logger.info("ai endpoints: %s", ", ".join(f"{e.name}={_loggable_url(e.base_url)}" for e in endpoints))
        return RunnerLoop(
            client,
            RoutingJobExecutor(compile_executor, executor, relay),
            RunnerLoopConfig(
                name=config.name,
                version=__version__,
                tags=tags - {RELAY_TAG} if not relay_on else tags | {RELAY_TAG},
                concurrency=config.concurrency,
                poll_wait_s=config.poll_wait_s,
                # Слоты ИИ остаются и без адресов: Студия может объявить их позже через `reannounce`,
                # а без согласованной возможности `ai_slots` цикл их не использует.
                ai_concurrency=config.ai_concurrency,
                host_kind=config.host_kind,
                ai_endpoints=declared,
                gate=self._gate,
                # Отчёт о развёртывании для админки шлёт только консольный раннер: у локальной Студии он ни к чему.
                deployment=partial(collect_deployment, config) if config.host_kind is RunnerHostKind.cli else None,
            ),
            observer=self._observer,
        )


def _fonts_host_dir(config: RunnerConfig, resolver: HostPathResolver) -> str | None:
    """Путь папки шрифтов для `docker -v`: заданный явно или переведённый соответствием путей хоста."""
    if config.fonts_dir is None:
        return None
    if config.fonts_host_dir:
        return config.fonts_host_dir.replace("\\", "/").rstrip("/")
    try:
        return resolver.to_host(config.fonts_dir)
    except PathNotInContainerMountError as exc:
        logger.warning("fonts folder is not mapped to a host path, fonts are not mounted: %s", exc)
        return None


def endpoints_of(config: RunnerConfig) -> tuple[AiEndpoint, ...]:
    """ИИ-адреса из окружения раннера; ключ читается из его переменной в момент запроса."""
    return tuple(
        AiEndpoint(
            name=entry.name,
            base_url=entry.url,
            flavor=entry.flavor,
            api_key=partial(_env_key, entry.key_env),
        )
        for entry in config.ai_endpoints
    )


def _loggable_url(url: str) -> str:
    """Адрес без логина и пароля: адреса из локальной Студии конфиг раннера не проверял."""
    parts = urlsplit(url)
    if parts.username is None and parts.password is None:
        return url
    host = parts.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    netloc = f"***@{host}:{parts.port}" if parts.port else f"***@{host}"
    return urlunsplit(parts._replace(netloc=netloc))


def _env_key(name: str | None) -> str | None:
    return os.environ.get(name) if name else None


def create_runner_container(  # noqa: PLR0913
    config: RunnerConfig,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    office_transport: httpx.AsyncBaseTransport | None = None,
    host_paths: HostPathResolver | None = None,
    ai_endpoints: Sequence[AiEndpoint] | None = None,
    observer: IRunnerLoopObserver | None = None,
    gate: Callable[[], bool] | None = None,
    ai_transport: httpx.AsyncBaseTransport | None = None,
    kube_api: IKubeApi | None = None,
    office_converter: IOfficeConvertService | None = None,
) -> AsyncContainer:
    """Транспорты подменяют сеть в тестах: api раннера, Gotenberg и модели.

    Локальная Студия передаёт свои ИИ-адреса (`ai_endpoints`, `None` значит из окружения раннера),
    наблюдатель состояния и шлюз «уступать локальным сборкам». `host_paths` нужен раннеру внутри
    контейнера Студии: docker монтирует папку сборки по пути хоста, а не по пути внутри контейнера.
    `kube_api` подменяет Kubernetes API исполнителя kubernetes в тестах. `office_converter` даёт Студии свой
    конвертер вместо адреса Gotenberg из конфига (управляемая служба Студии).
    """
    return make_async_container(
        RunnerProvider(
            config,
            transport,
            office_transport,
            host_paths,
            ai_endpoints=ai_endpoints,
            observer=observer,
            gate=gate,
            ai_transport=ai_transport,
            kube_api=kube_api,
            office_converter=office_converter,
        )
    )
