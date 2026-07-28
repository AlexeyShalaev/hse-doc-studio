from __future__ import annotations

from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from hse_doc_studio.api.schemas.catalog import (
    SubmissionDocItemResponse,
    SubmissionExtraItemResponse,
    SubmissionProfileResponse,
)
from hse_doc_studio.api.schemas.submission import (
    CreateSubmissionRequest,
    CustomDocPreviewItemResponse,
    SubmissionRecordResponse,
)
from hse_doc_studio.core.catalog import ExtraSubmissionItem, SubmissionDocItem, SubmissionProfile
from hse_doc_studio.core.entities import PackSubmissionRecord
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.infra.submission.assembler import is_archive_format_available
from hse_doc_studio.use_cases.submission.create_submission import (
    CreateSubmissionInput,
    CreateSubmissionUC,
)
from hse_doc_studio.use_cases.submission.get_submission_file import (
    GetSubmissionFileInput,
    GetSubmissionFileUC,
)
from hse_doc_studio.use_cases.submission.get_submission_profiles import (
    GetSubmissionProfilesInput,
    GetSubmissionProfilesUC,
)
from hse_doc_studio.use_cases.submission.list_submissions import (
    ListSubmissionsInput,
    ListSubmissionsUC,
)
from hse_doc_studio.use_cases.submission.preview_custom_docs import (
    CustomDocPreviewItem,
    PreviewSubmissionCustomDocsInput,
    PreviewSubmissionCustomDocsUC,
)

router = APIRouter(route_class=DishkaRoute)


def _map_custom_doc_preview(item: CustomDocPreviewItem) -> CustomDocPreviewItemResponse:
    return CustomDocPreviewItemResponse(
        doc_id=item.doc_id,
        doc_name=item.doc_name,
        original_filename=item.original_filename,
        ext=item.ext,
        convertible=item.convertible,
        default_decision=item.default_decision,
    )


def _map_profile(profile: SubmissionProfile) -> SubmissionProfileResponse:
    return SubmissionProfileResponse(
        id=profile.id,
        name=profile.name,
        description=profile.description,
        items=[
            SubmissionDocItemResponse(
                doc_id=item.doc_id,
                signatures=list(item.signatures),
                skip_if_nda=item.skip_if_nda,
                supported_kinds=list(item.supported_kinds),
            )
            for item in profile.items
        ],
        extra_items=[
            SubmissionExtraItemResponse(
                source=extra.source,
                output_name=extra.output_name,
                format=extra.format,
                supported_kinds=list(extra.supported_kinds),
            )
            for extra in profile.extra_items
        ],
    )


def _map_record(
    record: PackSubmissionRecord,
    size_bytes: int | None = None,
    profile_name: dict[str, str] | None = None,
) -> SubmissionRecordResponse:
    return SubmissionRecordResponse(
        id=str(record.id),
        profile_id=record.profile_id,
        profile_name=profile_name,
        created_at=record.created_at,
        output_path=str(record.output_path),
        output_dir=str(record.output_dir) if record.output_dir is not None else None,
        size_bytes=size_bytes,
        archive_format=record.archive_format,
        doc_count=len(record.doc_items),
    )


@router.get(
    "/projects/{project_id}/submissions/profiles",
    response_model=list[SubmissionProfileResponse],
)
async def get_submission_profiles(
    project_id: UUID,
    uc: FromDishka[GetSubmissionProfilesUC],
) -> list[SubmissionProfileResponse]:
    try:
        result = await uc.execute(GetSubmissionProfilesInput(project_id=project_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [_map_profile(p) for p in result.profiles]


@router.get(
    "/projects/{project_id}/submissions/preflight",
    response_model=list[CustomDocPreviewItemResponse],
)
async def get_submission_preflight(
    project_id: UUID,
    uc: FromDishka[PreviewSubmissionCustomDocsUC],
    profile_id: str = Query(...),
    author_slug: str | None = Query(None),
) -> list[CustomDocPreviewItemResponse]:
    try:
        result = await uc.execute(
            PreviewSubmissionCustomDocsInput(project_id=project_id, profile_id=profile_id, author_slug=author_slug)
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [_map_custom_doc_preview(item) for item in result.items]


@router.post(
    "/projects/{project_id}/submissions",
    response_model=SubmissionRecordResponse,
    status_code=201,
)
async def create_submission(
    project_id: UUID,
    body: CreateSubmissionRequest,
    uc: FromDishka[CreateSubmissionUC],
) -> SubmissionRecordResponse:
    doc_items = [SubmissionDocItem(doc_id=item.doc_id, signatures=tuple(item.signatures)) for item in body.items]
    extra_items = [
        ExtraSubmissionItem(source=item.source, output_name=item.output_name, format=item.format)
        for item in body.extra_items
    ]
    if not is_archive_format_available(body.archive_format):
        raise HTTPException(
            status_code=400,
            detail=f"Archive format {body.archive_format!r} is not available on this host (external tool missing)",
        )
    inp = CreateSubmissionInput(
        project_id=project_id,
        profile_id=body.profile_id,
        items=doc_items,
        extra_items=extra_items,
        archive_format=body.archive_format,
        author_slug=body.author_slug,
        custom_doc_decisions=body.custom_doc_decisions,
    )
    try:
        result = await uc.execute(inp)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # size_bytes is left unset here: the UI invalidates and refetches the list
    # right after this returns, and the list endpoint stats the archive for size.
    return _map_record(result.submission)


@router.get(
    "/projects/{project_id}/submissions",
    response_model=list[SubmissionRecordResponse],
)
async def list_submissions(
    project_id: UUID,
    uc: FromDishka[ListSubmissionsUC],
) -> list[SubmissionRecordResponse]:
    try:
        result = await uc.execute(ListSubmissionsInput(project_id=project_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [_map_record(item.record, item.size_bytes, item.profile_name) for item in result.items]


_ARCHIVE_MEDIA_TYPES = (
    (".zip", "application/zip"),
    (".tar.gz", "application/gzip"),
    (".7z", "application/x-7z-compressed"),
    (".rar", "application/vnd.rar"),
)


def _archive_media_type(name: str) -> str:
    for ext, media_type in _ARCHIVE_MEDIA_TYPES:
        if name.endswith(ext):
            return media_type
    return "application/octet-stream"


@router.get("/projects/{project_id}/submissions/{submission_id}/download")
async def download_submission(
    project_id: UUID,
    submission_id: UUID,
    uc: FromDishka[GetSubmissionFileUC],
) -> FileResponse:
    try:
        result = await uc.execute(GetSubmissionFileInput(project_id=project_id, submission_id=submission_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FileResponse(
        path=str(result.path),
        media_type=_archive_media_type(result.download_name),
        filename=result.download_name,
    )
