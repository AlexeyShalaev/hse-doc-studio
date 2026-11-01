from __future__ import annotations

from uuid import UUID

import structlog
from dishka.integrations.fastapi import FromDishka
from fastapi import APIRouter, HTTPException, status

from hse_doc_studio.api.dishka_route import SafeDishkaRoute
from hse_doc_studio.api.schemas.ai_providers import (
    AiProviderRelay,
    AIProviderResponse,
    CreateAIProviderRequest,
    ProviderModelsResponse,
    UpdateAIProviderRequest,
)
from hse_doc_studio.core.entities import AIProvider
from hse_doc_studio.core.enums import AIProviderOwnerKind, Lang
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.use_cases.ai_providers.create_ai_provider import (
    CreateAIProviderInput,
    CreateAIProviderUC,
)
from hse_doc_studio.use_cases.ai_providers.delete_ai_provider import (
    DeleteAIProviderInput,
    DeleteAIProviderUC,
)
from hse_doc_studio.use_cases.ai_providers.get_ai_provider import GetAIProviderInput, GetAIProviderUC
from hse_doc_studio.use_cases.ai_providers.list_ai_providers import ListAIProvidersUC
from hse_doc_studio.use_cases.ai_providers.list_provider_models import (
    ListProviderModelsInput,
    ListProviderModelsUC,
)
from hse_doc_studio.use_cases.ai_providers.relay_info import (
    AiProviderRelayInfo,
    AiProviderRunnerInvalidError,
    ProviderRelayDescriber,
    source_of,
)
from hse_doc_studio.use_cases.ai_providers.update_ai_provider import (
    UpdateAIProviderInput,
    UpdateAIProviderUC,
)
from hse_doc_studio.use_cases.ai_relay.client import relay_error_of

router = APIRouter(route_class=SafeDishkaRoute)
logger = structlog.get_logger()


def _relay_body(info: AiProviderRelayInfo | None) -> AiProviderRelay | None:
    if info is None:
        return None
    return AiProviderRelay(
        runner_id=info.runner_id,
        runner_name=info.runner_name,
        endpoint=info.endpoint,
        flavor=info.flavor.value,
        state=info.state.value,
    )


async def _describe(describer: ProviderRelayDescriber, provider: AIProvider) -> AIProviderResponse:
    return _map_provider(provider, (await describer.describe([provider])).get(provider.id))


def _map_provider(provider: AIProvider, relay: AiProviderRelayInfo | None = None) -> AIProviderResponse:
    return AIProviderResponse(
        id=provider.id,
        name=provider.name,
        type=provider.type,
        base_url=provider.base_url,
        models=provider.models,
        has_api_key=bool(provider.api_key),
        created_at=provider.created_at,
        ssl_verify=provider.ssl_verify,
        connect_timeout_s=provider.connect_timeout_s,
        request_timeout_s=provider.request_timeout_s,
        shared=provider.owner_kind is AIProviderOwnerKind.instance,
        source=source_of(provider).value,
        relay=_relay_body(relay),
    )


@router.get("/ai-providers", response_model=list[AIProviderResponse])
async def list_ai_providers(
    uc: FromDishka[ListAIProvidersUC], describer: FromDishka[ProviderRelayDescriber]
) -> list[AIProviderResponse]:
    result = await uc.execute()
    relays = await describer.describe(result.providers)
    return [_map_provider(p, relays.get(p.id)) for p in result.providers]


@router.post("/ai-providers", response_model=AIProviderResponse, status_code=status.HTTP_201_CREATED)
async def create_ai_provider(
    body: CreateAIProviderRequest,
    uc: FromDishka[CreateAIProviderUC],
    describer: FromDishka[ProviderRelayDescriber],
) -> AIProviderResponse:
    try:
        result = await uc.execute(
            CreateAIProviderInput(
                name=body.name,
                type=body.type,
                api_key=body.api_key,
                base_url=body.base_url,
                models=body.models,
                ssl_verify=body.ssl_verify,
                connect_timeout_s=body.connect_timeout_s,
                request_timeout_s=body.request_timeout_s,
                runner_id=body.runner_id,
                runner_endpoint=body.runner_endpoint,
            )
        )
    except AiProviderRunnerInvalidError:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _describe(describer, result.provider)


@router.get("/ai-providers/{provider_id}", response_model=AIProviderResponse)
async def get_ai_provider(
    provider_id: UUID,
    uc: FromDishka[GetAIProviderUC],
    describer: FromDishka[ProviderRelayDescriber],
) -> AIProviderResponse:
    try:
        result = await uc.execute(GetAIProviderInput(provider_id=provider_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return await _describe(describer, result.provider)


@router.patch("/ai-providers/{provider_id}", response_model=AIProviderResponse)
async def update_ai_provider(
    provider_id: UUID,
    body: UpdateAIProviderRequest,
    uc: FromDishka[UpdateAIProviderUC],
    describer: FromDishka[ProviderRelayDescriber],
) -> AIProviderResponse:
    try:
        result = await uc.execute(
            UpdateAIProviderInput(
                provider_id=provider_id,
                name=body.name,
                type=body.type,
                api_key=body.api_key,
                base_url=body.base_url,
                models=body.models,
                ssl_verify=body.ssl_verify,
                connect_timeout_s=body.connect_timeout_s,
                request_timeout_s=body.request_timeout_s,
                runner_id=body.runner_id,
                runner_endpoint=body.runner_endpoint,
            )
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AiProviderRunnerInvalidError:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _describe(describer, result.provider)


@router.delete("/ai-providers/{provider_id}", status_code=204)
async def delete_ai_provider(
    provider_id: UUID,
    uc: FromDishka[DeleteAIProviderUC],
) -> None:
    try:
        await uc.execute(DeleteAIProviderInput(provider_id=provider_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/ai-providers/{provider_id}/models", response_model=ProviderModelsResponse)
async def list_provider_models(
    provider_id: UUID,
    uc: FromDishka[ListProviderModelsUC],
) -> ProviderModelsResponse:
    try:
        result = await uc.execute(ListProviderModelsInput(provider_id=provider_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        # Провайдер через раннер: недоступность раннера это 503 `relay_unavailable` с понятным текстом.
        relay_error = relay_error_of(exc)
        if relay_error is not None:
            raise relay_error from exc
        # Auth/connection errors bubble up from the openai/anthropic SDK. The
        # exception object can embed the outgoing request (incl. the
        # Authorization header / api_key), so NEVER echo it to the client or
        # logs — surface a generic 502 and log only the safe error type.
        logger.warning(
            "ai_provider model listing failed",
            provider_id=str(provider_id),
            error_type=type(exc).__name__,
        )
        raise HTTPException(
            status_code=502,
            detail=(
                "Could not retrieve the model list. Check the API key and the provider address."
                if current_interface_language() is Lang.en
                else "Не удалось получить список моделей. Проверьте API-ключ и адрес провайдера."
            ),
        ) from exc
    return ProviderModelsResponse(models=result.models)
