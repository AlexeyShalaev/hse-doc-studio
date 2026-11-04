from __future__ import annotations

from typing import Any

from dishka.integrations.fastapi import FromDishka
from fastapi import APIRouter, HTTPException

from hse_doc_studio.api.dishka_route import SafeDishkaRoute
from hse_doc_studio.api.schemas.settings import SettingsResponse, UpdateSettingsRequest
from hse_doc_studio.core.paths import PathMapping
from hse_doc_studio.use_cases.settings.get_settings import GetSettingsUC
from hse_doc_studio.use_cases.settings.update_settings import (
    UpdateSettingsInput,
    UpdateSettingsUC,
)
from hse_doc_studio.use_cases.settings.value_rules import (
    DEFAULT_TEXT_SCALE,
    TEXT_SCALE_STEPS,
    disk_usage_warn_gb,
    git_fetch_interval_s,
    projects_dir,
    text_scale,
)

router = APIRouter(route_class=SafeDishkaRoute)


def _int_setting(settings: dict[str, Any], key: str, default: int) -> int:
    """Число из config.json: испорченное значение (чужой файл, правка вручную) не должно ронять весь GET /settings."""
    value = settings.get(key, default)
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _text_setting(settings: dict[str, Any], key: str) -> str | None:
    """Строка из config.json или None: испорченное значение читается как «не задано»."""
    value = settings.get(key)
    return value if isinstance(value, str) and value else None


def _map_settings(settings: dict[str, Any]) -> SettingsResponse:
    return SettingsResponse(
        theme=str(settings.get("theme", "system")),
        interface_language=str(settings.get("interface_language", "ru")),
        text_scale=text_scale(settings.get("text_scale")) or DEFAULT_TEXT_SCALE,
        default_engine=str(settings.get("default_engine", "xelatex")),
        latex_passes=_int_setting(settings, "latex_passes", 3),
        max_concurrent_compiles=_int_setting(settings, "max_concurrent_compiles", 2),
        latex_flags=settings.get("latex_flags"),
        compile_image=settings.get("compile_image"),
        default_ai_provider_id=settings.get("default_ai_provider_id"),
        default_ai_model=settings.get("default_ai_model"),
        agent_auto_approve_writes=bool(settings.get("agent_auto_approve_writes", False)),
        agent_enabled_tools=settings.get("agent_enabled_tools"),
        default_agent_persona=settings.get("default_agent_persona"),
        default_agent_persona_instructions=settings.get("default_agent_persona_instructions"),
        auto_update=bool(settings.get("auto_update", True)),
        disk_usage_warn_gb=_int_setting(settings, "disk_usage_warn_gb", 10),
        git_fetch_interval_s=_int_setting(settings, "git_fetch_interval_s", 300),
        projects_dir=_text_setting(settings, "projects_dir"),
    )


def _checked_text_scale(value: int) -> int:
    """Ступень размера текста; число вне шкалы это 400, а не молчаливое округление."""
    step = text_scale(value)
    if step is None:
        raise HTTPException(
            status_code=400, detail=f"text_scale must be one of {', '.join(map(str, TEXT_SCALE_STEPS))}"
        )
    return step


def _checked_projects_dir(raw: str | None, paths: PathMapping) -> str | None:
    """Папка проектов из облака: пустая строка возвращает стандартную, иначе нужен путь в доступных папках."""
    folder = projects_dir(raw)
    if folder is None and (raw or "").strip():
        raise HTTPException(status_code=400, detail="projects_dir must be an absolute path")
    if folder is not None and paths.to_container(folder) is None:
        raise HTTPException(status_code=400, detail="projects_dir must be inside a folder the Studio has access to")
    return folder


@router.get("/settings", response_model=SettingsResponse)
async def get_settings(
    uc: FromDishka[GetSettingsUC],
) -> SettingsResponse:
    result = await uc.execute()
    return _map_settings(result.settings)


@router.put("/settings", response_model=SettingsResponse)
async def update_settings(  # noqa: C901, PLR0912, PLR0915 — flat per-field patch mapping with explicit-null handling
    body: UpdateSettingsRequest,
    uc: FromDishka[UpdateSettingsUC],
    paths: FromDishka[PathMapping],
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
    if "text_scale" in fields_set and body.text_scale is not None:
        patch["text_scale"] = _checked_text_scale(body.text_scale)
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
        if disk_usage_warn_gb(body.disk_usage_warn_gb) is None:
            raise HTTPException(
                status_code=400,
                detail="disk_usage_warn_gb must be between 0 and 500",
            )
        patch["disk_usage_warn_gb"] = body.disk_usage_warn_gb
    if "git_fetch_interval_s" in fields_set and body.git_fetch_interval_s is not None:
        interval = git_fetch_interval_s(body.git_fetch_interval_s)
        if interval is None:
            raise HTTPException(
                status_code=400,
                detail="git_fetch_interval_s must be 0 or at least 60",
            )
        # 0 выключает проверку; всё, что меньше минуты, поднимается до минуты.
        patch["git_fetch_interval_s"] = interval
    if "projects_dir" in fields_set:
        patch["projects_dir"] = _checked_projects_dir(body.projects_dir, paths)

    try:
        result = await uc.execute(UpdateSettingsInput(patch=patch))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _map_settings(result.settings)
