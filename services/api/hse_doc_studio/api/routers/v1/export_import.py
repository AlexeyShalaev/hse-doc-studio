from __future__ import annotations

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException

from hse_doc_studio.api.schemas.export_import import (
    ExportBundle,
    ExportRequest,
    ImportRequest,
    ImportResponse,
)
from hse_doc_studio.use_cases.export_import.export_data import ExportDataInput, ExportDataUC
from hse_doc_studio.use_cases.export_import.import_data import ImportDataInput, ImportDataUC

router = APIRouter(route_class=DishkaRoute)


@router.post("/data/export", response_model=ExportBundle)
async def export_data(
    body: ExportRequest,
    uc: FromDishka[ExportDataUC],
) -> ExportBundle:
    result = await uc.execute(
        ExportDataInput(
            include_settings=body.include_settings,
            include_ai_providers=body.include_ai_providers,
            include_agent_personas=body.include_agent_personas,
            encryption_password=body.encryption_password or None,
        )
    )
    return ExportBundle(
        version=result.version,
        exported_at=result.exported_at,
        encrypted=result.encrypted,
        settings=result.settings,
        ai_providers=result.ai_providers,
        agent_personas=result.agent_personas,
    )


@router.post("/data/import", response_model=ImportResponse, status_code=201)
async def import_data(
    body: ImportRequest,
    uc: FromDishka[ImportDataUC],
) -> ImportResponse:
    try:
        result = await uc.execute(
            ImportDataInput(
                encrypted=body.encrypted,
                settings=body.settings,
                ai_providers=body.ai_providers,
                agent_personas=body.agent_personas,
                merge_strategy=body.merge_strategy,
                decryption_password=body.decryption_password,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ImportResponse(
        settings_imported=result.settings_imported,
        ai_providers_imported=result.ai_providers_imported,
        ai_providers_skipped=result.ai_providers_skipped,
        agent_personas_imported=result.agent_personas_imported,
        agent_personas_skipped=result.agent_personas_skipped,
        errors=result.errors,
    )
