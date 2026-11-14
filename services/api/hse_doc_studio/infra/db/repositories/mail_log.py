"""Журнал писем в Postgres (docs/design/mail-log.md, 5.1): дозапись мимо ambient, страница ключом id, сводка.

Срок хранения держит источник `mail_log` движка жизненного цикла (`server_lifecycle.py`), стирание и выгрузку
человека `SqlUserLifecycle`; здесь их нет. Очередь автоповтора (`mail_retry`, раздел 14, V8) хранит запрос письма
шифртекстом шифра секретов установки и живёт до исхода.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Collection
from dataclasses import replace
from datetime import datetime, timedelta

import structlog
from sqlalchemy import ColumnElement, and_, delete, func, or_, select, text, update

from hse_doc_studio.core.git_sync.protocols import ISecretCipher
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.mail.journal import (
    MailAttempt,
    MailCause,
    MailLogCounts,
    MailLogEntry,
    MailLogPage,
    MailLogQuery,
    MailParams,
    MailRequest,
    MailRetryJob,
    MailStatus,
)
from hse_doc_studio.core.secrets import column_aad
from hse_doc_studio.infra.db.listing import contains
from hse_doc_studio.infra.db.orm.mail_log import MailLogRow, MailRetryRow
from hse_doc_studio.infra.db.session import SessionProvider

logger = structlog.get_logger(__name__)

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
        next_attempt_at=entry.next_attempt_at,
        last_attempt_at=entry.last_attempt_at,
        resent_from_id=entry.resent_from_id,
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
        next_attempt_at=row.next_attempt_at,
        last_attempt_at=row.last_attempt_at,
        resent_from_id=row.resent_from_id,
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
    if query.retrying is True:
        conditions.append(and_(log.status == MailStatus.failed.value, log.next_attempt_at.is_not(None)))
    elif query.retrying is False:
        conditions.append(or_(log.status != MailStatus.failed.value, log.next_attempt_at.is_(None)))
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


_AAD_TABLE = "mail_retry"
_AAD_COLUMN = "request_enc"


def _aad(entry_id: int) -> str:
    return column_aad(_AAD_TABLE, _AAD_COLUMN, entry_id)


class SqlMailLogRepository:
    def __init__(self, sessions: SessionProvider, cipher: ISecretCipher | None = None) -> None:
        self._sessions = sessions
        # Без шифра (тесты хранилища без ключей) автоповтор не ставится: запрос в открытом виде в базу не идёт.
        self._cipher = cipher

    def _seal(self, entry_id: int, request: MailRequest) -> str | None:
        if self._cipher is None:
            return None
        try:
            return self._cipher.encrypt(Secret(json.dumps(request.to_json())), aad=_aad(entry_id))
        except Exception:
            logger.warning("mail_retry_seal_failed", mail_log_id=entry_id, exc_info=True)
            return None

    def _open(self, entry_id: int, sealed: str) -> MailRequest | None:
        if self._cipher is None:
            return None
        try:
            data = json.loads(self._cipher.decrypt(sealed, aad=_aad(entry_id)).reveal())
            return MailRequest.from_json(data) if isinstance(data, dict) else None
        except Exception:
            logger.warning("mail_retry_unreadable", mail_log_id=entry_id, exc_info=True)
            return None

    async def add(self, entry: MailLogEntry, retry: MailRequest | None = None) -> int:
        row = _row(entry)
        async with self._sessions.own() as db:
            db.add(row)
            await db.flush()
            due = entry.next_attempt_at
            if retry is not None and due is not None:
                sealed = self._seal(row.id, retry)
                if sealed is not None:
                    db.add(MailRetryRow(entry_id=row.id, due_at=due, request_enc=sealed))
                else:
                    # Зашифровать нечем: повтор не обещаем, строка остаётся окончательным сбоем.
                    row.next_attempt_at = None
                await db.flush()
            return row.id

    async def claim_retries(self, now: datetime, lease: timedelta, limit: int) -> list[MailRetryJob]:
        stmt = (
            select(MailRetryRow, MailLogRow.attempts, MailLogRow.at)
            .join(MailLogRow, MailLogRow.id == MailRetryRow.entry_id)
            .where(MailRetryRow.due_at <= now)
            .order_by(MailRetryRow.due_at, MailRetryRow.entry_id)
            .limit(max(1, limit))
            .with_for_update(of=MailRetryRow, skip_locked=True)
        )
        async with self._sessions.own() as db:
            rows = (await db.execute(stmt)).all()
            if not rows:
                return []
            ids = [retry.entry_id for retry, _, _ in rows]
            await db.execute(update(MailRetryRow).where(MailRetryRow.entry_id.in_(ids)).values(due_at=now + lease))
            return [
                MailRetryJob(
                    entry_id=retry.entry_id,
                    attempts=int(attempts),
                    first_at=at,
                    request=self._open(retry.entry_id, retry.request_enc),
                )
                for retry, attempts, at in rows
            ]

    async def finish_attempt(self, entry_id: int, attempt: MailAttempt) -> None:
        async with self._sessions.own() as db:
            await db.execute(
                update(MailLogRow)
                .where(MailLogRow.id == entry_id)
                .values(
                    status=attempt.status.value,
                    reason=attempt.reason,
                    smtp_code=attempt.smtp_code,
                    error_text=attempt.error_text,
                    message_id=attempt.message_id,
                    duration_ms=attempt.duration_ms,
                    attempts=attempt.attempts,
                    last_attempt_at=attempt.tried_at,
                    next_attempt_at=attempt.next_attempt_at,
                )
            )
            if attempt.next_attempt_at is None:
                await db.execute(delete(MailRetryRow).where(MailRetryRow.entry_id == entry_id))
            else:
                await db.execute(
                    update(MailRetryRow).where(MailRetryRow.entry_id == entry_id).values(due_at=attempt.next_attempt_at)
                )

    async def resends_of(self, entry_id: int) -> list[MailLogEntry]:
        stmt = select(MailLogRow).where(MailLogRow.resent_from_id == entry_id).order_by(MailLogRow.id.desc())
        async with self._sessions.use() as db:
            return [_entry(row) for row in (await db.execute(stmt)).scalars()]

    async def resent_ok(self, entry_ids: Collection[int]) -> set[int]:
        if not entry_ids:
            return set()
        stmt = select(MailLogRow.resent_from_id).where(
            MailLogRow.resent_from_id.in_(list(entry_ids)), MailLogRow.status == MailStatus.sent.value
        )
        async with self._sessions.use() as db:
            return {int(value) for value in (await db.execute(stmt)).scalars() if value is not None}

    async def resend_candidates(self, query: MailLogQuery, since: datetime, limit: int) -> list[MailLogEntry]:
        log = MailLogRow
        unsent = or_(
            log.status == MailStatus.not_sent.value,
            and_(log.status == MailStatus.failed.value, log.next_attempt_at.is_(None)),
        )
        scope = replace(query, statuses=(), retrying=None, before_id=None)
        conditions = [*_what(scope), *_whom(scope), *_window(scope)]
        stmt = select(log).where(unsent, log.at >= since, *conditions).order_by(log.id).limit(max(1, limit))
        async with self._sessions.use() as db:
            return [_entry(row) for row in (await db.execute(stmt)).scalars()]

    async def last_attempt(self) -> MailLogEntry | None:
        log = MailLogRow
        tried = func.coalesce(log.last_attempt_at, log.at)
        stmt = (
            select(log)
            .where(log.status.in_((MailStatus.sent.value, MailStatus.failed.value)))
            .order_by(tried.desc(), log.id.desc())
            .limit(1)
        )
        async with self._sessions.use() as db:
            row = (await db.execute(stmt)).scalars().first()
            return _entry(row) if row is not None else None

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
        waiting = and_(log.status == MailStatus.failed.value, log.next_attempt_at.is_not(None))
        by_status = (
            select(log.status, waiting.label("waiting"), func.count())
            .where(log.at >= since)
            .group_by(log.status, waiting)
        )
        last = (
            select(log.at, log.reason)
            .where(log.status == MailStatus.failed.value, log.at >= since)
            .order_by(log.at.desc(), log.id.desc())
            .limit(1)
        )
        async with self._sessions.use() as db:
            counts: dict[str, int] = {}
            for status, is_waiting, count in (await db.execute(by_status)).all():
                key = "retrying" if is_waiting else status
                counts[key] = counts.get(key, 0) + int(count)
            failure = (await db.execute(last)).first()
        return MailLogCounts(
            sent=counts.get(MailStatus.sent.value, 0),
            failed=counts.get(MailStatus.failed.value, 0),
            not_sent=counts.get(MailStatus.not_sent.value, 0),
            suppressed=counts.get(MailStatus.suppressed.value, 0),
            retrying=counts.get("retrying", 0),
            last_failure_at=failure[0] if failure is not None else None,
            last_failure_reason=failure[1] if failure is not None else None,
        )
