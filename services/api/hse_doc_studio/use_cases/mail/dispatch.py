"""Единая точка отправки писем (docs/design/mail-log.md, L1): собрать, отправить, разобрать сбой, записать журнал.

Каждый путь отправки отдаёт `MailDispatcher` готовый `MailRequest`; `IMailSender.send` вызывает только он (тест
архитектуры). На каждую попытку ровно одна строка журнала после исхода (L2) и одно значение метрики
`hse_mail_sent_total{kind,status}` (L19). Журнал пишется в своей короткой транзакции (`IMailLogRepository.add`), а
сбой записи не ломает ни отправку, ни действие вызывающего: только лог и `hse_mail_log_write_failures_total` (L15).

Кто вызвал письмо (`cause`, актор, фоновая задача, `request_id`) берётся из контекста (`core/mail/cause.py`),
вызывающему передавать его не нужно.
"""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from uuid import UUID

import structlog

from hse_doc_studio.core.identity.protocols import IMailLogRepository, IMailSender
from hse_doc_studio.core.mail.cause import current_caller
from hse_doc_studio.core.mail.journal import (
    ERROR_TEXT_MAX,
    MESSAGE_ID_MAX,
    SHORT_FIELD_MAX,
    SUBJECT_MAX,
    MailFailure,
    MailFailureClass,
    MailLogEntry,
    MailRequest,
    MailSendError,
    MailSkipReason,
    MailStatus,
    clean_error_text,
    safe_params,
    template_digest,
)

logger = structlog.get_logger(__name__)

# Подставляется, если отправитель не вернул Message-ID: строка `sent` без него не пишется (CHECK таблицы).
UNKNOWN_MESSAGE_ID = "<unknown>"


class MailCounters:
    """Счётчики процесса для `/metrics` (8.2): попытки по виду и итогу, сбои записи журнала."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._attempts: dict[tuple[str, str], int] = defaultdict(int)
        self._write_failures = 0

    def count(self, kind: str, status: MailStatus) -> None:
        with self._lock:
            self._attempts[(kind, status.value)] += 1

    def count_write_failure(self) -> None:
        with self._lock:
            self._write_failures += 1

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
    ) -> None:
        self._sender = sender
        self._log = log
        self._counters = counters
        self._clock = clock

    @property
    def enabled(self) -> bool:
        """Настроен ли SMTP (последнее известное состояние отправителя)."""
        return self._sender.enabled

    async def send(self, request: MailRequest) -> MailOutcome:
        """Отправить письмо. Без SMTP письмо не отправляется, а пишется `not_sent/smtp_off`, как `skip`."""
        if not self._sender.enabled:
            return await self.skip(request, MailSkipReason.smtp_off)
        mail = request.render()
        at = self._clock()
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
        return await self._finish(request, outcome, at=at, duration_ms=duration_ms, subject=mail.subject)

    async def skip(self, request: MailRequest, reason: MailSkipReason) -> MailOutcome:
        """Записать письмо, которое не отправлялось: `smtp_off` даёт `not_sent`, остальные причины `suppressed`."""
        return await self._finish(
            request, MailOutcome(_status_for(reason), reason=reason.value), at=self._clock(), duration_ms=0
        )

    async def _finish(
        self, request: MailRequest, outcome: MailOutcome, *, at: datetime, duration_ms: int, subject: str | None = None
    ) -> MailOutcome:
        self._counters.count(request.template.value, outcome.status)
        entry_id = await self._record(request, outcome, at=at, duration_ms=duration_ms, subject=subject)
        done = MailOutcome(outcome.status, outcome.reason, outcome.message_id, outcome.failure, entry_id)
        fields = {
            "template": request.template.value,
            "origin": request.origin.value,
            "status": done.status.value,
            "mail_log_id": entry_id,
        }
        if done.status is MailStatus.sent:
            logger.info("mail_sent", message_id=done.message_id, **fields)
        elif done.status is MailStatus.failed and done.failure is not None:
            logger.warning("mail_failed", reason=done.reason, smtp_code=done.failure.smtp_code, **fields)
        else:
            logger.info("mail_skipped", reason=done.reason, **fields)
        return done

    async def _record(
        self, request: MailRequest, outcome: MailOutcome, *, at: datetime, duration_ms: int, subject: str | None
    ) -> int | None:
        """Строка журнала; сбой записи (или сборки строки) остаётся в логе и метрике и не мешает вызывающему."""
        try:
            entry = self._entry(request, outcome, at=at, duration_ms=duration_ms, subject=subject)
            return await self._log.add(entry)
        except Exception:
            self._counters.count_write_failure()
            logger.exception("mail_log_write_failed", template=request.template.value, status=outcome.status.value)
            return None

    def _entry(
        self, request: MailRequest, outcome: MailOutcome, *, at: datetime, duration_ms: int, subject: str | None
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
        )
