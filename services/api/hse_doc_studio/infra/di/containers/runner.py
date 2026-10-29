"""Контейнер процесса раннера: HTTP-клиент протокола, рабочие папки и обработчики без репозиториев и базы."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
from dishka import AsyncContainer, Provider, Scope, make_async_container, provide

from hse_doc_studio import __version__
from hse_doc_studio.core.jobs.enums import JobKind
from hse_doc_studio.core.jobs.outputs import IJobOutputs
from hse_doc_studio.infra.jobs.handler_registry import JobHandlerRegistry
from hse_doc_studio.infra.jobs.office_convert import OfficeConvertHandler
from hse_doc_studio.infra.jobs.outputs import LocalJobOutputs
from hse_doc_studio.infra.jobs.pack_handler import PackHandler
from hse_doc_studio.infra.runner.capabilities import detect_tags
from hse_doc_studio.infra.runner.client import RunnerClient
from hse_doc_studio.infra.runner.config import RunnerConfig
from hse_doc_studio.infra.runner.handler_executor import HandlerJobExecutor, JobBlobFetcher
from hse_doc_studio.infra.runner.loop import RunnerLoop, RunnerLoopConfig
from hse_doc_studio.infra.runner.office import GotenbergConverter
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
        client = RunnerClient(
            config.api_url, config.token.get_secret_value(), version=__version__, transport=self._transport
        )
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
        return RunnerWorkspaces(config.data_dir, cache)

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
    def get_loop(self, config: RunnerConfig, client: RunnerClient, executor: HandlerJobExecutor) -> RunnerLoop:
        tags = config.explicit_tags() or detect_tags(office_url=config.office_url)
        return RunnerLoop(
            client,
            executor,
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
