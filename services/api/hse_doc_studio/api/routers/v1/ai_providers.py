from __future__ import annotations

from uuid import UUID

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException, status

from hse_doc_studio.api.schemas.ai_providers import (
    AIProviderResponse,
    CreateAIProviderRequest,
    ProviderModelsResponse,
    UpdateAIProviderRequest,
)
from hse_doc_studio.core.entities import AIProvider
from hse_doc_studio.core.enums import Lang
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
from hse_doc_studio.use_cases.ai_providers.update_ai_provider import (
    UpdateAIProviderInput,
    UpdateAIProviderUC,
)

router = APIRouter(route_class=DishkaRoute)
logger = structlog.get_logger()


def _map_provider(provider: AIProvider) -> AIProviderResponse:
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
    )


@router.get("/ai-providers", response_model=list[AIProviderResponse])
async def list_ai_providers(uc: FromDishka[ListAIProvidersUC]) -> list[AIProviderResponse]:
    result = await uc.execute()
    return [_map_provider(p) for p in result.providers]


@router.post("/ai-providers", response_model=AIProviderResponse, status_code=status.HTTP_201_CREATED)
async def create_ai_provider(
    body: CreateAIProviderRequest,
    uc: FromDishka[CreateAIProviderUC],
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
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _map_provider(result.provider)


@router.get("/ai-providers/{provider_id}", response_model=AIProviderResponse)
async def get_ai_provider(
    provider_id: UUID,
    uc: FromDishka[GetAIProviderUC],
) -> AIProviderResponse:
    try:
        result = await uc.execute(GetAIProviderInput(provider_id=provider_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _map_provider(result.provider)


@router.patch("/ai-providers/{provider_id}", response_model=AIProviderResponse)
async def update_ai_provider(
    provider_id: UUID,
    body: UpdateAIProviderRequest,
    uc: FromDishka[UpdateAIProviderUC],
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
            )
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _map_provider(result.provider)


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
