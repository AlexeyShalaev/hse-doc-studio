"""Единая точка отправки писем (docs/design/mail-log.md, L1): собрать, отправить, разобрать сбой, записать журнал.

Каждый путь отправки отдаёт `MailDispatcher` готовый `MailRequest`; `IMailSender.send` вызывает только он (тест
архитектуры). На каждую попытку ровно одна строка журнала после исхода (L2) и одно значение метрики
`hse_mail_sent_total{kind,status}` (L19). Журнал пишется в своей короткой транзакции (`IMailLogRepository.add`), а
сбой записи не ломает ни отправку, ни действие вызывающего: только лог и `hse_mail_log_write_failures_total` (L15).

Кто вызвал письмо (`cause`, актор, фоновая задача, `request_id`) берётся из контекста (`core/mail/cause.py`),
вызывающему передавать его не нужно.

Временный сбой (раздел 14, V6) ставит письмо в очередь автоповтора (`IMailLogRepository.add(..., retry=...)`), а
задача лидера `mail_retry` зовёт `retry_due`: созревшие письма уходят ещё раз, исход пишется в ту же строку (V7).
"""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from threading import Lock
from uuid import UUID

import structlog

from hse_doc_studio.core.identity.protocols import IMailLogRepository, IMailSender
from hse_doc_studio.core.mail.cause import current_caller
from hse_doc_studio.core.mail.compose import MailTemplate, RenderedMail
from hse_doc_studio.core.mail.journal import (
    ERROR_TEXT_MAX,
    MESSAGE_ID_MAX,
    RETRY_DELAYS,
    SHORT_FIELD_MAX,
    SUBJECT_MAX,
    MailAttempt,
    MailFailure,
    MailFailureClass,
    MailLinkKind,
    MailLogEntry,
    MailRequest,
    MailRetryJob,
    MailSendError,
    MailSkipReason,
    MailStatus,
    clean_error_text,
    is_transient,
    link_expired,
    next_retry_at,
    safe_params,
    template_digest,
)
from hse_doc_studio.core.mail.ports import IMailRelevance

logger = structlog.get_logger(__name__)

# Подставляется, если отправитель не вернул Message-ID: строка `sent` без него не пишется (CHECK таблицы).
UNKNOWN_MESSAGE_ID = "<unknown>"
# Очередь автоповтора (V9): сколько писем за проход и на сколько их откладывает аренда до исхода.
RETRY_BATCH = 20
RETRY_LEASE = timedelta(minutes=5)


class MailCounters:
    """Счётчики процесса для `/metrics` (8.2): попытки по виду и итогу, сбои записи журнала."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._attempts: dict[tuple[str, str], int] = defaultdict(int)
        self._write_failures = 0
        self._dropped: dict[str, int] = defaultdict(int)

    def count(self, kind: str, status: MailStatus) -> None:
        with self._lock:
            self._attempts[(kind, status.value)] += 1

    def count_write_failure(self) -> None:
        with self._lock:
            self._write_failures += 1

    def count_dropped(self, reason: str) -> None:
        with self._lock:
            self._dropped[reason] += 1

    def dropped(self) -> dict[str, int]:
        """`причина -> число` прекращённых автоповторов с запуска процесса (V16)."""
        with self._lock:
            return dict(self._dropped)

    def attempts(self) -> dict[tuple[str, str], int]:
        """`(вид, итог) -> число попыток` с запуска процесса."""
        with self._lock:
            return dict(self._attempts)

    @property
    def write_failures(self) -> int:
        with self._lock:
            return self._write_failures


# Один набор на процесс: диспетчеров может быть несколько (контейнеры, тесты), а метрика процесса одна.
MAIL_COUNTERS = MailCounters()


@dataclass(frozen=True)
class MailOutcome:
    """Итог попытки для вызывающего.

    `reason`: причина пропуска (`MailSkipReason`) или класс сбоя (`MailFailureClass`), у `sent` None.
    `entry_id`: id строки журнала; None, если запись журнала не удалась (письмо при этом ушло или не ушло как есть).
    """

    status: MailStatus
    reason: str | None = None
    message_id: str | None = None
    failure: MailFailure | None = None
    entry_id: int | None = None
    # Временный сбой: Студия повторит отправку сама (V6).
    next_attempt_at: datetime | None = None

    @property
    def sent(self) -> bool:
        return self.status is MailStatus.sent


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _cut(value: str | None, limit: int) -> str | None:
    return value[:limit] if value else None


def _project_id(value: str | None) -> str | None:
    """Колонка `project_id` типа uuid: не-UUID не ломает запись строки, а отбрасывается."""
    if not value:
        return None
    try:
        return str(UUID(str(value)))
    except ValueError:
        logger.warning("mail_log_project_id_invalid")
        return None


def _status_for(reason: MailSkipReason) -> MailStatus:
    return MailStatus.not_sent if reason is MailSkipReason.smtp_off else MailStatus.suppressed


class MailDispatcher:
    """Отправка письма с записью в журнал. Не бросает из-за почты или журнала: итог возвращается `MailOutcome`.

    Исключение пробрасывается только из `MailRequest.render()` у `send` (ошибка в коде письма, до отправки) и
    при отмене задачи.
    """

    def __init__(
        self,
        sender: IMailSender,
        log: IMailLogRepository,
        *,
        counters: MailCounters = MAIL_COUNTERS,
        clock: Callable[[], datetime] = _utcnow,
        relevance: IMailRelevance | None = None,
    ) -> None:
        self._sender = sender
        self._log = log
        self._counters = counters
        self._clock = clock
        self._relevance = relevance

    @property
    def enabled(self) -> bool:
        """Настроен ли SMTP (последнее известное состояние отправителя)."""
        return self._sender.enabled

    async def send(self, request: MailRequest, *, resent_from_id: int | None = None) -> MailOutcome:
        """Отправить письмо. Без SMTP письмо не отправляется, а пишется `not_sent/smtp_off`, как `skip`.

        Временный сбой (V6) ставит письмо в очередь автоповтора, кроме тестового: его админ ждёт сразу.
        `resent_from_id`: ручной повтор строки журнала (V2)."""
        if not self._sender.enabled:
            return await self.skip(request, MailSkipReason.smtp_off)
        mail = request.render()
        at = self._clock()
        outcome, duration_ms = await self._attempt(request, mail)
        if (
            outcome.failure is not None
            and request.template is not MailTemplate.smtp_test
            and is_transient(outcome.failure)
        ):
            outcome = replace(outcome, next_attempt_at=at + RETRY_DELAYS[0])
        return await self._finish(
            request, outcome, at=at, duration_ms=duration_ms, subject=mail.subject, resent_from_id=resent_from_id
        )

    async def _attempt(self, request: MailRequest, mail: RenderedMail) -> tuple[MailOutcome, int]:
        """Одна попытка через отправителя: итог без строки журнала и длительность в мс."""
        started = time.monotonic()
        failure: MailFailure | None = None
        message_id: str | None = None
        try:
            message_id = await self._sender.send(request.to, mail.subject, mail.text, html=mail.html)
        except MailSendError as exc:
            failure = exc.failure
        except Exception as exc:
            # Отправитель не разобрал сбой сам: без его секретов скрыть нечего, поэтому только класс и текст.
            failure = MailFailure(reason=MailFailureClass.other, text=clean_error_text(f"{type(exc).__name__}: {exc}"))
        duration_ms = max(0, round((time.monotonic() - started) * 1000))
        if failure is None:
            if not message_id:
                logger.warning("mail_sent_without_message_id", template=request.template.value)
            outcome = MailOutcome(MailStatus.sent, message_id=_cut(message_id, MESSAGE_ID_MAX) or UNKNOWN_MESSAGE_ID)
        else:
            outcome = MailOutcome(MailStatus.failed, reason=failure.reason.value, failure=failure)
        return outcome, duration_ms

    async def retry_due(self) -> int:
        """Проход очереди автоповтора (V9): созревшие письма уходят ещё раз; возвращает число попыток.

        Не бросает из-за почты и журнала: письмо, которое не удалось обработать, вернётся после аренды."""
        now = self._clock()
        jobs = await self._log.claim_retries(now, RETRY_LEASE, RETRY_BATCH)
        tried = 0
        for job in jobs:
            try:
                tried += await self._retry_one(job)
            except Exception:
                logger.exception("mail_retry_failed", mail_log_id=job.entry_id)
        return tried

    async def _retry_one(self, job: MailRetryJob) -> int:
        entry = await self._log.get(job.entry_id)
        if entry is None:
            return 0
        request = job.request
        now = self._clock()
        stop = await self._retry_stop(job, entry, now)
        if stop is not None or request is None:
            await self._drop(entry, stop or "unreadable")
            return 0
        outcome, duration_ms = await self._attempt(request, request.render())
        attempts = job.attempts + 1
        failure = outcome.failure
        next_at = next_retry_at(attempts, now) if failure is not None and is_transient(failure) else None
        await self._log.finish_attempt(
            job.entry_id,
            MailAttempt(
                status=outcome.status,
                attempts=attempts,
                tried_at=now,
                duration_ms=duration_ms,
                reason=outcome.reason,
                smtp_code=failure.smtp_code if failure else None,
                error_text=_cut(failure.text, ERROR_TEXT_MAX) if failure else None,
                message_id=outcome.message_id,
                next_attempt_at=next_at,
            ),
        )
        self._counters.count(request.template.value, outcome.status)
        fields = {"template": request.template.value, "mail_log_id": job.entry_id, "attempts": attempts}
        if outcome.sent:
            logger.info("mail_retry_sent", message_id=outcome.message_id, **fields)
        else:
            logger.warning(
                "mail_retry_failed_attempt",
                reason=outcome.reason,
                smtp_code=failure.smtp_code if failure else None,
                next_attempt_at=next_at.isoformat() if next_at else None,
                **fields,
            )
        return 1

    async def _retry_stop(self, job: MailRetryJob, entry: MailLogEntry, now: datetime) -> str | None:
        """Почему повтор прекращается (V9): запрос не читается, SMTP сняли, ссылка истекла, письмо устарело."""
        request = job.request
        if request is None:
            return "unreadable"
        if not self._sender.enabled:
            return "smtp_off"
        if link_expired(request, job.first_at, now):
            return "link_expired"
        if request.link_kind is not MailLinkKind.token and self._relevance is not None:
            block = await self._relevance.check(entry)
            return block.value if block is not None else None
        return None

    async def _drop(self, entry: MailLogEntry, reason: str) -> None:
        """Повтор прекращён (V9): строка остаётся окончательным сбоем с прежней причиной."""
        assert entry.id is not None  # noqa: S101 — строка из хранилища всегда с id
        self._counters.count_dropped(reason)
        logger.info("mail_retry_dropped", mail_log_id=entry.id, template=entry.template, reason=reason)
        await self._log.finish_attempt(
            entry.id,
            MailAttempt(
                status=entry.status,
                attempts=entry.attempts,
                tried_at=entry.tried_at,
                duration_ms=entry.duration_ms,
                reason=entry.reason,
                smtp_code=entry.smtp_code,
                error_text=entry.error_text,
                message_id=entry.message_id,
                next_attempt_at=None,
            ),
        )

    async def skip(self, request: MailRequest, reason: MailSkipReason) -> MailOutcome:
        """Записать письмо, которое не отправлялось: `smtp_off` даёт `not_sent`, остальные причины `suppressed`."""
        return await self._finish(
            request, MailOutcome(_status_for(reason), reason=reason.value), at=self._clock(), duration_ms=0
        )

    async def _finish(  # noqa: PLR0913 — поля одной строки журнала
        self,
        request: MailRequest,
        outcome: MailOutcome,
        *,
        at: datetime,
        duration_ms: int,
        subject: str | None = None,
        resent_from_id: int | None = None,
    ) -> MailOutcome:
        self._counters.count(request.template.value, outcome.status)
        entry_id, queued = await self._record(
            request, outcome, at=at, duration_ms=duration_ms, subject=subject, resent_from_id=resent_from_id
        )
        done = replace(outcome, entry_id=entry_id, next_attempt_at=outcome.next_attempt_at if queued else None)
        fields = {
            "template": request.template.value,
            "origin": request.origin.value,
            "status": done.status.value,
            "mail_log_id": entry_id,
        }
        if done.status is MailStatus.sent:
            logger.info("mail_sent", message_id=done.message_id, **fields)
        elif done.status is MailStatus.failed and done.failure is not None:
            logger.warning(
                "mail_failed",
                reason=done.reason,
                smtp_code=done.failure.smtp_code,
                retry=done.next_attempt_at is not None,
                **fields,
            )
        else:
            logger.info("mail_skipped", reason=done.reason, **fields)
        return done

    async def _record(  # noqa: PLR0913 — поля одной строки журнала
        self,
        request: MailRequest,
        outcome: MailOutcome,
        *,
        at: datetime,
        duration_ms: int,
        subject: str | None,
        resent_from_id: int | None,
    ) -> tuple[int | None, bool]:
        """Строка журнала и, при временном сбое, очередь автоповтора; сбой записи (или сборки строки) остаётся в
        логе и метрике и не мешает вызывающему. Второе значение: встал ли повтор в очередь."""
        try:
            entry = self._entry(
                request, outcome, at=at, duration_ms=duration_ms, subject=subject, resent_from_id=resent_from_id
            )
            retry = request if outcome.next_attempt_at is not None else None
            entry_id = await self._log.add(entry, retry)
        except Exception:
            self._counters.count_write_failure()
            logger.exception("mail_log_write_failed", template=request.template.value, status=outcome.status.value)
            return None, False
        return entry_id, retry is not None

    def _entry(  # noqa: PLR0913 — поля одной строки журнала
        self,
        request: MailRequest,
        outcome: MailOutcome,
        *,
        at: datetime,
        duration_ms: int,
        subject: str | None,
        resent_from_id: int | None = None,
    ) -> MailLogEntry:
        caller = current_caller()
        failure = outcome.failure
        return MailLogEntry(
            at=at,
            duration_ms=duration_ms,
            template=request.template.value,
            lang=request.lang.value,
            to_email=request.to,
            to_user_id=_cut(request.to_user_id, SHORT_FIELD_MAX),
            subject=(subject if subject is not None else request.render().subject)[:SUBJECT_MAX],
            status=outcome.status,
            reason=outcome.reason,
            smtp_code=failure.smtp_code if failure else None,
            error_text=_cut(failure.text, ERROR_TEXT_MAX) if failure else None,
            message_id=outcome.message_id,
            cause=caller.cause,
            actor_user_id=_cut(caller.actor_user_id, SHORT_FIELD_MAX),
            task=_cut(caller.task, SHORT_FIELD_MAX),
            origin=request.origin.value,
            request_id=_cut(caller.request_id, SHORT_FIELD_MAX),
            project_id=_project_id(request.project_id),
            ref_kind=request.ref_kind.value if request.ref_kind else None,
            ref_id=_cut(request.ref_id, SHORT_FIELD_MAX),
            params=safe_params(request),
            template_digest=template_digest(request.template, request.lang),
            next_attempt_at=outcome.next_attempt_at,
            resent_from_id=resent_from_id,
        )
