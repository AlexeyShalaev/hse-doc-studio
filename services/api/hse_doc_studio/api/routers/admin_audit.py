"""`/api/admin/audit`: чтение журнала аудита установки. Записывать в журнал через API нельзя.

Журнал листается непрозрачным курсором (новые первыми), фильтры сочетаются по И. Имя действовавшего и
подпись цели сервер отдаёт в самой строке.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from pydantic import StringConstraints

from hse_doc_studio.api.schemas.admin import (
    CURSOR_MAX,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    decode_cursor,
    encode_cursor,
)
from hse_doc_studio.api.schemas.session import AdminAuditActor, AdminAuditEvent, AdminAuditPage
from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.identity.entities import AuditQuery, AuditView
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.listing import SEARCH_MAX, search_text
from hse_doc_studio.use_cases.admin.audit import ListAuditUC

router = APIRouter()

_NO_STORE = {"Cache-Control": "no-store"}
_Category = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,31}$")]
_Action = Annotated[str, StringConstraints(min_length=1, max_length=128)]


def _event(view: AuditView) -> AdminAuditEvent:
    entry = view.entry
    return AdminAuditEvent(
        id=entry.id,
        at=entry.at,
        action=entry.action,
        actor_id=entry.actor_id,
        actor=AdminAuditActor(id=view.actor.id, name=view.actor.name, email=view.actor.email) if view.actor else None,
        target=entry.target,
        target_label=view.target_label,
        details=dict(entry.details),
    )


def _kinds(action: list[str] | None) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Старые клиенты присылают в `action` префикс с точкой (`admin.`): он читается как категория."""
    prefixes = tuple(a[:-1] for a in action or () if a.endswith("."))
    exact = tuple(a for a in action or () if not a.endswith("."))
    return prefixes, exact


@router.get("/audit", response_model=AdminAuditPage)
async def list_audit(  # noqa: PLR0913 — фильтры журнала приходят отдельными параметрами запроса
    request: Request,
    response: Response,
    actor_id: Annotated[str | None, Query(max_length=64)] = None,
    category: Annotated[
        list[_Category] | None, Query(description="Префикс действия до точки: auth, admin, org")
    ] = None,
    action: Annotated[list[_Action] | None, Query(description="Точное действие, можно несколько")] = None,
    target: Annotated[str | None, Query(max_length=256)] = None,
    since_at: Annotated[datetime | None, Query(alias="from", description="Включительно")] = None,
    until_at: Annotated[datetime | None, Query(alias="to", description="Не включая")] = None,
    since: Annotated[datetime | None, Query(description="Старое имя `from`")] = None,
    until: Annotated[datetime | None, Query(description="Старое имя `to`")] = None,
    q: Annotated[str | None, Query(max_length=SEARCH_MAX)] = None,
    cursor: Annotated[str | None, Query(max_length=CURSOR_MAX)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> AdminAuditPage:
    actor = current_actor()
    if actor is None:
        raise IdentityError(IdentityErrorCode.auth_required)
    try:
        before_id = decode_cursor(cursor) if cursor else None
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid cursor") from exc
    response.headers.update(_NO_STORE)
    prefixes, exact = _kinds(action)
    uc = await request.state.dishka_container.get(ListAuditUC)
    page = await uc.execute(
        actor,
        AuditQuery(
            actor_id=actor_id,
            categories=(*(category or ()), *prefixes),
            actions=exact,
            target=target,
            since=since_at or since,
            until=until_at or until,
            q=search_text(q),
            before_id=before_id,
            limit=limit,
        ),
    )
    return AdminAuditPage(
        items=[_event(e) for e in page.items],
        next_cursor=encode_cursor(page.next_before_id) if page.next_before_id is not None else None,
        total_estimate=page.total_estimate,
    )
