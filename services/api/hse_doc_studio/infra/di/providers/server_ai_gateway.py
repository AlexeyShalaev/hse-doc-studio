"""ИИ-шлюз сервера: общие вызовы моделей идут через `AiGateway`, раннерные ретрансляции остаются внутри него."""

from __future__ import annotations

from dishka import AnyOf, Provider, Scope, provide

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.agent.protocols import IAgentProvider
from hse_doc_studio.core.ai import IAIModelLister
from hse_doc_studio.core.ai_gateway.breaker import CircuitBreakers
from hse_doc_studio.core.ai_gateway.usage import IAiUsageLog
from hse_doc_studio.core.jobs.quotas import IProjectOrgReader
from hse_doc_studio.core.quotas.protocols import IQuotaGate
from hse_doc_studio.core.repositories import IAIProviderRepository
from hse_doc_studio.infra.ai.agent.sdk_agent_provider import SdkAgentProvider
from hse_doc_studio.infra.ai.errors import is_transient_ai_error
from hse_doc_studio.infra.ai.sdk_model_lister import SdkAIModelLister
from hse_doc_studio.infra.db.repositories.ai_usage import SqlAiUsageLog
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.use_cases.ai_gateway.gateway import AiGateway, GatewayConfig
from hse_doc_studio.use_cases.ai_gateway.status import AiGatewayStatusUC


class ServerAiGatewayProvider(Provider):
    scope = Scope.APP

    @provide
    def get_circuit_breakers(self) -> CircuitBreakers:
        cfg = settings.ai_gateway
        return CircuitBreakers(threshold=cfg.breaker_threshold, open_for_s=cfg.breaker_open_s)

    @provide
    def get_ai_usage_log(self, sessions: SessionProvider) -> IAiUsageLog:
        return SqlAiUsageLog(sessions)

    @provide(override=True)
    def get_ai_gateway(  # noqa: PLR0913
        self,
        agent: SdkAgentProvider,
        lister: SdkAIModelLister,
        gate: IQuotaGate,
        usage: IAiUsageLog,
        providers: IAIProviderRepository,
        project_orgs: IProjectOrgReader,
        breakers: CircuitBreakers,
    ) -> AnyOf[AiGateway, IAgentProvider, IAIModelLister]:
        cfg = settings.ai_gateway
        return AiGateway(
            agent,
            lister,
            gate,
            usage,
            providers,
            project_orgs,
            is_transient_ai_error,
            config=GatewayConfig(
                retries=cfg.retries, base_delay_s=cfg.retry_base_delay_s, max_delay_s=cfg.retry_max_delay_s
            ),
            breakers=breakers,
        )

    @provide
    def get_ai_gateway_status_uc(
        self, providers: IAIProviderRepository, usage: IAiUsageLog, breakers: CircuitBreakers
    ) -> AiGatewayStatusUC:
        return AiGatewayStatusUC(providers, usage, breakers)
