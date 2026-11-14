"""Журнал писем в памяти: те же правила, что у `SqlMailLogRepository` (контракт в tests/contract)."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from hse_doc_studio.core.mail.journal import (
    MailAttempt,
    MailLogCounts,
    MailLogEntry,
    MailLogPage,
    MailLogQuery,
    MailRequest,
    MailRetryJob,
    MailStatus,
)


def _retrying(entry: MailLogEntry) -> bool:
    return entry.status is MailStatus.failed and entry.next_attempt_at is not None


def _matches(entry: MailLogEntry, query: MailLogQuery) -> bool:
    q = (query.q or "").lower()
    return (
        (not query.templates or entry.template in query.templates)
        and (not query.statuses or entry.status in query.statuses)
        and (query.reason is None or entry.reason == query.reason)
        and (query.retrying is None or _retrying(entry) is query.retrying)
        and (query.recipient_id is None or entry.to_user_id == query.recipient_id)
        and (query.recipient is None or entry.to_email.lower() == query.recipient.strip().lower())
        and (query.project_id is None or entry.project_id == query.project_id)
        and (query.since is None or entry.at >= query.since)
        and (query.until is None or entry.at < query.until)
        and (not q or q in entry.to_email.lower() or q in entry.subject.lower())
        and (query.before_id is None or (entry.id or 0) < query.before_id)
    )


@dataclass
class _Queued:
    due_at: datetime
    request: MailRequest | None


class InMemoryMailLogRepository:
    def __init__(self, *, retries: bool = True) -> None:
        self.entries: list[MailLogEntry] = []
        self._next_id = 1
        # Сбой записи для тестов диспетчера: следующая `add` бросит это исключение.
        self.fail_with: Exception | None = None
        # Очередь автоповтора; `retries=False` ведёт себя как хранилище без шифра (повтор не ставится).
        self.queue: dict[int, _Queued] = {}
        self._retries = retries

    async def add(self, entry: MailLogEntry, retry: MailRequest | None = None) -> int:
        if self.fail_with is not None:
            raise self.fail_with
        entry_id = self._next_id
        self._next_id += 1
        due = entry.next_attempt_at
        if retry is not None and due is not None and self._retries:
            self.queue[entry_id] = _Queued(due, retry)
        elif retry is not None and due is not None:
            # Как хранилище без шифра: повтор не обещаем.
            entry = replace(entry, next_attempt_at=None)
        self.entries.append(replace(entry, id=entry_id))
        return entry_id

    async def page(self, query: MailLogQuery) -> MailLogPage:
        limit = max(1, query.limit)
        found = [e for e in reversed(self.entries) if _matches(e, query)]
        items = found[:limit]
        return MailLogPage(
            items=items,
            next_before_id=items[-1].id if len(found) > limit else None,
            total_estimate=None if query.filtered else len(self.entries),
        )

    async def get(self, entry_id: int) -> MailLogEntry | None:
        return next((e for e in self.entries if e.id == entry_id), None)

    async def summary(self, since: datetime) -> MailLogCounts:
        window = [e for e in self.entries if e.at >= since]
        failures = sorted((e for e in window if e.status is MailStatus.failed), key=lambda e: (e.at, e.id or 0))
        last = failures[-1] if failures else None
        return MailLogCounts(
            sent=sum(e.status is MailStatus.sent for e in window),
            failed=sum(not _retrying(e) for e in failures),
            not_sent=sum(e.status is MailStatus.not_sent for e in window),
            suppressed=sum(e.status is MailStatus.suppressed for e in window),
            retrying=sum(_retrying(e) for e in failures),
            last_failure_at=last.at if last is not None else None,
            last_failure_reason=last.reason if last is not None else None,
        )

    async def claim_retries(self, now: datetime, lease: timedelta, limit: int) -> list[MailRetryJob]:
        due = sorted(((q.due_at, entry_id) for entry_id, q in self.queue.items() if q.due_at <= now))[: max(1, limit)]
        jobs: list[MailRetryJob] = []
        for _, entry_id in due:
            queued = self.queue[entry_id]
            queued.due_at = now + lease
            entry = await self.get(entry_id)
            if entry is None:
                del self.queue[entry_id]
                continue
            jobs.append(MailRetryJob(entry_id, entry.attempts, entry.at, queued.request))
        return jobs

    async def finish_attempt(self, entry_id: int, attempt: MailAttempt) -> None:
        for i, entry in enumerate(self.entries):
            if entry.id == entry_id:
                self.entries[i] = replace(
                    entry,
                    status=attempt.status,
                    reason=attempt.reason,
                    smtp_code=attempt.smtp_code,
                    error_text=attempt.error_text,
                    message_id=attempt.message_id,
                    duration_ms=attempt.duration_ms,
                    attempts=attempt.attempts,
                    last_attempt_at=attempt.tried_at,
                    next_attempt_at=attempt.next_attempt_at,
                )
        if attempt.next_attempt_at is None:
            self.queue.pop(entry_id, None)
        elif entry_id in self.queue:
            self.queue[entry_id].due_at = attempt.next_attempt_at

    async def resends_of(self, entry_id: int) -> list[MailLogEntry]:
        return [e for e in reversed(self.entries) if e.resent_from_id == entry_id]

    async def resent_ok(self, entry_ids: Collection[int]) -> set[int]:
        wanted = set(entry_ids)
        return {
            e.resent_from_id
            for e in self.entries
            if e.resent_from_id in wanted and e.resent_from_id is not None and e.status is MailStatus.sent
        }

    async def resend_candidates(self, query: MailLogQuery, since: datetime, limit: int) -> list[MailLogEntry]:
        scope = replace(query, statuses=(), retrying=None, before_id=None)
        found = [
            e
            for e in self.entries
            if _matches(e, scope)
            and e.at >= since
            and (e.status is MailStatus.not_sent or (e.status is MailStatus.failed and e.next_attempt_at is None))
        ]
        return found[: max(1, limit)]

    async def last_attempt(self) -> MailLogEntry | None:
        tried = [e for e in self.entries if e.status in (MailStatus.sent, MailStatus.failed)]
        return max(tried, key=lambda e: (e.tried_at, e.id or 0), default=None)
