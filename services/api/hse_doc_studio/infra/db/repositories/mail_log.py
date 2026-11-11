"""Журнал писем в Postgres (docs/design/mail-log.md, 5.1): дозапись мимо ambient, страница ключом id, сводка.

Срок хранения держит источник `mail_log` движка жизненного цикла (`server_lifecycle.py`), стирание и выгрузку
человека `SqlUserLifecycle`; здесь их нет.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ColumnElement, func, select, text

from hse_doc_studio.core.mail.journal import (
    MailCause,
    MailLogCounts,
    MailLogEntry,
    MailLogPage,
    MailLogQuery,
    MailParams,
    MailStatus,
)
from hse_doc_studio.infra.db.listing import contains
from hse_doc_studio.infra.db.orm.mail_log import MailLogRow
from hse_doc_studio.infra.db.session import SessionProvider

# Оценка числа строк по статистике таблицы: -1, пока таблицу ни разу не анализировали (тогда оценки нет).
_ESTIMATE = text("SELECT reltuples::bigint FROM pg_class WHERE oid = to_regclass('mail_log')")


def _project_uuid(value: str | None) -> uuid.UUID | None:
    return uuid.UUID(value) if value is not None else None


def _row(entry: MailLogEntry) -> MailLogRow:
    return MailLogRow(
        at=entry.at,
        duration_ms=entry.duration_ms,
        template=entry.template,
        lang=entry.lang,
        to_email=entry.to_email,
        to_user_id=entry.to_user_id,
        subject=entry.subject,
        status=entry.status.value,
        reason=entry.reason,
        smtp_code=entry.smtp_code,
        error_text=entry.error_text,
        message_id=entry.message_id,
        attempts=entry.attempts,
        cause=entry.cause.value,
        actor_user_id=entry.actor_user_id,
        task=entry.task,
        origin=entry.origin,
        request_id=entry.request_id,
        project_id=_project_uuid(entry.project_id),
        ref_kind=entry.ref_kind,
        ref_id=entry.ref_id,
        params=entry.params.to_json(),
        template_digest=entry.template_digest,
    )


def _entry(row: MailLogRow) -> MailLogEntry:
    return MailLogEntry(
        id=row.id,
        at=row.at,
        duration_ms=row.duration_ms,
        template=row.template,
        lang=row.lang,
        to_email=row.to_email,
        to_user_id=row.to_user_id,
        subject=row.subject,
        status=MailStatus(row.status),
        reason=row.reason,
        smtp_code=row.smtp_code,
        error_text=row.error_text,
        message_id=row.message_id,
        attempts=row.attempts,
        cause=MailCause(row.cause),
        actor_user_id=row.actor_user_id,
        task=row.task,
        origin=row.origin,
        request_id=row.request_id,
        project_id=str(row.project_id) if row.project_id is not None else None,
        ref_kind=row.ref_kind,
        ref_id=row.ref_id,
        params=MailParams.from_json(row.params if isinstance(row.params, dict) else {}),
        template_digest=row.template_digest,
    )


def _conditions(query: MailLogQuery) -> list[ColumnElement[bool]]:
    return [*_what(query), *_whom(query), *_window(query)]


def _what(query: MailLogQuery) -> list[ColumnElement[bool]]:
    """Вид письма, итог и причина."""
    log = MailLogRow
    conditions: list[ColumnElement[bool]] = []
    if query.templates:
        conditions.append(log.template.in_(query.templates))
    if query.statuses:
        conditions.append(log.status.in_([status.value for status in query.statuses]))
    if query.reason is not None:
        conditions.append(log.reason == query.reason)
    return conditions


def _whom(query: MailLogQuery) -> list[ColumnElement[bool]]:
    """Получатель, проект и поиск по адресу и теме."""
    log = MailLogRow
    conditions: list[ColumnElement[bool]] = []
    if query.recipient_id is not None:
        conditions.append(log.to_user_id == query.recipient_id)
    if query.recipient is not None:
        # Точный адрес без учёта регистра: условие совпадает с выражением индекса `lower(to_email)`.
        conditions.append(func.lower(log.to_email) == query.recipient.strip().lower())
    if query.project_id is not None:
        conditions.append(log.project_id == _project_uuid(query.project_id))
    if query.q:
        conditions.append(contains(query.q, log.to_email, log.subject))
    return conditions


def _window(query: MailLogQuery) -> list[ColumnElement[bool]]:
    """Период и ключ страницы `before_id`."""
    log = MailLogRow
    conditions: list[ColumnElement[bool]] = []
    if query.since is not None:
        conditions.append(log.at >= query.since)
    if query.until is not None:
        conditions.append(log.at < query.until)
    if query.before_id is not None:
        conditions.append(log.id < query.before_id)
    return conditions


class SqlMailLogRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def add(self, entry: MailLogEntry) -> int:
        row = _row(entry)
        async with self._sessions.own() as db:
            db.add(row)
            await db.flush()
            return row.id

    async def page(self, query: MailLogQuery) -> MailLogPage:
        limit = max(1, query.limit)
        stmt = select(MailLogRow).where(*_conditions(query)).order_by(MailLogRow.id.desc()).limit(limit + 1)
        async with self._sessions.use() as db:
            rows = list((await db.execute(stmt)).scalars())
            estimate = None if query.filtered else (await db.execute(_ESTIMATE)).scalar_one_or_none()
        items = [_entry(row) for row in rows[:limit]]
        return MailLogPage(
            items=items,
            next_before_id=items[-1].id if len(rows) > limit else None,
            total_estimate=int(estimate) if estimate is not None and estimate >= 0 else None,
        )

    async def get(self, entry_id: int) -> MailLogEntry | None:
        async with self._sessions.use() as db:
            row = await db.get(MailLogRow, entry_id)
            return _entry(row) if row is not None else None

    async def summary(self, since: datetime) -> MailLogCounts:
        log = MailLogRow
        by_status = select(log.status, func.count()).where(log.at >= since).group_by(log.status)
        last = (
            select(log.at, log.reason)
            .where(log.status == MailStatus.failed.value, log.at >= since)
            .order_by(log.at.desc(), log.id.desc())
            .limit(1)
        )
        async with self._sessions.use() as db:
            counts = {status: int(count) for status, count in (await db.execute(by_status)).all()}
            failure = (await db.execute(last)).first()
        return MailLogCounts(
            sent=counts.get(MailStatus.sent.value, 0),
            failed=counts.get(MailStatus.failed.value, 0),
            not_sent=counts.get(MailStatus.not_sent.value, 0),
            suppressed=counts.get(MailStatus.suppressed.value, 0),
            last_failure_at=failure[0] if failure is not None else None,
            last_failure_reason=failure[1] if failure is not None else None,
        )
