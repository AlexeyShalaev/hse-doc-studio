"""`/api/admin/audit`: чтение журнала аудита установки. Записывать в журнал через API нельзя."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from hse_doc_studio.api.schemas.admin import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from hse_doc_studio.api.schemas.session import AdminAuditEvent, AdminAuditPage
from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.identity.entities import AuditEntry, AuditQuery
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.use_cases.admin.audit import ListAuditUC

router = APIRouter()

_NO_STORE = {"Cache-Control": "no-store"}


def _event(entry: AuditEntry) -> AdminAuditEvent:
    return AdminAuditEvent(
        id=entry.id,
        at=entry.at,
        action=entry.action,
        actor_id=entry.actor_id,
        target=entry.target,
        details=dict(entry.details),
    )


@router.get("/audit", response_model=AdminAuditPage)
async def list_audit(
    request: Request,
    response: Response,
    actor_id: Annotated[str | None, Query(max_length=64)] = None,
    action: Annotated[str | None, Query(max_length=128, description="Префикс действия: `admin.`, `auth.login`")] = None,
    target: Annotated[str | None, Query(max_length=256)] = None,
    since: Annotated[datetime | None, Query(description="Включительно")] = None,
    until: Annotated[datetime | None, Query(description="Не включая")] = None,
    cursor: Annotated[str | None, Query(pattern=r"^[0-9]{1,18}$")] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> AdminAuditPage:
    actor = current_actor()
    if actor is None:
        raise IdentityError(IdentityErrorCode.auth_required)
    response.headers.update(_NO_STORE)
    uc = await request.state.dishka_container.get(ListAuditUC)
    page = await uc.execute(
        actor,
        AuditQuery(
            actor_id=actor_id,
            action_prefix=action,
            target=target,
            since=since,
            until=until,
            before_id=int(cursor) if cursor else None,
            limit=limit,
        ),
    )
    return AdminAuditPage(
        items=[_event(e) for e in page.items],
        next_cursor=str(page.next_before_id) if page.next_before_id is not None else None,
    )
