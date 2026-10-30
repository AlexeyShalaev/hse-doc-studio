from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from hse_doc_studio.core.egress import IEgressPolicy
from hse_doc_studio.core.entities import AIProvider
from hse_doc_studio.core.enums import AIProviderType
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.identity.protocols import IAuditLog
from hse_doc_studio.core.repositories import IAIProviderRepository
from hse_doc_studio.use_cases.ai_providers.base_url import authorize_base_url
from hse_doc_studio.use_cases.ai_providers.relay_info import (
    AiProviderRunnerInvalidError,
    ProviderRelayDescriber,
    audit_runner_provider,
)


@dataclass
class UpdateAIProviderInput:
    provider_id: UUID
    name: str | None = None
    type: AIProviderType | None = None
    # None or blank → keep the stored key (the UI sends blank to mean "unchanged",
    # since the existing key is never sent back to the browser).
    api_key: str | None = None
    base_url: str | None = None
    models: list[str] | None = None
    # None → keep the stored value (PATCH semantics).
    ssl_verify: bool | None = None
    connect_timeout_s: float | None = None
    request_timeout_s: float | None = None
    runner_id: str | None = None
    runner_endpoint: str | None = None


@dataclass
class UpdateAIProviderOutput:
    provider: AIProvider


class UpdateAIProviderUC:
    def __init__(
        self,
        ai_provider_repo: IAIProviderRepository,
        egress: IEgressPolicy | None = None,
        relay: ProviderRelayDescriber | None = None,
        audit: IAuditLog | None = None,
    ) -> None:
        self._repo = ai_provider_repo
        self._egress = egress
        self._relay = relay or ProviderRelayDescriber()
        self._audit = audit

    async def execute(self, inp: UpdateAIProviderInput) -> UpdateAIProviderOutput:
        existing = await self._repo.get(inp.provider_id)
        if existing is None:
            raise NotFoundError(
                localized_error(f"AI-провайдер {inp.provider_id} не найден", f"AI provider {inp.provider_id} not found")
            )

        name = existing.name if inp.name is None else inp.name.strip()
        if not name:
            raise ValueError(localized_error("укажите название", "name is required"))

        # Blank/omitted key → keep the stored one (never sent back to the client).
        api_key = existing.api_key
        if inp.api_key is not None and inp.api_key.strip():
            api_key = inp.api_key.strip()

        connect_timeout_s = existing.connect_timeout_s if inp.connect_timeout_s is None else inp.connect_timeout_s
        request_timeout_s = existing.request_timeout_s if inp.request_timeout_s is None else inp.request_timeout_s
        if connect_timeout_s <= 0 or request_timeout_s <= 0:
            raise ValueError(localized_error("таймауты должны быть положительными", "timeouts must be positive"))

        new_type = existing.type if inp.type is None else inp.type
        base_url = existing.base_url if inp.base_url is None else inp.base_url.strip()
        runner_id, runner_endpoint = await self._runner_of(existing, inp, new_type)
        if existing.type is AIProviderType.runner:
            # Адреса и ключа у такого провайдера нет.
            base_url, api_key = "", ""
        elif base_url != existing.base_url:
            await authorize_base_url(self._egress, base_url, existing.owner_kind)
        updated = AIProvider(
            id=existing.id,
            name=name,
            type=new_type,
            api_key=api_key,
            base_url=base_url,
            models=existing.models if inp.models is None else list(inp.models),
            created_at=existing.created_at,
            ssl_verify=existing.ssl_verify if inp.ssl_verify is None else inp.ssl_verify,
            connect_timeout_s=connect_timeout_s,
            request_timeout_s=request_timeout_s,
            owner_kind=existing.owner_kind,
            runner_id=runner_id,
            runner_endpoint=runner_endpoint,
        )
        await self._repo.update(updated)
        await self._audit_rebind(existing, updated)
        return UpdateAIProviderOutput(provider=updated)

    async def _audit_rebind(self, existing: AIProvider, updated: AIProvider) -> None:
        """Журнал пишет только смену раннера или адреса: переименование ретрансляцию не перепривязывает."""
        if (updated.runner_id, updated.runner_endpoint) != (existing.runner_id, existing.runner_endpoint):
            await audit_runner_provider(self._audit, "ai_provider.update", updated)

    async def _runner_of(
        self, existing: AIProvider, inp: UpdateAIProviderInput, new_type: AIProviderType
    ) -> tuple[str | None, str | None]:
        """Вид `runner` не меняется; раннер и имя адреса при смене проверяются заново."""
        if (new_type is AIProviderType.runner) != (existing.type is AIProviderType.runner):
            raise AiProviderRunnerInvalidError(
                localized_error(
                    "Вид «через раннер» нельзя сменить: создайте провайдер заново",
                    "A runner provider cannot change its kind: create a new provider",
                )
            )
        if existing.type is not AIProviderType.runner or (inp.runner_id is None and inp.runner_endpoint is None):
            return existing.runner_id, existing.runner_endpoint
        return await self._relay.validate(
            inp.runner_id or existing.runner_id, inp.runner_endpoint or existing.runner_endpoint
        )
