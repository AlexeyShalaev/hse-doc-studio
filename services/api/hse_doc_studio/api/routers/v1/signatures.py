from __future__ import annotations

import dataclasses
from pathlib import PurePosixPath
from uuid import UUID

from dishka.integrations.fastapi import FromDishka
from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from hse_doc_studio.api.dishka_route import SafeDishkaRoute
from hse_doc_studio.api.schemas.signature import (
    AttachDetachedSignatureResponse,
    BuildAnchorResponse,
    BuildAnchorsResponse,
    DateMarkResponse,
    DetachedSignatureResponse,
    EmbeddedSignatureResponse,
    FreezePdfResponse,
    FrozenPdfResponse,
    LevelRequest,
    ManualSignerRequest,
    PackDateMarkResponse,
    PackPlaceResponse,
    PlacementResponse,
    ProfileRefResponse,
    RestorePlacementRequest,
    RuntimeSlotResponse,
    SetDateMarksRequest,
    SetSlotOptionalRequest,
    SignaturesStateResponse,
    SignedAtResponse,
    SignerInfoResponse,
    SignInStudioRequest,
    SkippedSlotResponse,
    SlotInfoResponse,
    SlotOptional,
    UpdatePlacementRequest,
    UpdateSlotConfigRequest,
    UploadSignatureResponse,
)
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.signatures.anchors import BuildAnchors
from hse_doc_studio.core.signatures.stamps import date_mark_text
from hse_doc_studio.core.signing_route.audit import signing_route_scope
from hse_doc_studio.core.signing_route.entities import RouteInputError
from hse_doc_studio.core.signing_route.ports import ISigningRouteGate
from hse_doc_studio.core.value_objects import (
    DetachedSignature,
    FrozenPdf,
    SignaturePlacement,
    SignatureSlot,
    SignaturesState,
    SignerInfo,
)
from hse_doc_studio.use_cases.signatures.attach_detached_signature import (
    AttachDetachedSignatureInput,
    AttachDetachedSignatureOutput,
    AttachDetachedSignatureUC,
    CompleteChainInput,
    CompleteDetachedChainUC,
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
from hse_doc_studio.use_cases.signatures.pack_places import MANUAL, PlaceInfo
from hse_doc_studio.use_cases.signatures.release_withheld import ReleaseWithheldInput, ReleaseWithheldUC
from hse_doc_studio.use_cases.signatures.restore_placement import RestorePlacementInput, RestorePlacementUC
from hse_doc_studio.use_cases.signatures.set_date_marks import DateMarkInput, SetDateMarksInput, SetDateMarksUC
from hse_doc_studio.use_cases.signatures.set_slot_optional import SetSlotOptionalInput, SetSlotOptionalUC
from hse_doc_studio.use_cases.signatures.sign_in_studio import SignInStudioInput, SignInStudioUC
from hse_doc_studio.use_cases.signatures.unpin_pdf import UnpinPdfInput, UnpinPdfUC
from hse_doc_studio.use_cases.signatures.update_signature_placement import (
    UpdateSignaturePlacementInput,
    UpdateSignaturePlacementUC,
)
from hse_doc_studio.use_cases.signatures.update_slot_config import (
    UpdateSlotConfigInput,
    UpdateSlotConfigUC,
)
from hse_doc_studio.use_cases.signatures.update_slot_signer import UpdateSlotSignerInput, UpdateSlotSignerUC
from hse_doc_studio.use_cases.signatures.upload_signature_png import (
    UploadSignaturePngInput,
    UploadSignaturePngUC,
)

router = APIRouter(route_class=SafeDishkaRoute)


def _map_slot(slot: SignatureSlot) -> SlotInfoResponse:
    return SlotInfoResponse(
        png_path=slot.png_path,
        natural_width_px=slot.natural_width_px,
        natural_height_px=slot.natural_height_px,
        signing_identity_id=slot.signing_identity_id,
        sign_mode=slot.sign_mode,
        sign_reason=slot.sign_reason,
        signer=SignerInfoResponse(**dataclasses.asdict(slot.signer)) if slot.signer else None,
    )


def _map_placement(
    placement: SignaturePlacement, texts: tuple[str | None, ...] = (), place: PlaceInfo = MANUAL
) -> PlacementResponse:
    """Размещение для ответа; `texts` что напечатает каждая метка даты сейчас (signing-route.md, 14.7), `place`
    откуда место и есть ли место в шаблоне (15.11)."""
    return PlacementResponse(
        enabled=placement.enabled,
        page=placement.page,
        x_mm=placement.x_mm,
        y_mm=placement.y_mm,
        width_mm=placement.width_mm,
        sign_date=placement.sign_date,
        dates=[
            DateMarkResponse(
                id=mark.id,
                page=mark.page,
                x_mm=mark.x_mm,
                y_mm=mark.y_mm,
                width_mm=mark.width_mm,
                height_mm=mark.height_mm,
                format=mark.format,
                align=mark.align,
                text=texts[i] if i < len(texts) else None,
            )
            for i, mark in enumerate(placement.dates)
        ],
        signed_at=SignedAtResponse(at=placement.signed_at.at, source=placement.signed_at.source)
        if placement.signed_at is not None
        else None,
        origin=place.origin,
        preset_available=place.preset_available,
    )


def _state_placement(
    state: SignaturesState, doc_id: str, slot_id: str, lang: str, place: PlaceInfo = MANUAL
) -> PlacementResponse:
    placement = state.placements[doc_id][slot_id]
    return _map_placement(
        placement, tuple(date_mark_text(state, doc_id, slot_id, mark, lang) for mark in placement.dates), place
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
        required=item.slot.required,
        extra_by={
            doc_id: [ProfileRefResponse(id=ref.id, name=ref.name) for ref in refs]
            for doc_id, refs in item.extra_by.items()
        },
        default_placements={
            doc_id: PackPlaceResponse(page=p.page, x_mm=p.x_mm, y_mm=p.y_mm, width_mm=p.width_mm)
            for doc_id, p in item.default_placements.items()
        },
        default_dates={
            doc_id: [
                PackDateMarkResponse(
                    page=m.page,
                    x_mm=m.x_mm,
                    y_mm=m.y_mm,
                    width_mm=m.width_mm,
                    height_mm=m.height_mm,
                    format=m.format,
                    align=m.align,
                )
                for m in marks
            ]
            for doc_id, marks in item.default_dates.items()
        },
    )


def _map_frozen(frozen: FrozenPdf, stale: bool, plate_outdated: bool = False) -> FrozenPdfResponse:
    return FrozenPdfResponse(
        sha256=frozen.sha256,
        size=frozen.size,
        frozen_at=frozen.frozen_at,
        stale=stale,
        plate_outdated=plate_outdated,
    )


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
        root_subject=sig.root_subject,
        root_fingerprint=sig.root_fingerprint,
        notes=list(sig.notes),
        added_at=sig.added_at,
        file_name=PurePosixPath(sig.file).name,
        current=frozen is not None and sig.pdf_sha256 == frozen.sha256 and not stale,
    )


def _map_anchors(anchors: BuildAnchors | None) -> BuildAnchorsResponse | None:
    if anchors is None:
        return None
    return BuildAnchorsResponse(
        build=anchors.build,
        items=[
            BuildAnchorResponse(id=a.id, kind=a.kind.value, page=a.page, x_mm=a.x_mm, y_mm=a.y_mm, width_mm=a.width_mm)
            for a in anchors.anchors
        ],
        problems=list(anchors.problem_codes()),
    )


def _map_state(
    state: SignaturesState,
    runtime_slots: list[RuntimeSlotItem],
    stale_frozen: set[str] | None = None,
    plate_outdated: set[str] | None = None,
    lang: str = "ru",
    places: dict[str, dict[str, PlaceInfo]] | None = None,
    anchors: dict[str, BuildAnchors | None] | None = None,
) -> SignaturesStateResponse:
    stale_frozen = stale_frozen or set()
    plate_outdated = plate_outdated or set()
    return SignaturesStateResponse(
        frozen={
            doc_id: _map_frozen(f, doc_id in stale_frozen, doc_id in plate_outdated)
            for doc_id, f in state.frozen.items()
        },
        detached={
            doc_id: {
                slot_id: _map_detached(sig, state.frozen.get(doc_id), doc_id in stale_frozen)
                for slot_id, sig in slot_map.items()
            }
            for doc_id, slot_map in state.detached.items()
        },
        slots={sid: _map_slot(slot) for sid, slot in state.slots.items()},
        placements={
            doc_id: {
                sid: _state_placement(state, doc_id, sid, lang, (places or {}).get(doc_id, {}).get(sid, MANUAL))
                for sid in slot_map
            }
            for doc_id, slot_map in state.placements.items()
        },
        runtime_slots=[_map_runtime_slot(item) for item in runtime_slots],
        withheld={doc_id: sorted(slots) for doc_id, slots in sorted(state.withheld.items()) if slots},
        optional={
            doc_id: {profile_id: sorted(slots) for profile_id, slots in sorted(by_profile.items()) if slots}
            for doc_id, by_profile in sorted(state.optional.items())
        },
        skipped={
            doc_id: {
                slot_id: SkippedSlotResponse(
                    profile_id=skip.profile_id,
                    route_id=skip.route_id,
                    round=skip.round,
                    at=skip.at,
                    keep_mark=skip.keep_mark,
                )
                for slot_id, skip in sorted(by_slot.items())
            }
            for doc_id, by_slot in sorted(state.skipped.items())
        },
        anchors={doc_id: _map_anchors(item) for doc_id, item in sorted((anchors or {}).items())},
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
    return _map_state(
        result.state,
        result.runtime_slots,
        result.stale_frozen,
        result.plate_outdated,
        result.lang,
        result.places,
        result.anchors,
    )


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
    gate: FromDishka[ISigningRouteGate],
) -> PlacementResponse:
    await gate.require_unlocked(project_id, doc_id=doc_id)
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
    return _map_placement(result.placement, result.texts, result.place)


@router.put(
    "/projects/{project_id}/signatures/placements/{doc_id}/{slot_id}/dates",
    response_model=PlacementResponse,
)
async def set_date_marks(
    project_id: UUID,
    doc_id: str,
    slot_id: str,
    body: SetDateMarksRequest,
    uc: FromDishka[SetDateMarksUC],
) -> PlacementResponse:
    """Метки даты подписания слота документа целиком и ручная дата подписи (signing-route.md, 14.7).

    Отказы: 400 `bad_date_mark` и `bad_date` с `{detail, code}`; 409 `route_locked` (документ держит идущий или
    завершённый маршрут, правку проведёт его сценарий) и `date_from_route` (ручная дата на паре участника маршрута).
    """
    try:
        result = await uc.execute(
            SetDateMarksInput(
                project_id=project_id,
                doc_id=doc_id,
                slot_id=slot_id,
                dates=[
                    DateMarkInput(
                        id=mark.id,
                        page=mark.page,
                        x_mm=mark.x_mm,
                        y_mm=mark.y_mm,
                        width_mm=mark.width_mm,
                        height_mm=mark.height_mm,
                        format=mark.format,
                        align=mark.align,
                    )
                    for mark in body.dates
                ],
                signed_at_given="signed_at" in body.model_fields_set,
                signed_at=body.signed_at.date if body.signed_at is not None else None,
                confirm_reset=body.confirm_reset,
            )
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RouteInputError:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _map_placement(result.placement, result.texts, result.place)


@router.post(
    "/projects/{project_id}/signatures/placements/{doc_id}/{slot_id}/restore",
    response_model=PlacementResponse,
)
async def restore_placement(
    project_id: UUID,
    doc_id: str,
    slot_id: str,
    uc: FromDishka[RestorePlacementUC],
    body: RestorePlacementRequest | None = None,
) -> PlacementResponse:
    """«Вернуть место из шаблона» (signing-route.md, 15.6): место и метки даты слота документа как в шаблоне проекта,
    `enabled` не меняется, пометка `from_pack`.

    Отказы: 400 `unknown_slot` (слот не ставится на документ); 409 `route_locked` (документ держит идущий или
    завершённый маршрут, а права отправки маршрута нет) и `resets_signatures` с `resets` (без `confirm_reset`).
    """
    try:
        result = await uc.execute(
            RestorePlacementInput(
                project_id=project_id,
                doc_id=doc_id,
                slot_id=slot_id,
                confirm_reset=body.confirm_reset if body is not None else False,
            )
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _map_placement(result.placement, result.texts, result.place)


@router.delete(
    "/projects/{project_id}/signatures/withheld/{doc_id}/{slot_id}",
    status_code=204,
)
async def release_withheld(
    project_id: UUID,
    doc_id: str,
    slot_id: str,
    uc: FromDishka[ReleaseWithheldUC],
    gate: FromDishka[ISigningRouteGate],
) -> None:
    """«Показать» картинку, которую придержал маршрут подписания (signing-route.md, 5.6): после отмены маршрута
    картинка не согласовавшего остаётся придержанной, показать её можно только явно. Пока документ держит идущий
    маршрут, правка закрыта (409 `route_locked`). Слот, который не придержан, ничего не меняет."""
    await gate.require_unlocked(project_id, doc_id=doc_id)
    try:
        await uc.execute(ReleaseWithheldInput(project_id=project_id, doc_id=doc_id, slot_id=slot_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put(
    "/projects/{project_id}/signatures/optional/{doc_id}/{slot_id}",
    response_model=SlotOptional,
)
async def set_slot_optional(
    project_id: UUID,
    doc_id: str,
    slot_id: str,
    body: SetSlotOptionalRequest,
    uc: FromDishka[SetSlotOptionalUC],
) -> SlotOptional:
    """«Подпись необязательна на этой точке» (signing-route.md, 13.6): отметить или снять. Видимого слоя не меняет,
    поэтому работает и на идущем маршруте. 400 `unknown_slot`, если слот не ставится на документ точки и не включён
    её маршрутом; 409 `optional_forbidden`, если пак запрещает; 409 `slot_signed`, если подпись уже стоит на
    документе маршрута."""
    try:
        out = await uc.execute(
            SetSlotOptionalInput(
                project_id=project_id,
                doc_id=doc_id,
                slot_id=slot_id,
                profile_id=body.profile_id,
                optional=body.optional,
            )
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SlotOptional(
        doc_id=out.doc_id,
        slot_id=out.slot_id,
        profile_id=out.profile_id,
        optional=out.optional,
        skipped=out.skipped,
        returns_next_round=out.returns_next_round,
    )


@router.post(
    "/projects/{project_id}/signatures/slots/{slot_id}/png",
    response_model=UploadSignatureResponse,
)
async def upload_signature_png(
    project_id: UUID,
    slot_id: str,
    uc: FromDishka[UploadSignaturePngUC],
    gate: FromDishka[ISigningRouteGate],
    file: UploadFile = File(...),
) -> UploadSignatureResponse:
    await gate.require_unlocked(project_id, slot_id=slot_id)
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
    gate: FromDishka[ISigningRouteGate],
) -> None:
    await gate.require_unlocked(project_id, slot_id=slot_id)
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
    gate: FromDishka[ISigningRouteGate],
) -> SlotInfoResponse:
    await gate.require_unlocked(project_id, slot_id=slot_id)
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
async def freeze_pdf(
    project_id: UUID, doc_id: str, uc: FromDishka[FreezePdfUC], gate: FromDishka[ISigningRouteGate]
) -> FreezePdfResponse:
    await gate.require_unlocked(project_id, doc_id=doc_id)
    try:
        result = await uc.execute(FreezePdfInput(project_id=project_id, doc_id=doc_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FreezePdfResponse(frozen=_map_frozen(result.frozen, stale=False), dropped_slots=result.dropped_slots)


@router.delete("/projects/{project_id}/docs/{doc_id}/frozen", status_code=204)
async def unfreeze_pdf(
    project_id: UUID, doc_id: str, uc: FromDishka[UnfreezePdfUC], gate: FromDishka[ISigningRouteGate]
) -> None:
    await gate.require_unlocked(project_id, doc_id=doc_id)
    try:
        await uc.execute(UnfreezePdfInput(project_id=project_id, doc_id=doc_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/projects/{project_id}/docs/{doc_id}/pinned", status_code=204)
async def unpin_pdf(project_id: UUID, doc_id: str, uc: FromDishka[UnpinPdfUC]) -> None:
    """«Подписывать текущую сборку»: снять версию на подписи (signing-route.md, 12.4).

    404, если её нет; 409 `route_locked`, пока документ держит маршрут (в том числе завершённый).
    """
    try:
        await uc.execute(UnpinPdfInput(project_id=project_id, doc_id=doc_id))
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
    gate: FromDishka[ISigningRouteGate],
    file: UploadFile = File(...),
    public_key: UploadFile | None = File(default=None),
) -> AttachDetachedSignatureResponse:
    content = await file.read()
    key = await public_key.read() if public_key is not None else None
    route_id = await gate.require_turn(project_id, doc_id, slot_id)
    try:
        with signing_route_scope(route_id):
            result = await uc.execute(
                AttachDetachedSignatureInput(
                    project_id=project_id, doc_id=doc_id, slot_id=slot_id, content=content, public_key=key or None
                )
            )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await gate.signature_written(project_id, doc_id, slot_id)
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
    "/projects/{project_id}/docs/{doc_id}/detached/{slot_id}/complete-chain",
    response_model=AttachDetachedSignatureResponse,
)
async def complete_detached_chain(
    project_id: UUID,
    doc_id: str,
    slot_id: str,
    uc: FromDishka[CompleteDetachedChainUC],
) -> AttachDetachedSignatureResponse:
    try:
        result = await uc.execute(CompleteChainInput(project_id=project_id, doc_id=doc_id, slot_id=slot_id))
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
    gate: FromDishka[ISigningRouteGate],
) -> AttachDetachedSignatureResponse:
    route_id = await gate.require_turn(project_id, doc_id, slot_id)
    try:
        with signing_route_scope(route_id):
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
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await gate.signature_written(project_id, doc_id, slot_id)
    return _map_attached(AttachDetachedSignatureOutput(signature=result.signature))


@router.post(
    "/projects/{project_id}/docs/{doc_id}/embedded/{slot_id}/sign",
    response_model=EmbeddedSignatureResponse,
)
async def sign_embedded_in_studio(
    project_id: UUID,
    doc_id: str,
    slot_id: str,
    body: SignInStudioRequest,
    uc: FromDishka[SignInStudioUC],
    gate: FromDishka[ISigningRouteGate],
) -> EmbeddedSignatureResponse:
    """Встроенная подпись PAdES ключом Студии: дописывается поверх зафиксированного PDF (signature-plan.md, 4)."""
    route_id = await gate.require_turn(project_id, doc_id, slot_id)
    try:
        with signing_route_scope(route_id):
            result = await uc.sign_pades(
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
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await gate.signature_written(project_id, doc_id, slot_id)
    sig = result.signature
    return EmbeddedSignatureResponse(
        field_name=sig.field_name,
        verdict=sig.verdict,
        signer=sig.signer,
        signer_id=sig.signer_id,
        signed_at=sig.signed_at,
        revision_size=sig.revision_size,
        notes=list(sig.notes),
    )


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
    gate: FromDishka[ISigningRouteGate],
) -> None:
    await gate.require_unlocked(project_id, doc_id=doc_id)
    try:
        await uc.execute(DeleteDetachedSignatureInput(project_id=project_id, doc_id=doc_id, slot_id=slot_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _signer_result(exc: Exception) -> HTTPException:
    return HTTPException(status_code=404 if isinstance(exc, NotFoundError) else 400, detail=str(exc))


@router.put(
    "/projects/{project_id}/signatures/slots/{slot_id}/signer",
    response_model=SlotInfoResponse,
)
async def set_slot_signer(
    project_id: UUID,
    slot_id: str,
    body: ManualSignerRequest,
    uc: FromDishka[UpdateSlotSignerUC],
    gate: FromDishka[ISigningRouteGate],
) -> SlotInfoResponse:
    """Signer for the plate: one of the Studio's keys (`identity_id`) or typed-in fields."""
    await gate.require_unlocked(project_id, slot_id=slot_id)
    manual = None
    if body.identity_id is None:
        manual = SignerInfo(
            kind="manual",
            owner=body.owner.strip(),
            cert_id=body.cert_id.strip(),
            valid_from=body.valid_from,
            valid_to=body.valid_to,
            level=body.level,
        )
    try:
        result = await uc.execute(
            UpdateSlotSignerInput(project_id=project_id, slot_id=slot_id, identity_id=body.identity_id, manual=manual)
        )
    except (NotFoundError, ValueError) as exc:
        raise _signer_result(exc) from exc
    return _map_slot(result.slot)


@router.put(
    "/projects/{project_id}/signatures/slots/{slot_id}/signer/level",
    response_model=SlotInfoResponse,
)
async def set_slot_signer_level(
    project_id: UUID,
    slot_id: str,
    body: LevelRequest,
    uc: FromDishka[UpdateSlotSignerUC],
    gate: FromDishka[ISigningRouteGate],
) -> SlotInfoResponse:
    await gate.require_unlocked(project_id, slot_id=slot_id)
    try:
        result = await uc.execute(UpdateSlotSignerInput(project_id=project_id, slot_id=slot_id, level=body.level))
    except (NotFoundError, ValueError) as exc:
        raise _signer_result(exc) from exc
    return _map_slot(result.slot)


@router.post(
    "/projects/{project_id}/signatures/slots/{slot_id}/signer/file",
    response_model=SlotInfoResponse,
)
async def set_slot_signer_from_file(
    project_id: UUID,
    slot_id: str,
    uc: FromDishka[UpdateSlotSignerUC],
    gate: FromDishka[ISigningRouteGate],
    file: UploadFile = File(...),
) -> SlotInfoResponse:
    """Signer for the plate from the signer's public certificate (.cer/.pem) or OpenPGP public key (.asc)."""
    await gate.require_unlocked(project_id, slot_id=slot_id)
    try:
        result = await uc.execute(
            UpdateSlotSignerInput(project_id=project_id, slot_id=slot_id, certificate=await file.read())
        )
    except (NotFoundError, ValueError) as exc:
        raise _signer_result(exc) from exc
    return _map_slot(result.slot)


@router.delete("/projects/{project_id}/signatures/slots/{slot_id}/signer", response_model=SlotInfoResponse)
async def clear_slot_signer(
    project_id: UUID, slot_id: str, uc: FromDishka[UpdateSlotSignerUC], gate: FromDishka[ISigningRouteGate]
) -> SlotInfoResponse:
    await gate.require_unlocked(project_id, slot_id=slot_id)
    try:
        result = await uc.execute(UpdateSlotSignerInput(project_id=project_id, slot_id=slot_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _map_slot(result.slot)
