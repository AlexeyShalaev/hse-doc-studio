"""Состояние ИИ-шлюза для админки: общие провайдеры, их вызовы за сутки и автомат отказов."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from time import monotonic
from uuid import UUID

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.ai_gateway.breaker import BreakerState, CircuitBreakers
from hse_doc_studio.core.ai_gateway.usage import IAiUsageLog
from hse_doc_studio.core.enums import AIProviderOwnerKind
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.repositories import IAIProviderRepository
from hse_doc_studio.use_cases.admin.users import require_admin


@dataclass(frozen=True)
class GatewayProviderStatus:
    provider_id: UUID
    name: str
    type: str
    breaker: BreakerState
    failures: int
    calls: int
    errors: int
    denied: int
    input_tokens: int
    output_tokens: int


class AiGatewayStatusUC:
    def __init__(
        self, providers: IAIProviderRepository, usage: IAiUsageLog, breakers: CircuitBreakers, *, clock: Clock = utc_now
    ) -> None:
        self._providers = providers
        self._usage = usage
        self._breakers = breakers
        self._clock = clock

    async def execute(self, actor: Actor) -> list[GatewayProviderStatus]:
        require_admin(actor)
        summary = {item.provider_id: item for item in await self._usage.summary(self._clock() - timedelta(days=1))}
        now = monotonic()
        out: list[GatewayProviderStatus] = []
        for provider in await self._providers.list_all():
            if provider.owner_kind is not AIProviderOwnerKind.instance:
                continue
            row = summary.get(provider.id)
            out.append(
                GatewayProviderStatus(
                    provider_id=provider.id,
                    name=provider.name,
                    type=provider.type.value,
                    breaker=self._breakers.state(provider.id, now),
                    failures=self._breakers.failures(provider.id),
                    calls=row.calls if row else 0,
                    errors=row.errors if row else 0,
                    denied=row.denied if row else 0,
                    input_tokens=row.input_tokens if row else 0,
                    output_tokens=row.output_tokens if row else 0,
                )
            )
        return out
