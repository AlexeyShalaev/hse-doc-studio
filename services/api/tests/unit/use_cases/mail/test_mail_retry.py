"""Автоповтор и ручной повтор писем (docs/design/mail-log.md, раздел 14, V1..V12)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from hse_doc_studio.core.access.entities import Actor, ActorSource
from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.identity.errors import IdentityError
from hse_doc_studio.core.mail import MailTemplate
from hse_doc_studio.core.mail.journal import (
    MAX_ATTEMPTS,
    RETRY_DELAYS,
    MailFailure,
    MailFailureClass,
    MailLinkKind,
    MailLogQuery,
    MailOrigin,
    MailRefKind,
    MailRequest,
    MailSendError,
    MailStatus,
    ResendBlock,
)
from hse_doc_studio.use_cases.mail.dispatch import RETRY_LEASE, MailCounters, MailDispatcher
from hse_doc_studio.use_cases.mail.resend import (
    ResendGate,
    ResendMailBatchUC,
    ResendMailUC,
    ResendOutcome,
    drain_resend_batches,
)

from tests.fakes.mail_log import InMemoryMailLogRepository
from tests.fakes.mail_relevance import InMemoryMailRelevance

T0 = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
SERVER = "https://studio.example.org"
PROJECT = "5b0c1d2e-3f40-4152-8364-758697a8b9c0"
ROUTE = "0d1e2f30-4152-4637-8899-aabbccddeeff"
ADMIN = Actor.user("boss", is_instance_admin=True, source=ActorSource.session)
USER = Actor.user("anna", source=ActorSource.session)

TEMP = MailSendError(MailFailure(reason=MailFailureClass.recipient_refused, smtp_code=451, text="try later"))
LOST = MailSendError(MailFailure(reason=MailFailureClass.connect, text="Connection refused"))
HARD = MailSendError(MailFailure(reason=MailFailureClass.recipient_refused, smtp_code=550, text="no mailbox"))


class _Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now


class _Sender:
    """Отвечает по очереди из `script`; кончился сценарий, письмо уходит."""

    def __init__(self, *script: Exception | None, enabled: bool = True) -> None:
        self.script = list(script)
        self.enabled = enabled
        self.sent: list[tuple[str, str, str]] = []

    async def send(self, to: str, subject: str, body: str, *, html: str | None = None) -> str:
        error = self.script.pop(0) if self.script else None
        if error is not None:
            raise error
        self.sent.append((to, subject, body))
        return f"<{len(self.sent)}@studio.example.org>"


class _Audit:
    def __init__(self) -> None:
        self.events: list[tuple[str, str | None, dict[str, Any]]] = []

    async def record(
        self, action: str, *, actor_id: str | None, target: str | None = None, details: Any = None
    ) -> None:
        self.events.append((action, target, dict(details or {})))


def _world(
    *script: Exception | None, enabled: bool = True
) -> tuple[MailDispatcher, InMemoryMailLogRepository, _Sender, _Clock, InMemoryMailRelevance]:
    log, sender, clock, relevance = (
        InMemoryMailLogRepository(),
        _Sender(*script, enabled=enabled),
        _Clock(),
        InMemoryMailRelevance(),
    )
    dispatcher = MailDispatcher(sender, log, counters=MailCounters(), clock=clock, relevance=relevance)
    return dispatcher, log, sender, clock, relevance


def _reminder(**over: Any) -> MailRequest:
    fields: dict[str, Any] = {
        "template": MailTemplate.signing_reminder,
        "lang": Lang.ru,
        "to": "anna@example.org",
        "server_url": SERVER,
        "origin": MailOrigin.signing_auto_reminder,
        "link_kind": MailLinkKind.page,
        "link": f"{SERVER}/sign/{PROJECT}/{ROUTE}",
        "values": {"actor": "Борис", "project": "ВКР", "profile": "Заявление", "deadline": "15 ноября"},
        "to_user_id": "u-anna",
        "project_id": PROJECT,
        "ref_kind": MailRefKind.signing_route,
        "ref_id": ROUTE,
    }
    fields.update(over)
    return MailRequest(**fields)


def _reset(**over: Any) -> MailRequest:
    fields: dict[str, Any] = {
        "template": MailTemplate.reset_password,
        "lang": Lang.ru,
        "to": "anna@example.org",
        "server_url": SERVER,
        "origin": MailOrigin.forgot_password,
        "link_kind": MailLinkKind.token,
        "link": f"{SERVER}/reset/Tk-secret",
        "ttl": timedelta(hours=1),
    }
    fields.update(over)
    return MailRequest(**fields)


# --- Автоповтор (V6..V9) ---


@pytest.mark.parametrize("error", [TEMP, LOST])
async def test__send__transient_failure_is_queued_in_the_same_row(error: Exception) -> None:
    dispatcher, log, _, _, _ = _world(error)

    outcome = await dispatcher.send(_reset())

    assert outcome.status is MailStatus.failed
    assert outcome.next_attempt_at == T0 + RETRY_DELAYS[0]
    (entry,) = log.entries
    assert entry.next_attempt_at == T0 + RETRY_DELAYS[0]
    assert entry.retrying is True
    assert entry.attempts == 1
    assert log.queue[entry.id or 0].request == _reset()


@pytest.mark.parametrize(
    ("request_", "error"),
    [
        (_reset(), HARD),
        (_reset(), MailSendError(MailFailure(reason=MailFailureClass.auth, smtp_code=535))),
        (
            MailRequest(
                template=MailTemplate.smtp_test,
                lang=Lang.ru,
                to="boss@example.org",
                server_url=SERVER,
                origin=MailOrigin.smtp_test,
            ),
            TEMP,
        ),
    ],
)
async def test__send__permanent_failure_and_test_mail_are_not_queued(request_: MailRequest, error: Exception) -> None:
    dispatcher, log, _, _, _ = _world(error)

    outcome = await dispatcher.send(request_)

    assert outcome.status is MailStatus.failed
    assert outcome.next_attempt_at is None
    assert log.entries[0].next_attempt_at is None
    assert log.queue == {}


async def test__send__no_cipher_means_no_promise_of_a_retry() -> None:
    log = InMemoryMailLogRepository(retries=False)
    dispatcher = MailDispatcher(_Sender(TEMP), log, counters=MailCounters(), clock=_Clock())

    outcome = await dispatcher.send(_reset())

    assert log.entries[0].next_attempt_at is None
    # Вызывающему диспетчер честно говорит о попытке, хранилище решает, встала ли она в очередь.
    assert outcome.status is MailStatus.failed


async def test__retry_due__waits_for_the_pause_then_sends_into_the_same_row() -> None:
    dispatcher, log, sender, clock, _ = _world(TEMP)
    await dispatcher.send(_reminder())

    clock.now = T0 + RETRY_DELAYS[0] - timedelta(seconds=1)
    assert await dispatcher.retry_due() == 0

    clock.now = T0 + RETRY_DELAYS[0]
    assert await dispatcher.retry_due() == 1

    (entry,) = log.entries
    assert entry.status is MailStatus.sent
    assert entry.attempts == 2
    assert entry.at == T0
    assert entry.last_attempt_at == clock.now
    assert entry.next_attempt_at is None
    assert (entry.reason, entry.smtp_code, entry.error_text) == (None, None, None)
    assert entry.message_id == "<1@studio.example.org>"
    assert log.queue == {}
    assert len(sender.sent) == 1


async def test__retry_due__gives_up_after_the_last_attempt() -> None:
    dispatcher, log, sender, clock, _ = _world(*([TEMP] * MAX_ATTEMPTS))
    await dispatcher.send(_reminder())

    for _ in range(MAX_ATTEMPTS + 2):
        entry = log.entries[0]
        if entry.next_attempt_at is None:
            break
        clock.now = entry.next_attempt_at
        await dispatcher.retry_due()

    entry = log.entries[0]
    assert entry.attempts == MAX_ATTEMPTS
    assert entry.status is MailStatus.failed
    assert entry.smtp_code == 451
    assert entry.next_attempt_at is None
    assert log.queue == {}
    assert sender.sent == []


async def test__retry_due__permanent_answer_on_a_retry_stops() -> None:
    dispatcher, log, _, clock, _ = _world(LOST, HARD)
    await dispatcher.send(_reminder())

    clock.now = T0 + RETRY_DELAYS[0]
    await dispatcher.retry_due()

    entry = log.entries[0]
    assert (entry.attempts, entry.smtp_code, entry.next_attempt_at) == (2, 550, None)
    assert log.queue == {}


async def test__retry_due__a_claimed_row_waits_for_the_lease() -> None:
    dispatcher, log, _, clock, _ = _world(TEMP)
    await dispatcher.send(_reminder())
    clock.now = T0 + RETRY_DELAYS[0]

    claimed = await log.claim_retries(clock.now, RETRY_LEASE, 10)

    # Процесс взял письмо и упал: до конца аренды его никто не берёт, после неё повторит следующий проход.
    assert [job.entry_id for job in claimed] == [1]
    assert await dispatcher.retry_due() == 0
    clock.now += RETRY_LEASE
    assert await dispatcher.retry_due() == 1
    assert log.entries[0].status is MailStatus.sent


@pytest.mark.parametrize("case", ["expired_link", "smtp_off", "stale", "unreadable"])
async def test__retry_due__stops_without_sending(case: str) -> None:
    dispatcher, log, sender, clock, relevance = _world(TEMP)
    request = _reset() if case == "expired_link" else _reminder()
    await dispatcher.send(request)
    clock.now = T0 + RETRY_DELAYS[0]
    if case == "expired_link":
        clock.now = T0 + timedelta(hours=1)
    elif case == "smtp_off":
        sender.enabled = False
    elif case == "stale":
        relevance.blocks[1] = ResendBlock.route_done
    else:
        log.queue[1].request = None
    counters = dispatcher._counters  # noqa: SLF001 — счётчики процесса этого диспетчера

    assert await dispatcher.retry_due() == 0

    entry = log.entries[0]
    assert entry.status is MailStatus.failed
    assert entry.attempts == 1
    assert entry.next_attempt_at is None
    assert entry.smtp_code == 451
    assert log.queue == {}
    assert sender.sent == []
    reason = {"expired_link": "link_expired", "stale": "route_done"}.get(case, case)
    assert counters.dropped() == {reason: 1}


async def test__summary__waiting_rows_are_counted_apart() -> None:
    dispatcher, log, _, _, _ = _world(TEMP, HARD, None)
    for _ in range(3):
        await dispatcher.send(_reminder())

    counts = await log.summary(T0 - timedelta(hours=1))

    assert (counts.sent, counts.failed, counts.retrying) == (1, 1, 1)
    waiting = await log.page(MailLogQuery(retrying=True))
    assert [e.id for e in waiting.items] == [1]
    rest = await log.page(MailLogQuery(retrying=False))
    assert [e.id for e in rest.items] == [3, 2]


# --- Ручной повтор (V1..V5, V12) ---


def _resend_world(
    *script: Exception | None,
) -> tuple[ResendMailUC, ResendMailBatchUC, InMemoryMailLogRepository, _Sender, _Clock, InMemoryMailRelevance, _Audit]:
    dispatcher, log, sender, clock, relevance = _world(*script)
    audit = _Audit()
    gate = ResendGate(log, relevance, dispatcher, clock=clock)
    single = ResendMailUC(log, gate, dispatcher, audit, public_url=SERVER)  # type: ignore[arg-type]
    batch = ResendMailBatchUC(log, gate, dispatcher, audit, public_url=SERVER, clock=clock)  # type: ignore[arg-type]
    return single, batch, log, sender, clock, relevance, audit


async def test__resend__sends_a_new_row_linked_to_the_original() -> None:
    single, _, log, sender, clock, _, audit = _resend_world(HARD)
    await MailDispatcher(sender, log, counters=MailCounters(), clock=clock).send(_reminder())
    clock.now = T0 + timedelta(hours=2)

    result = await single.execute(ADMIN, 1)

    assert result is not None
    assert result.outcome is ResendOutcome.sent
    assert result.entry_id == 2
    original, copy = log.entries
    assert original.status is MailStatus.failed
    assert copy.status is MailStatus.sent
    assert copy.resent_from_id == 1
    assert copy.origin == MailOrigin.admin_resend.value
    assert copy.at == clock.now
    assert copy.ref_kind == MailRefKind.signing_route.value
    assert audit.events == [("mail.resent", "1", {"entry_id": 2, "outcome": "sent", "template": "signing_reminder"})]
    # Второй раз уже не нужно: письмо дошло.
    again = await single.execute(ADMIN, 1)
    assert again is not None
    assert again.blocked is ResendBlock.already_resent


async def test__resend__stale_or_token_mail_is_blocked_and_not_sent() -> None:
    single, _, log, sender, clock, relevance, audit = _resend_world(HARD, HARD)
    dispatcher = MailDispatcher(sender, log, counters=MailCounters(), clock=clock)
    await dispatcher.send(_reminder())
    await dispatcher.send(_reset())
    relevance.blocks[1] = ResendBlock.route_done

    stale = await single.execute(ADMIN, 1)
    token = await single.execute(ADMIN, 2)

    assert stale is not None
    assert stale.outcome is ResendOutcome.blocked
    assert stale.blocked is ResendBlock.route_done
    assert token is not None
    assert token.blocked is ResendBlock.token_link
    assert len(log.entries) == 2
    assert audit.events == []
    assert await single.execute(ADMIN, 99) is None
    with pytest.raises(IdentityError):
        await single.execute(USER, 1)


async def test__resend__transient_failure_goes_to_the_retry_queue() -> None:
    single, _, log, sender, clock, _, _ = _resend_world(HARD, TEMP)
    await MailDispatcher(sender, log, counters=MailCounters(), clock=clock).send(_reminder())

    result = await single.execute(ADMIN, 1)

    assert result is not None
    assert result.outcome is ResendOutcome.retrying
    assert log.entries[1].retrying is True


async def test__batch__preview_counts_then_sends_in_the_background() -> None:
    _, batch, log, sender, clock, relevance, audit = _resend_world(HARD, HARD, HARD, HARD)
    dispatcher = MailDispatcher(sender, log, counters=MailCounters(), clock=clock)
    await dispatcher.send(_reminder())
    await dispatcher.send(_reminder(to="boris@example.org", to_user_id="u-boris"))
    await dispatcher.send(_reset())
    await dispatcher.send(_reminder(to="old@example.org", to_user_id=None))
    log.entries[3] = log.entries[3].__class__(**{**log.entries[3].__dict__, "at": T0 - timedelta(days=4)})
    relevance.blocks[2] = ResendBlock.route_done

    preview = await batch.execute(ADMIN, MailLogQuery(), dry_run=True)

    assert (preview.planned, preview.started) == (1, False)
    assert preview.skipped == {"route_done": 1, "token_link": 1}
    assert len(log.entries) == 4
    assert audit.events == []

    started = await batch.execute(ADMIN, MailLogQuery(), dry_run=False)
    await drain_resend_batches()

    assert started.started is True
    assert log.entries[4].resent_from_id == 1
    assert log.entries[4].status is MailStatus.sent
    assert audit.events[0][0] == "mail.resent_batch"
    assert audit.events[0][2]["planned"] == 1
    # Повторный запуск пропускает уже дошедшее.
    after = await batch.execute(ADMIN, MailLogQuery(), dry_run=False)
    assert after.planned == 0
    assert after.skipped["already_resent"] == 1


async def test__batch__filters_apply_and_status_filters_are_ignored() -> None:
    _, batch, log, sender, clock, _, _ = _resend_world(HARD, HARD)
    dispatcher = MailDispatcher(sender, log, counters=MailCounters(), clock=clock)
    await dispatcher.send(_reminder())
    await dispatcher.send(_reminder(to="boris@example.org", to_user_id="u-boris"))

    preview = await batch.execute(
        ADMIN, MailLogQuery(recipient="Boris@example.org", statuses=(MailStatus.sent,)), dry_run=True
    )

    assert preview.planned == 1


# --- Самодиагностика (V14) ---


async def test__mail_delivery_check__reads_the_log_hour_and_day() -> None:
    from hse_doc_studio.core.diagnostics.entities import DiagStatus  # noqa: PLC0415
    from hse_doc_studio.core.diagnostics.thresholds import DEFAULTS  # noqa: PLC0415
    from hse_doc_studio.use_cases.diagnostics.checks import MailDeliveryCheck  # noqa: PLC0415

    dispatcher, log, sender, clock, _ = _world(None, None, None, LOST, LOST, LOST)
    for _ in range(6):
        await dispatcher.send(_reminder())
    check = MailDeliveryCheck(log, sender)

    verdict = await check.run(DEFAULTS, clock.now)

    assert verdict.status is DiagStatus.fail
    assert verdict.reason == "mail_failing_hour"
    assert dict(verdict.values) == {"failed": 3, "total": 6, "percent": 50}
    sender.enabled = False
    assert (await check.run(DEFAULTS, clock.now)).reason == "not_configured"
