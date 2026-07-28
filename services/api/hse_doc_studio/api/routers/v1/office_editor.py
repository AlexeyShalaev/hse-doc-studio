from __future__ import annotations

from typing import Any
from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException, Request

from hse_doc_studio.api.schemas.office_editor import OfficeEditorConfigResponse
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.infra.office.editor_manager import OfficeEditorManager
from hse_doc_studio.use_cases.office_editor.get_editor_config import (
    GetOfficeEditorConfigInput,
    GetOfficeEditorConfigUC,
    NotOfficeDocumentError,
)
from hse_doc_studio.use_cases.office_editor.handle_callback import (
    OfficeEditorCallbackInput,
    OfficeEditorCallbackUC,
)

router = APIRouter(route_class=DishkaRoute)


@router.get(
    "/projects/{project_id}/documents/{doc_id}/office-editor",
    response_model=OfficeEditorConfigResponse,
)
async def get_office_editor_config(
    project_id: UUID,
    doc_id: str,
    uc: FromDishka[GetOfficeEditorConfigUC],
) -> OfficeEditorConfigResponse:
    """Конфиг встроенного DS-редактора; может блокироваться до ~3 минут
    (холодный старт контейнера) — фронт ждёт со спиннером."""
    try:
        result = await uc.execute(GetOfficeEditorConfigInput(project_id=project_id, doc_id=doc_id))
    except NotOfficeDocumentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return OfficeEditorConfigResponse(
        state=result.state,
        editor_base_url=result.editor_base_url,
        api_js_url=result.api_js_url,
        config=result.config,
        image=result.image,
        detail=result.detail,
        settings_section=result.settings_section,
    )


@router.post("/office-editor/callback")
async def office_editor_callback(
    project_id: UUID,
    doc_id: str,
    sig: str,
    request: Request,
    uc: FromDishka[OfficeEditorCallbackUC],
) -> dict[str, int]:
    """Приёмник колбэков Document Server (вызывает ТОЛЬКО контейнер, не фронт)."""
    try:
        body: Any = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid JSON body") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="callback body must be a JSON object")
    try:
        return await uc.execute(
            OfficeEditorCallbackInput(
                project_id=project_id,
                doc_id=doc_id,
                sig=sig,
                body=body,
                authorization=request.headers.get("Authorization"),
            )
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/projects/{project_id}/documents/{doc_id}/office-editor/touch",
    status_code=204,
    response_model=None,
)
async def touch_office_editor(
    project_id: UUID,  # noqa: ARG001 — единый контейнер на все проекты; путь — для симметрии API
    doc_id: str,  # noqa: ARG001
    manager: FromDishka[OfficeEditorManager],
) -> None:
    """Keepalive открытой вкладки редактора: не даёт idle-reaper'у погасить
    контейнер под живым редактором (фронт шлёт каждые ~120 с)."""
    manager.touch()
