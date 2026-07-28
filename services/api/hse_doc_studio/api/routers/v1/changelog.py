from __future__ import annotations

from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException, Query

from hse_doc_studio.api.schemas.changelog import (
    AddChangeLogEntryRequest,
    ChangeLogEntryResponse,
)
from hse_doc_studio.core.entities import ChangeLogEntry
from hse_doc_studio.core.enums import ChangeLogKind
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.use_cases.changelog.add_changelog_entry import (
    AddChangelogEntryInput,
    AddChangelogEntryUC,
)
from hse_doc_studio.use_cases.changelog.list_changelog import (
    ListChangelogInput,
    ListChangelogUC,
)

router = APIRouter(route_class=DishkaRoute)


def _map_entry(entry: ChangeLogEntry) -> ChangeLogEntryResponse:
    return ChangeLogEntryResponse(
        id=str(entry.id),
        at=entry.at,
        kind=str(entry.kind),
        doc_id=entry.doc_id,
        summary=entry.summary,
        note=entry.note,
    )


@router.get(
    "/projects/{project_id}/changelog",
    response_model=list[ChangeLogEntryResponse],
)
async def list_changelog(
    project_id: UUID,
    uc: FromDishka[ListChangelogUC],
    doc_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[ChangeLogEntryResponse]:
    try:
        result = await uc.execute(
            ListChangelogInput(
                project_id=project_id,
                doc_id=doc_id,
                limit=limit,
                offset=offset,
            )
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [_map_entry(e) for e in result.entries]


@router.post(
    "/projects/{project_id}/changelog",
    response_model=ChangeLogEntryResponse,
    status_code=201,
)
async def add_changelog_entry(
    project_id: UUID,
    body: AddChangeLogEntryRequest,
    uc: FromDishka[AddChangelogEntryUC],
) -> ChangeLogEntryResponse:
    try:
        kind = ChangeLogKind(body.kind)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Unknown changelog kind: {body.kind}") from exc

    try:
        result = await uc.execute(
            AddChangelogEntryInput(
                project_id=project_id,
                summary=body.summary,
                doc_id=body.doc_id,
                kind=kind,
                note=body.note,
            )
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _map_entry(result.entry)
