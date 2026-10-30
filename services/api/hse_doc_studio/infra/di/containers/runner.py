"""Контейнер процесса раннера: HTTP-клиент протокола, рабочие папки и обработчики без репозиториев и базы."""

from __future__ import annotations

import shutil
from collections.abc import AsyncIterator

import httpx
from dishka import AsyncContainer, Provider, Scope, make_async_container, provide

from hse_doc_studio import __version__
from hse_doc_studio.core.jobs.enums import JobKind
from hse_doc_studio.core.jobs.outputs import IJobOutputs
from hse_doc_studio.core.language_check import ILanguageCheckService
from hse_doc_studio.core.office import IOfficeConvertService
from hse_doc_studio.infra.checks.runner import CheckRunner
from hse_doc_studio.infra.compile.concurrency import CompileConcurrencyLimiter
from hse_doc_studio.infra.compile.docker_compile_executor import DockerCompileExecutor
from hse_doc_studio.infra.compile.docker_image_manager import DockerImageManager
from hse_doc_studio.infra.compile.host_path_resolver import HostPathResolver
from hse_doc_studio.infra.docker.cli import docker_binary
from hse_doc_studio.infra.jobs.embedded_runner import EmbeddedCompileRunner
from hse_doc_studio.infra.jobs.handler_registry import JobHandlerRegistry
from hse_doc_studio.infra.jobs.office_convert import OfficeConvertHandler
from hse_doc_studio.infra.jobs.outputs import LocalJobOutputs
from hse_doc_studio.infra.jobs.pack_handler import PackHandler
from hse_doc_studio.infra.runner.capabilities import detect_tags
from hse_doc_studio.infra.runner.client import RunnerClient
from hse_doc_studio.infra.runner.compile_executor import CompileJobExecutor, RoutingJobExecutor
from hse_doc_studio.infra.runner.config import RunnerConfig
from hse_doc_studio.infra.runner.handler_executor import HandlerJobExecutor, JobBlobFetcher
from hse_doc_studio.infra.runner.identity import RunnerIdentityStore
from hse_doc_studio.infra.runner.language_check import NoLanguageCheck
from hse_doc_studio.infra.runner.loop import RunnerLoop, RunnerLoopConfig
from hse_doc_studio.infra.runner.office import GotenbergConverter, NoOfficeConverter
from hse_doc_studio.infra.runner.settings import RunnerSettingsRepository
from hse_doc_studio.infra.runner.verify import EphemeralVerifyHandler
from hse_doc_studio.infra.runner.workspace import BlobCache, RunnerWorkspaces


class RunnerProvider(Provider):
    scope = Scope.APP

    def __init__(
        self,
        config: RunnerConfig,
        transport: httpx.AsyncBaseTransport | None = None,
        office_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__()
        self._config = config
        self._transport = transport
        self._office_transport = office_transport

    @provide
    def get_config(self) -> RunnerConfig:
        return self._config

    @provide
    async def get_client(self, config: RunnerConfig) -> AsyncIterator[RunnerClient]:
        store = RunnerIdentityStore(config.data_dir)
        client = RunnerClient(
            config.api_url,
            config.token.get_secret_value(),
            version=__version__,
            transport=self._transport,
            on_registered=lambda registered: store.save(config.api_url, registered),
        )
        if (identity := store.load(config.api_url)) is not None:
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
    def get_outputs(self) -> IJobOutputs:
        return LocalJobOutputs()

    @provide
    def get_handlers(self, config: RunnerConfig) -> JobHandlerRegistry:
        registry = JobHandlerRegistry()
        registry.register(JobKind.verify_detached, EphemeralVerifyHandler())
        registry.register(JobKind.pack_submission, PackHandler())
        if config.office_url:
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
        if not config.office_url:
            return NoOfficeConverter()
        return GotenbergConverter(config.office_url, config.office_timeout_s, self._office_transport)

    @provide
    def get_compile_runner(  # noqa: PLR0913
        self,
        config: RunnerConfig,
        office_convert: IOfficeConvertService,
        outputs: IJobOutputs,
    ) -> EmbeddedCompileRunner:
        # Те же исполнитель и тело сборки, что у встроенного раннера; отличаются настройки, изоляция и слоты.
        async def image() -> str:
            return config.tex_image

        lt_manager: ILanguageCheckService = NoLanguageCheck()
        return EmbeddedCompileRunner(
            executor=DockerCompileExecutor(
                HostPathResolver(),
                image=config.tex_image,
                cache_volume_name=config.tex_cache_volume,
                idle_timeout_s=config.tex_idle_timeout_s,
                limits=config.executor_limits(),
            ),
            image_manager=DockerImageManager(),
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
    def get_loop(
        self,
        config: RunnerConfig,
        client: RunnerClient,
        executor: HandlerJobExecutor,
        compile_executor: CompileJobExecutor,
    ) -> RunnerLoop:
        tags = config.explicit_tags() or detect_tags(
            office_url=config.office_url, tex_available=shutil.which(docker_binary()) is not None
        )
        return RunnerLoop(
            client,
            RoutingJobExecutor(compile_executor, executor),
            RunnerLoopConfig(
                name=config.name,
                version=__version__,
                tags=tags,
                concurrency=config.concurrency,
                poll_wait_s=config.poll_wait_s,
            ),
        )


def create_runner_container(
    config: RunnerConfig,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    office_transport: httpx.AsyncBaseTransport | None = None,
) -> AsyncContainer:
    """Транспорты подменяют сеть в тестах: api раннера и Gotenberg."""
    return make_async_container(RunnerProvider(config, transport, office_transport))
