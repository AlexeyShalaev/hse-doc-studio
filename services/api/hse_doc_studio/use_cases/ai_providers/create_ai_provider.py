from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from hse_doc_studio.core.egress import IEgressPolicy
from hse_doc_studio.core.entities import AIProvider
from hse_doc_studio.core.enums import AIProviderOwnerKind, AIProviderType
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import IAIProviderRepository
from hse_doc_studio.use_cases.ai_providers.base_url import authorize_base_url
from hse_doc_studio.use_cases.ai_providers.relay_info import AiProviderRunnerInvalidError, ProviderRelayDescriber


@dataclass
class CreateAIProviderInput:
    name: str
    type: AIProviderType
    api_key: str
    base_url: str = ""
    models: list[str] = field(default_factory=list)
    ssl_verify: bool = True
    connect_timeout_s: float = 10.0
    request_timeout_s: float = 60.0
    owner_kind: AIProviderOwnerKind = AIProviderOwnerKind.user
    # Вид `runner`: свой раннер и имя объявленного им ИИ-адреса.
    runner_id: str | None = None
    runner_endpoint: str | None = None


@dataclass
class CreateAIProviderOutput:
    provider: AIProvider


class CreateAIProviderUC:
    def __init__(
        self,
        ai_provider_repo: IAIProviderRepository,
        egress: IEgressPolicy | None = None,
        relay: ProviderRelayDescriber | None = None,
    ) -> None:
        self._repo = ai_provider_repo
        self._egress = egress
        self._relay = relay or ProviderRelayDescriber()

    async def execute(self, inp: CreateAIProviderInput) -> CreateAIProviderOutput:
        name = inp.name.strip()
        if not name:
            raise ValueError(localized_error("укажите название", "name is required"))
        if inp.connect_timeout_s <= 0 or inp.request_timeout_s <= 0:
            raise ValueError(localized_error("таймауты должны быть положительными", "timeouts must be positive"))
        if inp.type is AIProviderType.runner:
            return await self._create_runner(inp, name)
        if not inp.api_key.strip():
            raise ValueError(localized_error("укажите API-ключ", "api_key is required"))
        base_url = inp.base_url.strip()
        await authorize_base_url(self._egress, base_url, inp.owner_kind)
        provider = AIProvider(
            id=uuid4(),
            name=name,
            type=inp.type,
            api_key=inp.api_key.strip(),
            base_url=base_url,
            models=list(inp.models),
            created_at=datetime.now(timezone.utc),
            ssl_verify=inp.ssl_verify,
            connect_timeout_s=inp.connect_timeout_s,
            request_timeout_s=inp.request_timeout_s,
            owner_kind=inp.owner_kind,
        )
        await self._repo.create(provider)
        return CreateAIProviderOutput(provider=provider)

    async def _create_runner(self, inp: CreateAIProviderInput, name: str) -> CreateAIProviderOutput:
        """Ни адреса, ни ключа: сервер не ходит в сеть человека, запросы передаёт его раннер."""
        if inp.owner_kind is not AIProviderOwnerKind.user:
            raise AiProviderRunnerInvalidError(
                localized_error("Общий провайдер не может идти через раннер", "A shared provider cannot use a runner")
            )
        runner_id, endpoint = await self._relay.validate(inp.runner_id, inp.runner_endpoint)
        provider = AIProvider(
            id=uuid4(),
            name=name,
            type=AIProviderType.runner,
            api_key="",
            base_url="",
            models=list(inp.models),
            created_at=datetime.now(timezone.utc),
            ssl_verify=True,
            connect_timeout_s=inp.connect_timeout_s,
            request_timeout_s=inp.request_timeout_s,
            owner_kind=AIProviderOwnerKind.user,
            runner_id=runner_id,
            runner_endpoint=endpoint,
        )
        await self._repo.create(provider)
        return CreateAIProviderOutput(provider=provider)
