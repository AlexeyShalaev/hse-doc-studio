"""`/api/admin/mail-log`: журнал писем (docs/design/mail-log.md, 6). Только чтение, гард задаёт `make_admin_router`.

Список листается непрозрачным курсором (новые сверху, как «Аудит»), фильтры сочетаются по И, лишний параметр
запроса даёт 422. Карточка отдаёт письмо, перерисованное без ссылок и сообщений людей; сводка считает итоги за сутки.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import StringConstraints

from hse_doc_studio.api.schemas.admin import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, cursor_param, encode_cursor
from hse_doc_studio.api.schemas.mail_log import (
    AdminMailLogDetail,
    AdminMailLogEntry,
    AdminMailLogFailure,
    AdminMailLogLastFailure,
    AdminMailLogPage,
    AdminMailLogPreview,
    AdminMailLogProject,
    AdminMailLogRef,
    AdminMailLogSummary,
    AdminPersonRef,
    MailStatusName,
)
from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.listing import SEARCH_MAX, search_text
from hse_doc_studio.core.mail.journal import TEMPLATE_MAX, MailLogQuery, MailStatus
from hse_doc_studio.core.mail.ports import MailPerson
from hse_doc_studio.use_cases.mail.log import (
    GetMailLogEntryUC,
    ListMailLogUC,
    MailLogSummaryUC,
    MailLogView,
)

router = APIRouter()

_NO_STORE = {"Cache-Control": "no-store"}
_Template = Annotated[str, StringConstraints(pattern=rf"^[a-z_]{{1,{TEMPLATE_MAX}}}$")]
# Причина или класс сбоя (`mail_log.reason`, varchar(32)).
_Reason = Annotated[str, StringConstraints(pattern=r"^[a-z_]{1,32}$")]
_LIST_PARAMS = frozenset(
    {"template", "status", "reason", "recipient_id", "recipient", "project_id", "from", "to", "q", "cursor", "limit"}
)
# Строка журнала не длиннее `id` из bigint: больший id не найдётся, а не уронит запрос.
_ID_MAX = 2**63 - 1


def _actor() -> Actor:
    actor = current_actor()
    if actor is None:
        raise IdentityError(IdentityErrorCode.auth_required)
    return actor


def _invalid(loc: str, msg: str) -> RequestValidationError:
    return RequestValidationError([{"type": "value_error", "loc": ("query", loc), "msg": msg}])


def _only_known_params(request: Request) -> None:
    """Лишний параметр списка это ошибка клиента (опечатка в фильтре), а не молча весь журнал."""
    extra = sorted(set(request.query_params) - _LIST_PARAMS)
    if extra:
        raise _invalid(extra[0], "Unknown query parameter")


def _person(person: MailPerson | None) -> AdminPersonRef | None:
    return AdminPersonRef(id=person.id, name=person.name, email=person.email) if person is not None else None


def _entry(view: MailLogView) -> AdminMailLogEntry:
    entry = view.entry
    assert entry.id is not None  # noqa: S101 — строка из хранилища всегда с id
    failed = entry.status is MailStatus.failed
    return AdminMailLogEntry(
        id=entry.id,
        at=entry.at,
        template=entry.template,
        template_known=entry.template_known,
        lang="en" if entry.lang == "en" else "ru",
        to_email=entry.to_email,
        to_user=_person(view.to_user),
        subject=entry.subject,
        status=entry.status.value,
        reason=entry.reason,
        failure=AdminMailLogFailure(smtp_code=entry.smtp_code, text=entry.error_text) if failed else None,
        message_id=entry.message_id,
        attempts=entry.attempts,
        duration_ms=entry.duration_ms,
        cause=entry.cause.value,
        actor=_person(view.actor),
        task=entry.task,
        origin=entry.origin,
        project=(
            AdminMailLogProject(id=UUID(entry.project_id), name=view.project_name)
            if entry.project_id is not None
            else None
        ),
        ref=AdminMailLogRef(kind=entry.ref_kind, id=entry.ref_id) if entry.ref_kind and entry.ref_id else None,
    )


@router.get("/mail-log", response_model=AdminMailLogPage, dependencies=[Depends(_only_known_params)])
async def list_mail_log(  # noqa: PLR0913 — фильтры журнала приходят отдельными параметрами запроса
    request: Request,
    response: Response,
    template: Annotated[list[_Template] | None, Query(description="Вид письма, можно несколько")] = None,
    status: Annotated[list[MailStatusName] | None, Query(description="Итог, можно несколько")] = None,
    reason: Annotated[_Reason | None, Query(description="Причина или класс сбоя")] = None,
    recipient_id: Annotated[str | None, Query(min_length=1, max_length=64, description="id получателя")] = None,
    recipient: Annotated[
        str | None, Query(min_length=1, max_length=320, description="Адрес получателя без учёта регистра")
    ] = None,
    project_id: UUID | None = None,
    since: Annotated[datetime | None, Query(alias="from", description="Включительно")] = None,
    until: Annotated[datetime | None, Query(alias="to", description="Не включая")] = None,
    q: Annotated[str | None, Query(max_length=SEARCH_MAX, description="Подстрока адреса или темы")] = None,
    before_id: Annotated[int | None, Depends(cursor_param)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> AdminMailLogPage:
    if since is not None and until is not None and since > until:
        raise _invalid("from", "'from' is later than 'to'")
    response.headers.update(_NO_STORE)
    uc = await request.state.dishka_container.get(ListMailLogUC)
    page = await uc.execute(
        _actor(),
        MailLogQuery(
            templates=tuple(dict.fromkeys(template or ())),
            statuses=tuple(MailStatus(s) for s in dict.fromkeys(status or ())),
            reason=reason,
            recipient_id=recipient_id,
            recipient=(recipient.strip() or None) if recipient is not None else None,
            project_id=str(project_id) if project_id is not None else None,
            since=since,
            until=until,
            q=search_text(q),
            before_id=before_id,
            limit=limit,
        ),
    )
    return AdminMailLogPage(
        items=[_entry(view) for view in page.items],
        next_cursor=encode_cursor(page.next_before_id) if page.next_before_id is not None else None,
        total_estimate=page.total_estimate,
    )


@router.get("/mail-log/summary", response_model=AdminMailLogSummary)
async def mail_log_summary(request: Request, response: Response) -> AdminMailLogSummary:
    response.headers.update(_NO_STORE)
    summary = await (await request.state.dishka_container.get(MailLogSummaryUC)).execute(_actor())
    counts = summary.counts
    last = (
        AdminMailLogLastFailure(at=counts.last_failure_at, reason=counts.last_failure_reason or "other")
        if counts.failed > 0 and counts.last_failure_at is not None
        else None
    )
    return AdminMailLogSummary(
        smtp_configured=summary.smtp_configured,
        window_hours=24,
        sent=counts.sent,
        failed=counts.failed,
        not_sent=counts.not_sent,
        suppressed=counts.suppressed,
        last_failure=last,
        retention_days=summary.retention_days,
    )


@router.get("/mail-log/{entry_id}", response_model=AdminMailLogDetail)
async def get_mail_log_entry(entry_id: int, request: Request, response: Response) -> AdminMailLogDetail:
    response.headers.update(_NO_STORE)
    uc = await request.state.dishka_container.get(GetMailLogEntryUC)
    detail = await uc.execute(_actor(), entry_id) if 1 <= entry_id <= _ID_MAX else None
    if detail is None:
        raise IdentityError(IdentityErrorCode.not_found)
    preview = detail.preview
    return AdminMailLogDetail(
        entry=_entry(detail.view),
        preview=AdminMailLogPreview(subject=preview.subject, html=preview.html, text=preview.text) if preview else None,
        link_hidden=detail.link_hidden,
        note_hidden=detail.note_hidden,
        rerendered=detail.rerendered,
    )
