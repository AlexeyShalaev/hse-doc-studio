from __future__ import annotations

from pathlib import PurePosixPath
from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from hse_doc_studio.api.schemas.signature import (
    AttachDetachedSignatureResponse,
    DetachedSignatureResponse,
    FreezePdfResponse,
    FrozenPdfResponse,
    PlacementResponse,
    ProfileRefResponse,
    RuntimeSlotResponse,
    SignaturesStateResponse,
    SignInStudioRequest,
    SlotInfoResponse,
    UpdatePlacementRequest,
    UpdateSlotConfigRequest,
    UploadSignatureResponse,
)
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.value_objects import (
    DetachedSignature,
    FrozenPdf,
    SignaturePlacement,
    SignatureSlot,
    SignaturesState,
)
from hse_doc_studio.use_cases.signatures.attach_detached_signature import (
    AttachDetachedSignatureInput,
    AttachDetachedSignatureOutput,
    AttachDetachedSignatureUC,
    RecheckDetachedSignatureInput,
    RecheckDetachedSignatureUC,
)
from hse_doc_studio.use_cases.signatures.delete_detached_signature import (
    DeleteDetachedSignatureInput,
    DeleteDetachedSignatureUC,
)
from hse_doc_studio.use_cases.signatures.delete_signature_png import (
    DeleteSignaturePngInput,
    DeleteSignaturePngUC,
)
from hse_doc_studio.use_cases.signatures.freeze_pdf import (
    FreezePdfInput,
    FreezePdfUC,
    UnfreezePdfInput,
    UnfreezePdfUC,
)
from hse_doc_studio.use_cases.signatures.get_detached_files import (
    BuildDetachedPackageInput,
    BuildDetachedPackageUC,
    DetachedFileOutput,
    GetDetachedSignatureFileInput,
    GetDetachedSignatureFileUC,
    GetFrozenPdfInput,
    GetFrozenPdfUC,
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
from hse_doc_studio.use_cases.signatures.sign_in_studio import SignInStudioInput, SignInStudioUC
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


def _map_frozen(frozen: FrozenPdf, stale: bool) -> FrozenPdfResponse:
    return FrozenPdfResponse(sha256=frozen.sha256, size=frozen.size, frozen_at=frozen.frozen_at, stale=stale)


def _map_detached(sig: DetachedSignature, frozen: FrozenPdf | None, stale: bool) -> DetachedSignatureResponse:
    return DetachedSignatureResponse(
        format=sig.format,
        origin=sig.origin,
        verdict=sig.verdict,
        signer=sig.signer,
        signer_id=sig.signer_id,
        issuer=sig.issuer,
        algorithm=sig.algorithm,
        signed_at=sig.signed_at,
        not_before=sig.not_before,
        not_after=sig.not_after,
        chain=sig.chain,
        notes=list(sig.notes),
        added_at=sig.added_at,
        file_name=PurePosixPath(sig.file).name,
        current=frozen is not None and sig.pdf_sha256 == frozen.sha256 and not stale,
    )


def _map_state(
    state: SignaturesState, runtime_slots: list[RuntimeSlotItem], stale_frozen: set[str] | None = None
) -> SignaturesStateResponse:
    stale_frozen = stale_frozen or set()
    return SignaturesStateResponse(
        frozen={doc_id: _map_frozen(f, doc_id in stale_frozen) for doc_id, f in state.frozen.items()},
        detached={
            doc_id: {
                slot_id: _map_detached(sig, state.frozen.get(doc_id), doc_id in stale_frozen)
                for slot_id, sig in slot_map.items()
            }
            for doc_id, slot_map in state.detached.items()
        },
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
    return _map_state(result.state, result.runtime_slots, result.stale_frozen)


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


def _file_response(result: DetachedFileOutput, media_type: str) -> FileResponse:
    background = BackgroundTask(result.temp_path.unlink, missing_ok=True) if result.temp_path is not None else None
    return FileResponse(
        path=str(result.path), media_type=media_type, filename=result.download_name, background=background
    )


@router.post("/projects/{project_id}/docs/{doc_id}/frozen", response_model=FreezePdfResponse)
async def freeze_pdf(project_id: UUID, doc_id: str, uc: FromDishka[FreezePdfUC]) -> FreezePdfResponse:
    try:
        result = await uc.execute(FreezePdfInput(project_id=project_id, doc_id=doc_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FreezePdfResponse(frozen=_map_frozen(result.frozen, stale=False), dropped_slots=result.dropped_slots)


@router.delete("/projects/{project_id}/docs/{doc_id}/frozen", status_code=204)
async def unfreeze_pdf(project_id: UUID, doc_id: str, uc: FromDishka[UnfreezePdfUC]) -> None:
    try:
        await uc.execute(UnfreezePdfInput(project_id=project_id, doc_id=doc_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/projects/{project_id}/docs/{doc_id}/frozen/pdf")
async def get_frozen_pdf(project_id: UUID, doc_id: str, uc: FromDishka[GetFrozenPdfUC]) -> FileResponse:
    try:
        result = await uc.execute(GetFrozenPdfInput(project_id=project_id, doc_id=doc_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _file_response(result, "application/pdf")


@router.get("/projects/{project_id}/docs/{doc_id}/signing-package")
async def get_signing_package(
    project_id: UUID,
    doc_id: str,
    uc: FromDishka[BuildDetachedPackageUC],
    mode: str = Query(default="request", pattern="^(request|signed)$"),
) -> FileResponse:
    try:
        result = await uc.execute(
            BuildDetachedPackageInput(
                project_id=project_id, doc_id=doc_id, mode="signed" if mode == "signed" else "request"
            )
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _file_response(result, "application/zip")


def _map_attached(result: AttachDetachedSignatureOutput) -> AttachDetachedSignatureResponse:
    return AttachDetachedSignatureResponse(
        signature=_map_detached(result.signature, None, stale=False).model_copy(update={"current": True}),
        missing_key_id=result.missing_key_id,
    )


@router.post(
    "/projects/{project_id}/docs/{doc_id}/detached/{slot_id}",
    response_model=AttachDetachedSignatureResponse,
)
async def attach_detached_signature(
    project_id: UUID,
    doc_id: str,
    slot_id: str,
    uc: FromDishka[AttachDetachedSignatureUC],
    file: UploadFile = File(...),
    public_key: UploadFile | None = File(default=None),
) -> AttachDetachedSignatureResponse:
    content = await file.read()
    key = await public_key.read() if public_key is not None else None
    try:
        result = await uc.execute(
            AttachDetachedSignatureInput(
                project_id=project_id, doc_id=doc_id, slot_id=slot_id, content=content, public_key=key or None
            )
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _map_attached(result)


@router.post(
    "/projects/{project_id}/docs/{doc_id}/detached/{slot_id}/recheck",
    response_model=AttachDetachedSignatureResponse,
)
async def recheck_detached_signature(
    project_id: UUID,
    doc_id: str,
    slot_id: str,
    uc: FromDishka[RecheckDetachedSignatureUC],
    public_key: UploadFile | None = File(default=None),
) -> AttachDetachedSignatureResponse:
    key = await public_key.read() if public_key is not None else None
    try:
        result = await uc.execute(
            RecheckDetachedSignatureInput(project_id=project_id, doc_id=doc_id, slot_id=slot_id, public_key=key or None)
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _map_attached(result)


@router.post(
    "/projects/{project_id}/docs/{doc_id}/detached/{slot_id}/sign",
    response_model=AttachDetachedSignatureResponse,
)
async def sign_detached_in_studio(
    project_id: UUID,
    doc_id: str,
    slot_id: str,
    body: SignInStudioRequest,
    uc: FromDishka[SignInStudioUC],
) -> AttachDetachedSignatureResponse:
    try:
        result = await uc.execute(
            SignInStudioInput(
                project_id=project_id,
                doc_id=doc_id,
                slot_id=slot_id,
                identity_id=body.identity_id,
                passphrase=body.passphrase,
            )
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _map_attached(AttachDetachedSignatureOutput(signature=result.signature))


@router.get("/projects/{project_id}/docs/{doc_id}/detached/{slot_id}/file")
async def get_detached_signature_file(
    project_id: UUID,
    doc_id: str,
    slot_id: str,
    uc: FromDishka[GetDetachedSignatureFileUC],
) -> FileResponse:
    try:
        result = await uc.execute(GetDetachedSignatureFileInput(project_id=project_id, doc_id=doc_id, slot_id=slot_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _file_response(result, "application/octet-stream")


@router.delete("/projects/{project_id}/docs/{doc_id}/detached/{slot_id}", status_code=204)
async def delete_detached_signature(
    project_id: UUID,
    doc_id: str,
    slot_id: str,
    uc: FromDishka[DeleteDetachedSignatureUC],
) -> None:
    try:
        await uc.execute(DeleteDetachedSignatureInput(project_id=project_id, doc_id=doc_id, slot_id=slot_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
