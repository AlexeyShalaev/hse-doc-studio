from __future__ import annotations

from typing import Any

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException

from hse_doc_studio.api.schemas.settings import SettingsResponse, UpdateSettingsRequest
from hse_doc_studio.use_cases.settings.get_settings import GetSettingsUC
from hse_doc_studio.use_cases.settings.update_settings import (
    UpdateSettingsInput,
    UpdateSettingsUC,
)

router = APIRouter(route_class=DishkaRoute)


def _map_settings(settings: dict[str, Any]) -> SettingsResponse:
    return SettingsResponse(
        theme=str(settings.get("theme", "system")),
        interface_language=str(settings.get("interface_language", "ru")),
        default_engine=str(settings.get("default_engine", "xelatex")),
        latex_passes=int(settings.get("latex_passes", 3)),
        max_concurrent_compiles=int(settings.get("max_concurrent_compiles", 2)),
        latex_flags=settings.get("latex_flags"),
        compile_image=settings.get("compile_image"),
        default_ai_provider_id=settings.get("default_ai_provider_id"),
        default_ai_model=settings.get("default_ai_model"),
        agent_auto_approve_writes=bool(settings.get("agent_auto_approve_writes", False)),
        agent_enabled_tools=settings.get("agent_enabled_tools"),
        default_agent_persona=settings.get("default_agent_persona"),
        default_agent_persona_instructions=settings.get("default_agent_persona_instructions"),
        auto_update=bool(settings.get("auto_update", True)),
        disk_usage_warn_gb=int(settings.get("disk_usage_warn_gb", 10)),
    )


@router.get("/settings", response_model=SettingsResponse)
async def get_settings(
    uc: FromDishka[GetSettingsUC],
) -> SettingsResponse:
    result = await uc.execute()
    return _map_settings(result.settings)


@router.put("/settings", response_model=SettingsResponse)
async def update_settings(  # noqa: C901, PLR0912 — flat per-field patch mapping with explicit-null handling
    body: UpdateSettingsRequest,
    uc: FromDishka[UpdateSettingsUC],
) -> SettingsResponse:
    # Use `model_fields_set` to distinguish "field omitted from request" from
    # "field present with null value" — clients clear nullable settings
    # (latex_flags) by sending an explicit null.
    fields_set = body.model_fields_set
    patch: dict[str, Any] = {}

    if "theme" in fields_set and body.theme is not None:
        patch["theme"] = body.theme
    if "interface_language" in fields_set and body.interface_language is not None:
        if body.interface_language not in ("ru", "en"):
            raise HTTPException(
                status_code=400,
                detail="interface_language must be 'ru' or 'en'",
            )
        patch["interface_language"] = body.interface_language
    if "default_engine" in fields_set and body.default_engine is not None:
        patch["default_engine"] = body.default_engine
    if "latex_passes" in fields_set and body.latex_passes is not None:
        if not 3 <= body.latex_passes <= 10:
            raise HTTPException(
                status_code=400,
                detail="latex_passes must be between 3 and 10",
            )
        patch["latex_passes"] = body.latex_passes
    if "max_concurrent_compiles" in fields_set and body.max_concurrent_compiles is not None:
        if not 1 <= body.max_concurrent_compiles <= 8:
            raise HTTPException(
                status_code=400,
                detail="max_concurrent_compiles must be between 1 and 8",
            )
        patch["max_concurrent_compiles"] = body.max_concurrent_compiles
    if "latex_flags" in fields_set:
        patch["latex_flags"] = body.latex_flags
    if "compile_image" in fields_set:
        patch["compile_image"] = body.compile_image
    # Nullable: an explicit null clears the chosen default (e.g. after deleting
    # the provider it pointed at).
    if "default_ai_provider_id" in fields_set:
        patch["default_ai_provider_id"] = body.default_ai_provider_id
    if "default_ai_model" in fields_set:
        patch["default_ai_model"] = body.default_ai_model
    if "agent_auto_approve_writes" in fields_set and body.agent_auto_approve_writes is not None:
        patch["agent_auto_approve_writes"] = body.agent_auto_approve_writes
    # Nullable: an explicit null re-enables the full tool catalog.
    if "agent_enabled_tools" in fields_set:
        patch["agent_enabled_tools"] = body.agent_enabled_tools
    # Nullable: an explicit null resets the sticky default role to neutral.
    if "default_agent_persona" in fields_set:
        patch["default_agent_persona"] = body.default_agent_persona
    if "default_agent_persona_instructions" in fields_set:
        patch["default_agent_persona_instructions"] = body.default_agent_persona_instructions
    if "disk_usage_warn_gb" in fields_set and body.disk_usage_warn_gb is not None:
        if not 0 <= body.disk_usage_warn_gb <= 500:
            raise HTTPException(
                status_code=400,
                detail="disk_usage_warn_gb must be between 0 and 500",
            )
        patch["disk_usage_warn_gb"] = body.disk_usage_warn_gb

    try:
        result = await uc.execute(UpdateSettingsInput(patch=patch))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _map_settings(result.settings)
