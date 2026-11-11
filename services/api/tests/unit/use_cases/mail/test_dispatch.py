"""`MailDispatcher` (docs/design/mail-log.md, L1, L2, L8, L15, L16, 8.2): строка журнала на каждую попытку."""

from __future__ import annotations

import asyncio
import dataclasses
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any, TypeVar

import pytest
from hse_doc_studio.core.access.context import set_current_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.background import BackgroundTaskRunner, PeriodicTask
from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.mail import MailTemplate
from hse_doc_studio.core.mail.journal import (
    ERROR_TEXT_MAX,
    SUBJECT_MAX,
    MailCause,
    MailFailure,
    MailFailureClass,
    MailLinkKind,
    MailLogEntry,
    MailOrigin,
    MailRefKind,
    MailRequest,
    MailSendError,
    MailSkipReason,
    MailStatus,
    safe_params,
    template_digest,
)
from hse_doc_studio.core.request_id import reset_request_id, set_request_id
from hse_doc_studio.use_cases.mail.dispatch import UNKNOWN_MESSAGE_ID, MailCounters, MailDispatcher, MailOutcome

from tests.fakes.mail_log import InMemoryMailLogRepository

T = TypeVar("T")

NOW = datetime(2026, 11, 11, 14, 32, 5, tzinfo=UTC)
SERVER = "https://studio.example.org"
TOKEN = "Tk_dispatch-secret-0123456789abcdef"  # noqa: S105 — известная строка теста, не секрет
NOTE = "Личное сообщение: позвоните по номеру 8-900-000-00-00"
PROJECT = "0b9f6a52-3c1d-4e7a-9f7e-2f1c9b1a5d10"


class _Sender:
    def __init__(self, *, enabled: bool = True, error: Exception | None = None, message_id: str | None = None) -> None:
        self.enabled = enabled
        self.error = error
        self.message_id = message_id
        self.sent: list[tuple[str, str, str, str | None]] = []

    async def send(self, to: str, subject: str, body: str, *, html: str | None = None) -> str:
        if self.error is not None:
            raise self.error
        self.sent.append((to, subject, body, html))
        return self.message_id if self.message_id is not None else f"<{len(self.sent)}@studio.example.org>"


def _reset(**over: Any) -> MailRequest:
    fields: dict[str, Any] = {
        "template": MailTemplate.reset_password,
        "lang": Lang.ru,
        "to": "anna.petrova@example.org",
        "server_url": SERVER,
        "origin": MailOrigin.forgot_password,
        "link_kind": MailLinkKind.token,
        "link": f"{SERVER}/reset/{TOKEN}",
        "ttl": timedelta(hours=1),
        "to_user_id": "u-anna",
    }
    fields.update(over)
    return MailRequest(**fields)


def _invitation(**over: Any) -> MailRequest:
    fields: dict[str, Any] = {
        "template": MailTemplate.project_invitation_link,
        "lang": Lang.en,
        "to": "boris@example.org",
        "server_url": SERVER,
        "origin": MailOrigin.project_invite,
        "link_kind": MailLinkKind.token,
        "link": f"{SERVER}/invite/{TOKEN}",
        "values": {"actor": "Анна Петрова", "project": "Курсовая", "role": "editor"},
        "note": NOTE,
        "project_id": PROJECT,
        "ref_kind": MailRefKind.project_invitation,
        "ref_id": "inv-1",
    }
    fields.update(over)
    return MailRequest(**fields)


class _World:
    def __init__(self, sender: _Sender | None = None) -> None:
        self.sender = sender or _Sender()
        self.log = InMemoryMailLogRepository()
        self.counters = MailCounters()
        self.mail = MailDispatcher(self.sender, self.log, counters=self.counters, clock=lambda: NOW)

    @property
    def row(self) -> MailLogEntry:
        [entry] = self.log.entries
        return entry


async def _isolated(make: Callable[[], Awaitable[T]]) -> T:
    """Своя копия контекста: актор и request_id, поставленные внутри, не утекают в другие тесты."""
    return await asyncio.create_task(make())  # type: ignore[arg-type]


async def _as(actor: Actor | None, request_id: str | None, call: Callable[[], Awaitable[T]]) -> T:
    async def run() -> T:
        set_current_actor(actor)
        token = set_request_id(request_id)
        try:
            return await call()
        finally:
            reset_request_id(token)

    return await _isolated(run)


def _columns(entry: MailLogEntry) -> str:
    values = dataclasses.asdict(entry)
    values["params"] = entry.params.to_json()
    return json.dumps(values, ensure_ascii=False, default=str)


# --- итоги ---


async def test__send__sent_row_has_message_id_subject_params_and_digest() -> None:
    world = _World()
    request = _reset()

    outcome = await world.mail.send(request)

    [(to, subject, text, html)] = world.sender.sent
    assert (to, subject) == ("anna.petrova@example.org", request.render().subject)
    assert TOKEN in text
    assert html is not None
    assert TOKEN in html
    row = world.row
    assert outcome == MailOutcome(MailStatus.sent, message_id="<1@studio.example.org>", entry_id=row.id)
    assert outcome.sent
    assert (row.status, row.reason, row.message_id) == (MailStatus.sent, None, "<1@studio.example.org>")
    assert (row.template, row.lang, row.to_email, row.to_user_id) == (
        "reset_password",
        "ru",
        "anna.petrova@example.org",
        "u-anna",
    )
    assert (row.at, row.subject, row.origin, row.attempts) == (NOW, subject, "forgot_password", 1)
    assert row.duration_ms >= 0
    assert row.params == safe_params(request)
    assert row.template_digest == template_digest(MailTemplate.reset_password, Lang.ru)
    assert (row.smtp_code, row.error_text) == (None, None)


async def test__send__classified_failure_keeps_class_code_and_text() -> None:
    failure = MailFailure(reason=MailFailureClass.recipient_refused, smtp_code=550, text="5.1.1 User unknown")
    world = _World(_Sender(error=MailSendError(failure)))

    outcome = await world.mail.send(_invitation())

    row = world.row
    assert outcome.status is MailStatus.failed
    assert (outcome.reason, outcome.failure, outcome.message_id) == ("recipient_refused", failure, None)
    assert (row.status, row.reason, row.smtp_code, row.error_text) == (
        MailStatus.failed,
        "recipient_refused",
        550,
        "5.1.1 User unknown",
    )
    assert row.message_id is None
    assert outcome.failure is not None
    assert outcome.failure.describe() == "recipient_refused 550: 5.1.1 User unknown"


async def test__send__unclassified_exception_is_other_with_a_clean_one_line_text() -> None:
    world = _World(_Sender(error=OSError("smtp\r\ndown " + "x" * 400)))

    outcome = await world.mail.send(_reset())

    row = world.row
    assert (outcome.status, row.reason, row.smtp_code) == (MailStatus.failed, "other", None)
    assert row.error_text is not None
    assert row.error_text.startswith("OSError: smtp down x")
    assert "\n" not in row.error_text
    assert len(row.error_text) <= ERROR_TEXT_MAX


async def test__send__without_smtp_writes_not_sent_and_does_not_call_the_sender() -> None:
    world = _World(_Sender(enabled=False))

    outcome = await world.mail.send(_reset())

    assert world.sender.sent == []
    assert outcome == MailOutcome(MailStatus.not_sent, reason="smtp_off", entry_id=world.row.id)
    assert (world.row.status, world.row.reason, world.row.duration_ms) == (MailStatus.not_sent, "smtp_off", 0)
    assert world.row.subject == _reset().render().subject


async def test__send__smtp_removed_between_check_and_send_is_failed_smtp_off() -> None:
    world = _World(_Sender(error=MailSendError(MailFailure(reason=MailFailureClass.smtp_off))))

    outcome = await world.mail.send(_reset())

    assert (outcome.status, outcome.reason) == (MailStatus.failed, "smtp_off")


@pytest.mark.parametrize(
    ("reason", "status"),
    [
        (MailSkipReason.smtp_off, MailStatus.not_sent),
        (MailSkipReason.email_unverified, MailStatus.suppressed),
        (MailSkipReason.account_blocked, MailStatus.suppressed),
    ],
)
async def test__skip__writes_the_reason_and_sends_nothing(reason: MailSkipReason, status: MailStatus) -> None:
    world = _World()

    outcome = await world.mail.skip(_invitation(), reason)

    assert world.sender.sent == []
    assert (outcome.status, outcome.reason, outcome.entry_id) == (status, reason.value, world.row.id)
    assert (world.row.status, world.row.reason, world.row.message_id) == (status, reason.value, None)


async def test__sender_without_message_id_still_writes_a_sent_row() -> None:
    world = _World(_Sender(message_id=""))

    outcome = await world.mail.send(_reset())

    assert outcome.message_id == UNKNOWN_MESSAGE_ID
    assert world.row.message_id == UNKNOWN_MESSAGE_ID


# --- ничего секретного ---


@pytest.mark.parametrize("status", ["sent", "failed", "skipped"])
async def test__row__keeps_neither_the_token_nor_the_note(status: str) -> None:
    error = MailSendError(MailFailure(reason=MailFailureClass.other, text="boom")) if status == "failed" else None
    world = _World(_Sender(error=error))

    if status == "skipped":
        await world.mail.skip(_invitation(), MailSkipReason.email_unverified)
    else:
        await world.mail.send(_invitation())

    dumped = _columns(world.row)
    assert TOKEN not in dumped
    assert "8-900" not in dumped
    assert world.row.params.note_len == len(NOTE)
    assert world.row.params.link is MailLinkKind.token


# --- журнал не мешает отправке (L15) ---


async def test__journal_failure_does_not_break_sending_and_is_counted() -> None:
    world = _World()
    world.log.fail_with = RuntimeError("database is down")

    outcome = await world.mail.send(_reset())

    assert len(world.sender.sent) == 1
    assert outcome.status is MailStatus.sent
    assert outcome.entry_id is None
    assert outcome.message_id == "<1@studio.example.org>"
    assert world.counters.write_failures == 1
    assert world.counters.attempts() == {("reset_password", "sent"): 1}


async def test__journal_failure_on_skip_is_swallowed_too() -> None:
    world = _World()
    world.log.fail_with = RuntimeError("database is down")

    outcome = await world.mail.skip(_reset(), MailSkipReason.smtp_off)

    assert (outcome.status, outcome.entry_id) == (MailStatus.not_sent, None)
    assert world.counters.write_failures == 1


# --- метрика (8.2) ---


async def test__counters__one_per_attempt_by_kind_and_status() -> None:
    world = _World()

    await world.mail.send(_reset())
    await world.mail.send(_reset())
    await world.mail.skip(_invitation(), MailSkipReason.account_blocked)
    world.sender.error = OSError("down")
    await world.mail.send(_invitation())

    assert world.counters.attempts() == {
        ("reset_password", "sent"): 2,
        ("project_invitation_link", "suppressed"): 1,
        ("project_invitation_link", "failed"): 1,
    }
    assert world.counters.write_failures == 0


# --- обрезка под колонки и объект письма ---


async def test__fields_are_cut_to_the_columns() -> None:
    long_id = "x" * 100
    world = _World(_Sender(message_id="<" + "m" * 400 + ">"))
    request = _invitation(
        ref_id=long_id,
        to_user_id=long_id,
        values={"actor": "А" * 200, "project": "П" * 200, "role": "editor"},
    )

    await _as(Actor.user(long_id), long_id, lambda: world.mail.send(request))

    row = world.row
    assert len(row.subject) <= SUBJECT_MAX
    assert row.message_id is not None
    assert len(row.message_id) == 255  # noqa: PLR2004 — varchar(255)
    assert {len(v or "") for v in (row.ref_id, row.to_user_id, row.actor_user_id, row.request_id)} == {64}
    assert (row.project_id, row.ref_kind) == (PROJECT, "project_invitation")


async def test__project_id_is_normalized_and_a_non_uuid_is_dropped() -> None:
    world = _World()

    await world.mail.send(_invitation(project_id=PROJECT.upper()))
    await world.mail.send(_invitation(project_id="not-a-uuid"))

    assert [e.project_id for e in world.log.entries] == [PROJECT, None]


# --- кто вызвал (L8) ---


async def test__cause__user_from_the_current_actor_with_request_id() -> None:
    world = _World()

    await _as(Actor.user("u-boss", "Босс"), "req-12345678", lambda: world.mail.send(_reset()))

    row = world.row
    assert (row.cause, row.actor_user_id, row.task, row.request_id) == (
        MailCause.user,
        "u-boss",
        None,
        "req-12345678",
    )


async def test__cause__anonymous_request_without_an_actor() -> None:
    world = _World()

    await _as(None, "req-anon-0001", lambda: world.mail.send(_reset()))

    row = world.row
    assert (row.cause, row.actor_user_id, row.task, row.request_id) == (
        MailCause.anonymous,
        None,
        None,
        "req-anon-0001",
    )


async def test__cause__guest_by_link_is_anonymous() -> None:
    world = _World()

    await _as(Actor.guest("gs_1", "Гость"), None, lambda: world.mail.send(_reset()))

    assert (world.row.cause, world.row.actor_user_id) == (MailCause.anonymous, None)


async def test__cause__background_send_started_by_a_request_inherits_its_actor() -> None:
    world = _World()

    async def request() -> None:
        # Как `LinkDelivery` и `Notifier`: запрос отвечает сразу, письмо уходит отдельной задачей.
        await asyncio.create_task(world.mail.send(_reset()))

    await _as(Actor.user("u-anna"), "req-bg-00001", request)

    assert (world.row.cause, world.row.actor_user_id, world.row.request_id) == (
        MailCause.user,
        "u-anna",
        "req-bg-00001",
    )


async def test__cause__system_inside_a_background_runner_tick() -> None:
    world = _World()
    done = asyncio.Event()

    async def tick() -> None:
        if not done.is_set():
            await world.mail.send(_reset(origin=MailOrigin.signing_auto_reminder))
            done.set()

    runner = BackgroundTaskRunner(leader_retry_s=0.01)
    runner.register(PeriodicTask("signing_reminders", 60, tick, run_on_start=True))
    runner.start()
    try:
        await asyncio.wait_for(done.wait(), 2)
    finally:
        await runner.stop()

    row = world.row
    assert (row.cause, row.task, row.actor_user_id, row.request_id, row.origin) == (
        MailCause.system,
        "signing_reminders",
        None,
        None,
        "signing_auto_reminder",
    )
