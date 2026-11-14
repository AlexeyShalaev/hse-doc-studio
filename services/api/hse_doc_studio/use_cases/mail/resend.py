"""Повтор писем из журнала (docs/design/mail-log.md, раздел 14): «Отправить ещё раз» и «Отправить неушедшие».

Повторяются только письма без ссылки с токеном: письмо собирается заново из безопасных параметров строки (V3) и
уходит новой строкой журнала с `origin=admin_resend` и ссылкой на исходную (V2). Перед отправкой общие правила
(`resend_block`: итог, токен, окно 72 часа, уже повторено, SMTP) и актуальность объекта (`IMailRelevance`, 14.2).
"""

from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum

import structlog

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.protocols import IAuditLog, IMailLogRepository
from hse_doc_studio.core.mail.journal import (
    RESEND_BATCH_LIMIT,
    RESEND_WINDOW,
    MailLogEntry,
    MailLogQuery,
    MailRequest,
    ResendBlock,
    resend_block,
    resend_request,
)
from hse_doc_studio.core.mail.ports import IMailRelevance
from hse_doc_studio.use_cases.admin.users import require_admin
from hse_doc_studio.use_cases.mail.dispatch import MailDispatcher, MailOutcome

logger = structlog.get_logger(__name__)

# Фоновые отправки «Отправить неушедшие»: цикл событий держит задачи слабо.
_BATCHES: set[asyncio.Task[None]] = set()


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ResendOutcome(StrEnum):
    sent = "sent"
    failed = "failed"
    # Временный сбой: письмо встало в очередь автоповтора (V6).
    retrying = "retrying"
    blocked = "blocked"


@dataclass(frozen=True)
class ResendResult:
    outcome: ResendOutcome
    blocked: ResendBlock | None = None
    entry_id: int | None = None
    # Причина или класс сбоя новой попытки.
    reason: str | None = None


@dataclass(frozen=True)
class ResendBatch:
    planned: int
    skipped: dict[str, int]
    started: bool
    limit: int = RESEND_BATCH_LIMIT


class ResendGate:
    """Можно ли отправить строку ещё раз: общие правила и актуальность объекта."""

    def __init__(
        self,
        log: IMailLogRepository,
        relevance: IMailRelevance,
        dispatcher: MailDispatcher,
        *,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._log = log
        self._relevance = relevance
        self._dispatcher = dispatcher
        self._clock = clock

    async def block(self, entry: MailLogEntry, *, resent: bool | None = None) -> ResendBlock | None:
        if resent is None:
            resent = entry.id is not None and entry.id in await self._log.resent_ok([entry.id])
        general = resend_block(entry, now=self._clock(), smtp_enabled=self._dispatcher.enabled, resent=resent)
        if general is not None:
            return general
        return await self._relevance.check(entry)


def _result(outcome: MailOutcome) -> ResendResult:
    if outcome.sent:
        kind = ResendOutcome.sent
    elif outcome.next_attempt_at is not None:
        kind = ResendOutcome.retrying
    else:
        kind = ResendOutcome.failed
    return ResendResult(kind, entry_id=outcome.entry_id, reason=outcome.reason)


class ResendMailUC:
    """«Отправить ещё раз» на карточке письма: сразу, в запросе; неактуальное письмо не уходит (`blocked`)."""

    def __init__(
        self,
        log: IMailLogRepository,
        gate: ResendGate,
        dispatcher: MailDispatcher,
        audit: IAuditLog,
        *,
        public_url: str | None,
    ) -> None:
        self._log = log
        self._gate = gate
        self._dispatcher = dispatcher
        self._audit = audit
        self._public_url = public_url

    async def execute(self, actor: Actor, entry_id: int) -> ResendResult | None:
        """None, если строки нет."""
        admin_id = require_admin(actor)
        entry = await self._log.get(entry_id)
        if entry is None:
            return None
        block = await self._gate.block(entry)
        if block is not None:
            return ResendResult(ResendOutcome.blocked, blocked=block)
        outcome = await self._dispatcher.send(resend_request(entry, self._public_url), resent_from_id=entry_id)
        result = _result(outcome)
        await self._audit.record(
            "mail.resent",
            actor_id=admin_id,
            target=str(entry_id),
            details={"entry_id": result.entry_id, "outcome": result.outcome.value, "template": entry.template},
        )
        return result


class ResendMailBatchUC:
    """«Отправить неушедшие» (V11): сначала предпросмотр, затем отправка фоном по одному письму."""

    def __init__(
        self,
        log: IMailLogRepository,
        gate: ResendGate,
        dispatcher: MailDispatcher,
        audit: IAuditLog,
        *,
        public_url: str | None,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._log = log
        self._gate = gate
        self._dispatcher = dispatcher
        self._audit = audit
        self._public_url = public_url
        self._clock = clock

    async def plan(self, query: MailLogQuery) -> tuple[list[MailLogEntry], Counter[str]]:
        """Письма, которые уйдут (старые первыми, не больше `RESEND_BATCH_LIMIT`), и пропущенные по причинам."""
        since = self._clock() - RESEND_WINDOW
        # С запасом: часть кандидатов отсеется по токену и актуальности.
        candidates = await self._log.resend_candidates(query, since, RESEND_BATCH_LIMIT * 5)
        resent = await self._log.resent_ok([e.id for e in candidates if e.id is not None])
        ready: list[MailLogEntry] = []
        skipped: Counter[str] = Counter()
        for entry in candidates:
            if len(ready) >= RESEND_BATCH_LIMIT:
                skipped["over_limit"] += 1
                continue
            block = await self._gate.block(entry, resent=entry.id in resent)
            if block is None:
                ready.append(entry)
            else:
                skipped[block.value] += 1
        return ready, skipped

    async def execute(self, actor: Actor, query: MailLogQuery, *, dry_run: bool) -> ResendBatch:
        admin_id = require_admin(actor)
        scope = replace(query, statuses=(), retrying=None, before_id=None)
        ready, skipped = await self.plan(scope)
        started = not dry_run and bool(ready)
        if started:
            requests = [(e.id, resend_request(e, self._public_url)) for e in ready if e.id is not None]
            # Задача копирует контекст запроса: в журнале вызвавший это админ, как у одиночного повтора.
            task = asyncio.create_task(self._send_all(requests))
            _BATCHES.add(task)
            task.add_done_callback(_BATCHES.discard)
            await self._audit.record(
                "mail.resent_batch",
                actor_id=admin_id,
                details={"planned": len(ready), "skipped": dict(skipped), "filters": _filters(scope)},
            )
        return ResendBatch(planned=len(ready), skipped=dict(skipped), started=started)

    async def _send_all(self, requests: list[tuple[int, MailRequest]]) -> None:
        sent = 0
        for entry_id, request in requests:
            try:
                outcome = await self._dispatcher.send(request, resent_from_id=entry_id)
            except Exception:
                logger.exception("mail_resend_failed", mail_log_id=entry_id)
                continue
            sent += int(outcome.sent)
        logger.info("mail_resend_batch_done", planned=len(requests), sent=sent)


def _filters(query: MailLogQuery) -> dict[str, object]:
    """Фильтры пачки для аудита: только заданные."""
    raw: dict[str, object] = {
        "template": list(query.templates) or None,
        "reason": query.reason,
        "recipient_id": query.recipient_id,
        "recipient": query.recipient,
        "project_id": query.project_id,
        "from": query.since.isoformat() if query.since else None,
        "to": query.until.isoformat() if query.until else None,
        "q": query.q,
    }
    return {key: value for key, value in raw.items() if value is not None}


async def drain_resend_batches() -> None:
    """Дожидается фоновых пачек (тесты и остановка)."""
    if _BATCHES:
        await asyncio.gather(*list(_BATCHES), return_exceptions=True)
