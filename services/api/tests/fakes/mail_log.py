"""Журнал писем в памяти: те же правила, что у `SqlMailLogRepository` (контракт в tests/contract)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from hse_doc_studio.core.mail.journal import MailLogCounts, MailLogEntry, MailLogPage, MailLogQuery, MailStatus


def _matches(entry: MailLogEntry, query: MailLogQuery) -> bool:
    q = (query.q or "").lower()
    return (
        (not query.templates or entry.template in query.templates)
        and (not query.statuses or entry.status in query.statuses)
        and (query.reason is None or entry.reason == query.reason)
        and (query.recipient_id is None or entry.to_user_id == query.recipient_id)
        and (query.recipient is None or entry.to_email.lower() == query.recipient.strip().lower())
        and (query.project_id is None or entry.project_id == query.project_id)
        and (query.since is None or entry.at >= query.since)
        and (query.until is None or entry.at < query.until)
        and (not q or q in entry.to_email.lower() or q in entry.subject.lower())
        and (query.before_id is None or (entry.id or 0) < query.before_id)
    )


class InMemoryMailLogRepository:
    def __init__(self) -> None:
        self.entries: list[MailLogEntry] = []
        self._next_id = 1
        # Сбой записи для тестов диспетчера: следующая `add` бросит это исключение.
        self.fail_with: Exception | None = None

    async def add(self, entry: MailLogEntry) -> int:
        if self.fail_with is not None:
            raise self.fail_with
        entry_id = self._next_id
        self._next_id += 1
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
            failed=len(failures),
            not_sent=sum(e.status is MailStatus.not_sent for e in window),
            suppressed=sum(e.status is MailStatus.suppressed for e in window),
            last_failure_at=last.at if last is not None else None,
            last_failure_reason=last.reason if last is not None else None,
        )
