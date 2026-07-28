from __future__ import annotations

import json
from collections.abc import AsyncIterator
from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import StreamingResponse

from hse_doc_studio.api.schemas.checks import (
    CheckResultsResponse,
)
from hse_doc_studio.api.schemas.checks import (
    map_check_result as _map_check_result,
)
from hse_doc_studio.api.schemas.compile import (
    CancelCompileResponse,
    CompileDetailResponse,
    CompileListItemResponse,
    TriggerCompileResponse,
)
from hse_doc_studio.core.entities import CompileRecord
from hse_doc_studio.core.enums import CheckSeverity
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.value_objects import CheckResult
from hse_doc_studio.infra.compile.errors import CompileSetupError
from hse_doc_studio.use_cases.checks.get_check_results import (
    GetCheckResultsInput,
    GetCheckResultsUC,
)
from hse_doc_studio.use_cases.compile.cancel_compile import (
    CancelCompileInput,
    CancelCompileUC,
)
from hse_doc_studio.use_cases.compile.get_archived_pdf import (
    GetArchivedPdfInput,
    GetArchivedPdfUC,
)
from hse_doc_studio.use_cases.compile.get_compile import GetCompileInput, GetCompileUC
from hse_doc_studio.use_cases.compile.get_compile_stream import (
    GetCompileStreamInput,
    GetCompileStreamUC,
)
from hse_doc_studio.use_cases.compile.list_compiles import ListCompilesInput, ListCompilesUC
from hse_doc_studio.use_cases.compile.trigger_compile import TriggerCompileInput, TriggerCompileUC

router = APIRouter(route_class=DishkaRoute)


def _severity_counts(check_results: list[CheckResult]) -> tuple[int, int]:
    warnings = sum(1 for r in check_results if r.severity == CheckSeverity.warn)
    errors = sum(1 for r in check_results if r.severity == CheckSeverity.err)
    return warnings, errors


def _to_list_item(record: CompileRecord) -> CompileListItemResponse:
    warnings, errors = _severity_counts(record.check_results)
    return CompileListItemResponse(
        id=str(record.id),
        doc_id=record.doc_id,
        engine=str(record.engine),
        status=str(record.status),
        started_at=record.started_at,
        finished_at=record.finished_at,
        pages=record.pages,
        words=record.words,
        chars=record.chars,
        warnings=warnings,
        errors=errors,
    )


@router.post(
    "/projects/{project_id}/documents/{doc_id}/compile",
    response_model=TriggerCompileResponse,
    status_code=202,
)
async def trigger_compile(
    project_id: UUID,
    doc_id: str,
    uc: FromDishka[TriggerCompileUC],
) -> TriggerCompileResponse:
    try:
        result = await uc.execute(TriggerCompileInput(project_id=project_id, doc_id=doc_id))
    except CompileSetupError as exc:
        # Environmental failure (Docker missing / image not installed) — surface
        # as a structured 409 so the UI can offer install instead of treating
        # it as a regular build failure.
        raise HTTPException(status_code=409, detail=exc.to_dict()) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return TriggerCompileResponse(compile_id=str(result.compile_id))


@router.get(
    "/projects/{project_id}/documents/{doc_id}/compiles",
    response_model=list[CompileListItemResponse],
)
async def list_compiles(
    project_id: UUID,
    doc_id: str,
    uc: FromDishka[ListCompilesUC],
) -> list[CompileListItemResponse]:
    records = uc.execute(ListCompilesInput(project_id=project_id, doc_id=doc_id))
    return [_to_list_item(r) for r in records]


@router.get(
    "/projects/{project_id}/documents/{doc_id}/compiles/{compile_id}/pdf",
)
async def get_archived_pdf(
    project_id: UUID,
    doc_id: str,
    compile_id: UUID,
    uc: FromDishka[GetArchivedPdfUC],
) -> Response:
    """Serve a previously-archived compiled PDF (for visual diff)."""
    try:
        result = uc.execute(GetArchivedPdfInput(project_id=project_id, doc_id=doc_id, compile_id=compile_id))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(content=result.content, media_type="application/pdf")


@router.get(
    "/projects/{project_id}/documents/{doc_id}/compiles/{compile_id}",
    response_model=CompileDetailResponse,
)
async def get_compile(
    project_id: UUID,
    doc_id: str,
    compile_id: UUID,
    uc: FromDishka[GetCompileUC],
) -> CompileDetailResponse:
    record = uc.execute(GetCompileInput(project_id=project_id, compile_id=compile_id))
    if record is None:
        raise HTTPException(status_code=404, detail=f"Compile record not found: {compile_id}")
    warnings, errors = _severity_counts(record.check_results)
    return CompileDetailResponse(
        id=str(record.id),
        doc_id=record.doc_id,
        engine=str(record.engine),
        status=str(record.status),
        started_at=record.started_at,
        finished_at=record.finished_at,
        log=record.log or "",
        pages=record.pages,
        words=record.words,
        chars=record.chars,
        warnings=warnings,
        errors=errors,
        check_results=[_map_check_result(r).model_dump() for r in record.check_results],
    )


@router.get(
    "/projects/{project_id}/compiles/{compile_id}/stream",
)
async def get_compile_stream(
    project_id: UUID,
    compile_id: UUID,
    uc: FromDishka[GetCompileStreamUC],
) -> StreamingResponse:
    # GetCompileStreamUC needs doc_id — use a placeholder since the route doesn't include it.
    # The real lookup is by compile_id within the project, doc_id is used only for searching.
    # We set doc_id to empty string; the UC finds by project_id + compile_id.
    inp = GetCompileStreamInput(project_id=project_id, doc_id="", compile_id=compile_id)
    try:
        stream = await uc.execute(inp)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    async def _event_stream() -> AsyncIterator[str]:
        done_payload: dict[str, object] = {
            "status": "success",
            "pages": None,
            "warnings": 0,
            "errors": 0,
        }
        async for line in stream:
            if line.startswith("__STATUS__:"):
                done_payload["status"] = line.split(":", 1)[1] or "success"
                continue
            # JSON-encode so the client can do JSON.parse on event.data.
            yield f"event: log\ndata: {json.dumps(line, ensure_ascii=False)}\n\n"
        yield f"event: done\ndata: {json.dumps(done_payload)}\n\n"

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable proxy buffering when behind nginx
        },
    )


@router.post(
    "/projects/{project_id}/compiles/{compile_id}/cancel",
    response_model=CancelCompileResponse,
)
async def cancel_compile(
    project_id: UUID,
    compile_id: UUID,
    uc: FromDishka[CancelCompileUC],
) -> CancelCompileResponse:
    try:
        result = await uc.execute(CancelCompileInput(project_id=project_id, compile_id=compile_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return CancelCompileResponse(
        cancelled_task=result.cancelled_task,
        record_finalised=result.record_finalised,
    )


@router.get(
    "/projects/{project_id}/documents/{doc_id}/checks",
    response_model=CheckResultsResponse,
)
async def get_checks(
    project_id: UUID,
    doc_id: str,
    uc: FromDishka[GetCheckResultsUC],
    scope: str | None = Query(
        default=None,
        description="Pass 'document' to keep only findings in this document's file and its imports.",
    ),
) -> CheckResultsResponse:
    try:
        result = await uc.execute(
            GetCheckResultsInput(
                project_id=project_id,
                doc_id=doc_id,
                scope_to_document=scope == "document",
            )
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return CheckResultsResponse(
        doc_id=doc_id,
        compile_id=str(result.compile_id) if result.compile_id is not None else None,
        results=[_map_check_result(r) for r in result.results],
    )
