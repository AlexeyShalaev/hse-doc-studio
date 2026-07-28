from __future__ import annotations

from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from hse_doc_studio.api.schemas.document import (
    CustomFileOverrideResponse,
    DocumentDetailResponse,
    DocumentListItemResponse,
    UpdateDocumentRequest,
)
from hse_doc_studio.core.entities import Document
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.value_objects import ChecksOverride, CustomFileOverride
from hse_doc_studio.use_cases.documents.get_document import (
    GetDocumentInput,
    GetDocumentOutput,
    GetDocumentUC,
)
from hse_doc_studio.use_cases.documents.list_documents import (
    DocumentListEntry,
    ListDocumentsInput,
    ListDocumentsUC,
)
from hse_doc_studio.use_cases.documents.revert_custom_file import (
    RevertCustomFileInput,
    RevertCustomFileUC,
)
from hse_doc_studio.use_cases.documents.update_document import (
    _MISSING,
    InvalidVariantError,
    UpdateDocumentInput,
    UpdateDocumentUC,
)
from hse_doc_studio.use_cases.documents.upload_custom_file import (
    UploadCustomFileInput,
    UploadCustomFileUC,
)

router = APIRouter(route_class=DishkaRoute)


def _map_custom_file(
    custom_file: CustomFileOverride | None, preview_available: bool
) -> CustomFileOverrideResponse | None:
    if custom_file is None:
        return None
    return CustomFileOverrideResponse(
        original_filename=custom_file.original_filename,
        stored_path=custom_file.stored_path,
        ext=custom_file.ext,
        uploaded_at=custom_file.uploaded_at,
        convert_to_pdf_at_package=custom_file.convert_to_pdf_at_package,
        preview_available=preview_available,
    )


def _map_doc_list_item(entry: DocumentListEntry) -> DocumentListItemResponse:
    doc = entry.document
    return DocumentListItemResponse(
        id=doc.id,
        # Локализованные имя/код определения из пака; пустой словарь (пак не
        # найден) — фронт падает на свой i18n-словарь по def_id.
        name=entry.name or {},
        code=entry.code or {},
        status=str(doc.status),
        chosen_variant=doc.chosen_variant,
        last_compile_id=str(doc.last_compile_id) if doc.last_compile_id is not None else None,
        last_compile_at=None,  # Would come from compile repo — not wired here
        pages=None,
        warnings=0,
        errors=0,
        def_id=doc.def_id,
        owner=doc.owner,
        owner_name=entry.owner_name,
        source_file=entry.source_file,
        output_file=entry.output_file,
        engine=entry.engine,
        group=entry.group,
    )


def _map_doc_detail(
    doc: Document,
    resolution: GetDocumentOutput | None = None,
    *,
    custom_preview_available: bool | None = None,
) -> DocumentDetailResponse:
    # `resolution` — резолв определения/инстанса из GetDocumentUC (GET);
    # PATCH/upload/revert-ответы его не несут — фронт перечитывает детали
    # после мутации. `custom_preview_available` — явный override для
    # upload/revert (там уже известно, удался ли конверт-превью), иначе
    # берётся из `resolution`, иначе консервативный дефолт (только .pdf).
    co = doc.checks_override
    if custom_preview_available is not None:
        preview_available = custom_preview_available
        signing_available = doc.custom_file is None or doc.custom_file.ext == ".pdf" or custom_preview_available
    elif resolution is not None:
        preview_available = resolution.custom_preview_available
        signing_available = resolution.signing_available
    else:
        preview_available = doc.custom_file is not None and doc.custom_file.ext == ".pdf"
        signing_available = doc.custom_file is None or doc.custom_file.ext == ".pdf"
    return DocumentDetailResponse(
        id=doc.id,
        status=str(doc.status),
        chosen_variant=doc.chosen_variant,
        last_compile_id=str(doc.last_compile_id) if doc.last_compile_id is not None else None,
        checks_override={
            "disabled_categories": list(co.disabled_categories),
            "disabled": list(co.disabled),
            "enabled": list(co.enabled),
            "severity_override": {k: str(v) for k, v in co.severity_override.items()},
        },
        name=(resolution.name if resolution is not None else None) or {},
        code=(resolution.code if resolution is not None else None) or {},
        source_file=resolution.source_file if resolution is not None else None,
        output_file=resolution.output_file if resolution is not None else None,
        gost_ref=resolution.gost_ref if resolution is not None else None,
        engine=resolution.engine if resolution is not None else None,
        preview_file=resolution.preview_file if resolution is not None else None,
        preview_updated_at=resolution.preview_updated_at if resolution is not None else None,
        custom_file=_map_custom_file(doc.custom_file, preview_available),
        signing_available=signing_available,
    )


@router.get(
    "/projects/{project_id}/documents",
    response_model=list[DocumentListItemResponse],
)
async def list_documents(
    project_id: UUID,
    uc: FromDishka[ListDocumentsUC],
) -> list[DocumentListItemResponse]:
    try:
        result = await uc.execute(ListDocumentsInput(project_id=project_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [_map_doc_list_item(e) for e in result.entries]


@router.get(
    "/projects/{project_id}/documents/{doc_id}",
    response_model=DocumentDetailResponse,
)
async def get_document(
    project_id: UUID,
    doc_id: str,
    uc: FromDishka[GetDocumentUC],
) -> DocumentDetailResponse:
    try:
        result = await uc.execute(GetDocumentInput(project_id=project_id, doc_id=doc_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _map_doc_detail(result.document, result)


@router.patch(
    "/projects/{project_id}/documents/{doc_id}",
    response_model=DocumentDetailResponse,
)
async def update_document(
    project_id: UUID,
    doc_id: str,
    body: UpdateDocumentRequest,
    uc: FromDishka[UpdateDocumentUC],
) -> DocumentDetailResponse:
    checks_override: ChecksOverride | None = None
    if body.checks_override is not None:
        raw = body.checks_override
        checks_override = ChecksOverride(
            disabled_categories=tuple(raw.get("disabled_categories", [])),
            disabled=tuple(raw.get("disabled", [])),
            enabled=tuple(raw.get("enabled", [])),
            severity_override=raw.get("severity_override", {}),
        )

    # Determine chosen_variant: use sentinel to distinguish "not provided" from explicit None
    chosen_variant = body.chosen_variant if "chosen_variant" in body.model_fields_set else _MISSING

    try:
        inp = UpdateDocumentInput(
            project_id=project_id,
            doc_id=doc_id,
            checks_override=checks_override,
            chosen_variant=chosen_variant,  # type: ignore[arg-type]
        )
        result = await uc.execute(inp)
    except InvalidVariantError as exc:
        # Плохой запрос (неизвестный вариант / док без вариантов), не not-found.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _map_doc_detail(result.document)


@router.post(
    "/projects/{project_id}/documents/{doc_id}/custom-file",
    response_model=DocumentDetailResponse,
)
async def upload_custom_file(
    project_id: UUID,
    doc_id: str,
    uc: FromDishka[UploadCustomFileUC],
    file: UploadFile = File(...),
) -> DocumentDetailResponse:
    content = await file.read()
    try:
        result = await uc.execute(
            UploadCustomFileInput(
                project_id=project_id,
                doc_id=doc_id,
                filename=file.filename or doc_id,
                content=content,
            )
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _map_doc_detail(result.document, custom_preview_available=result.preview_generated)


@router.delete(
    "/projects/{project_id}/documents/{doc_id}/custom-file",
    response_model=DocumentDetailResponse,
)
async def revert_custom_file(
    project_id: UUID,
    doc_id: str,
    uc: FromDishka[RevertCustomFileUC],
    delete_file: bool = Query(False),
) -> DocumentDetailResponse:
    try:
        result = await uc.execute(
            RevertCustomFileInput(project_id=project_id, doc_id=doc_id, delete_uploaded_file=delete_file)
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _map_doc_detail(result.document, custom_preview_available=False)
