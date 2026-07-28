from __future__ import annotations

from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from hse_doc_studio.api.schemas.signature import (
    PlacementResponse,
    ProfileRefResponse,
    RuntimeSlotResponse,
    SignaturesStateResponse,
    SlotInfoResponse,
    UpdatePlacementRequest,
    UpdateSlotConfigRequest,
    UploadSignatureResponse,
)
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.value_objects import (
    SignaturePlacement,
    SignatureSlot,
    SignaturesState,
)
from hse_doc_studio.use_cases.signatures.delete_signature_png import (
    DeleteSignaturePngInput,
    DeleteSignaturePngUC,
)
from hse_doc_studio.use_cases.signatures.get_signatures import (
    GetSignaturesInput,
    GetSignaturesUC,
    RuntimeSlotItem,
)
from hse_doc_studio.use_cases.signatures.get_signed_doc_pdf import (
    GetSignedDocPdfInput,
    GetSignedDocPdfUC,
)
from hse_doc_studio.use_cases.signatures.update_signature_placement import (
    UpdateSignaturePlacementInput,
    UpdateSignaturePlacementUC,
)
from hse_doc_studio.use_cases.signatures.update_slot_config import (
    UpdateSlotConfigInput,
    UpdateSlotConfigUC,
)
from hse_doc_studio.use_cases.signatures.upload_signature_png import (
    UploadSignaturePngInput,
    UploadSignaturePngUC,
)

router = APIRouter(route_class=DishkaRoute)


def _map_slot(slot: SignatureSlot) -> SlotInfoResponse:
    return SlotInfoResponse(
        png_path=slot.png_path,
        natural_width_px=slot.natural_width_px,
        natural_height_px=slot.natural_height_px,
        signing_identity_id=slot.signing_identity_id,
        sign_mode=slot.sign_mode,
        sign_reason=slot.sign_reason,
    )


def _map_placement(placement: SignaturePlacement) -> PlacementResponse:
    return PlacementResponse(
        enabled=placement.enabled,
        page=placement.page,
        x_mm=placement.x_mm,
        y_mm=placement.y_mm,
        width_mm=placement.width_mm,
        sign_date=placement.sign_date,
    )


def _map_runtime_slot(item: RuntimeSlotItem) -> RuntimeSlotResponse:
    placement = item.slot.slot_def.default_placement
    return RuntimeSlotResponse(
        id=item.slot.id,
        label=item.slot.label,
        applies_to=item.applies_to,
        required_by={
            doc_id: [ProfileRefResponse(id=ref.id, name=ref.name) for ref in refs]
            for doc_id, refs in item.required_by.items()
        },
        default_placement={
            "page": placement.page,
            "x_mm": placement.x_mm,
            "y_mm": placement.y_mm,
            "width_mm": placement.width_mm,
        },
        owner=item.slot.owner,
    )


def _map_state(state: SignaturesState, runtime_slots: list[RuntimeSlotItem]) -> SignaturesStateResponse:
    return SignaturesStateResponse(
        slots={sid: _map_slot(slot) for sid, slot in state.slots.items()},
        placements={
            doc_id: {sid: _map_placement(p) for sid, p in slot_map.items()}
            for doc_id, slot_map in state.placements.items()
        },
        runtime_slots=[_map_runtime_slot(item) for item in runtime_slots],
    )


@router.get(
    "/projects/{project_id}/signatures",
    response_model=SignaturesStateResponse,
)
async def get_signatures(
    project_id: UUID,
    uc: FromDishka[GetSignaturesUC],
) -> SignaturesStateResponse:
    try:
        result = await uc.execute(GetSignaturesInput(project_id=project_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _map_state(result.state, result.runtime_slots)


@router.patch(
    "/projects/{project_id}/signatures/placements/{doc_id}/{slot_id}",
    response_model=PlacementResponse,
)
async def update_placement(
    project_id: UUID,
    doc_id: str,
    slot_id: str,
    body: UpdatePlacementRequest,
    uc: FromDishka[UpdateSignaturePlacementUC],
) -> PlacementResponse:
    try:
        result = await uc.execute(
            UpdateSignaturePlacementInput(
                project_id=project_id,
                doc_id=doc_id,
                slot_id=slot_id,
                enabled=body.enabled,
                page=body.page,
                x_mm=body.x_mm,
                y_mm=body.y_mm,
                width_mm=body.width_mm,
                sign_date=body.sign_date,
            )
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _map_placement(result.placement)


@router.post(
    "/projects/{project_id}/signatures/slots/{slot_id}/png",
    response_model=UploadSignatureResponse,
)
async def upload_signature_png(
    project_id: UUID,
    slot_id: str,
    uc: FromDishka[UploadSignaturePngUC],
    file: UploadFile = File(...),
) -> UploadSignatureResponse:
    content = await file.read()
    try:
        result = await uc.execute(
            UploadSignaturePngInput(
                project_id=project_id,
                slot_id=slot_id,
                filename=file.filename or f"{slot_id}.png",
                content=content,
            )
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return UploadSignatureResponse(
        png_path=result.png_path,
        natural_width_px=result.natural_width_px,
        natural_height_px=result.natural_height_px,
    )


@router.delete(
    "/projects/{project_id}/signatures/slots/{slot_id}/png",
    status_code=204,
)
async def delete_signature_png(
    project_id: UUID,
    slot_id: str,
    uc: FromDishka[DeleteSignaturePngUC],
) -> None:
    try:
        await uc.execute(DeleteSignaturePngInput(project_id=project_id, slot_id=slot_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/projects/{project_id}/docs/{doc_id}/pdf/signed")
async def get_signed_doc_pdf(
    project_id: UUID,
    doc_id: str,
    uc: FromDishka[GetSignedDocPdfUC],
) -> FileResponse:
    try:
        result = await uc.execute(GetSignedDocPdfInput(project_id=project_id, doc_id=doc_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    background = BackgroundTask(result.temp_path.unlink, missing_ok=True) if result.temp_path is not None else None

    # Detached mode: UC packed the PDF + .sig files into a zip.
    if result.zip_path is not None:
        return FileResponse(
            path=str(result.zip_path),
            media_type="application/zip",
            filename=result.download_name,
            background=background,
        )

    return FileResponse(
        path=str(result.pdf_path),
        media_type="application/pdf",
        filename=result.download_name,
        background=background,
    )


@router.patch(
    "/projects/{project_id}/signatures/slots/{slot_id}/config",
    response_model=SlotInfoResponse,
)
async def update_slot_config(
    project_id: UUID,
    slot_id: str,
    body: UpdateSlotConfigRequest,
    uc: FromDishka[UpdateSlotConfigUC],
) -> SlotInfoResponse:
    try:
        result = await uc.execute(
            UpdateSlotConfigInput(
                project_id=project_id,
                slot_id=slot_id,
                signing_identity_id=body.signing_identity_id,
                sign_mode=body.sign_mode,
                sign_reason=body.sign_reason,
            )
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _map_slot(result.slot)
