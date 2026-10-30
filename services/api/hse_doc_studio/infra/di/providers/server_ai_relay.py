"""Ретрансляция ИИ через личный раннер: каналы и тела запросов в памяти api, клиент и ручки раннера."""

from __future__ import annotations

from dishka import Provider, Scope, provide

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.agent.protocols import IAgentProvider
from hse_doc_studio.core.ai import IAIModelLister
from hse_doc_studio.core.jobs.queue import IJobQueue
from hse_doc_studio.core.jobs.relay import IRelayHub
from hse_doc_studio.core.jobs.routing import IPersonalRunnerSettings
from hse_doc_studio.core.jobs.runners import IRunnerRepository
from hse_doc_studio.infra.ai.agent.sdk_agent_provider import SdkAgentProvider
from hse_doc_studio.infra.ai.sdk_model_lister import SdkAIModelLister
from hse_doc_studio.infra.jobs.relay_hub import RelayHub
from hse_doc_studio.use_cases.ai_providers.relay_info import ProviderRelayDescriber
from hse_doc_studio.use_cases.ai_relay.client import AiRelayClient, RelayLimits
from hse_doc_studio.use_cases.ai_relay.request_store import RelayRequestStore, RelayTerminalCleanup
from hse_doc_studio.use_cases.ai_relay.runner_side import RelayRunnerService
from hse_doc_studio.use_cases.jobs.queue_service import JobQueueService
from hse_doc_studio.use_cases.jobs.runner_io import RunnerJobIoService
from hse_doc_studio.use_cases.jobs.terminal import JobTerminalBroadcaster
from hse_doc_studio.use_cases.jobs.wakeup import JobWakeup


def relay_limits() -> RelayLimits:
    jobs = settings.jobs
    return RelayLimits(
        pickup_s=jobs.relay_pickup_s,
        max_request_bytes=jobs.relay_max_request_bytes,
        max_response_bytes=jobs.relay_max_response_bytes,
        max_pending_per_user=jobs.relay_max_pending_per_user,
        max_duration_s=jobs.relay_max_duration_s,
    )


class ServerAiRelayProvider(Provider):
    """Одна реплика api: канал живёт там, где поставлена задача (как `JobWakeup`)."""

    scope = Scope.APP

    @provide
    def get_relay_hub(self, terminal: JobTerminalBroadcaster) -> RelayHub:
        hub = RelayHub()
        # Задача стала терминальной без `end` (потеря раннера, отмена, таймаут): поток рвётся с её кодом.
        terminal.add(hub)
        return hub

    @provide
    def get_relay_hub_port(self, hub: RelayHub) -> IRelayHub:
        return hub

    @provide
    def get_relay_request_store(self, hub: IRelayHub, terminal: JobTerminalBroadcaster) -> RelayRequestStore:
        store = RelayRequestStore()
        # Хаб уже среди слушателей (он зависимость): сначала поток рвётся с кодом задачи, потом память чистится.
        terminal.add(RelayTerminalCleanup(hub, store))
        return store

    @provide
    def get_ai_relay_client(  # noqa: PLR0913
        self,
        queue: IJobQueue,
        queue_service: JobQueueService,
        runners: IRunnerRepository,
        hub: IRelayHub,
        store: RelayRequestStore,
        wakeup: JobWakeup,
        personal: IPersonalRunnerSettings,
    ) -> AiRelayClient:
        # Личные раннеры выключены админом: ретрансляция отказывает сразу с `disabled`, задачу не ставит.
        return AiRelayClient(queue, queue_service, runners, hub, store, wakeup, personal, limits=relay_limits())

    @provide(override=True)
    def get_provider_relay_describer(
        self, runners: IRunnerRepository, personal: IPersonalRunnerSettings
    ) -> ProviderRelayDescriber:
        return ProviderRelayDescriber(runners, personal)

    @provide(override=True)
    def get_ai_model_lister(self, relay: AiRelayClient) -> IAIModelLister:
        return SdkAIModelLister(relay)

    @provide(override=True)
    def get_agent_provider(self, relay: AiRelayClient) -> IAgentProvider:
        return SdkAgentProvider(relay=relay)

    @provide
    def get_relay_runner_service(
        self, io: RunnerJobIoService, store: RelayRequestStore, hub: IRelayHub
    ) -> RelayRunnerService:
        return RelayRunnerService(io, store, hub)
