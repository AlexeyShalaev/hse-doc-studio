"""Политика повтора писем (docs/design/mail-log.md, раздел 14): временный сбой, паузы, окно и сборка письма."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.mail import MailTemplate
from hse_doc_studio.core.mail.journal import (
    MAX_ATTEMPTS,
    RESEND_WINDOW,
    RETRY_DELAYS,
    MailCause,
    MailFailure,
    MailFailureClass,
    MailLinkKind,
    MailLogEntry,
    MailOrigin,
    MailParams,
    MailRefKind,
    MailRequest,
    MailStatus,
    ResendBlock,
    is_transient,
    link_expired,
    next_retry_at,
    rerender,
    resend_block,
    resend_request,
    safe_params,
)

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
SERVER = "https://studio.example.org"
PROJECT = "5b0c1d2e-3f40-4152-8364-758697a8b9c0"
ROUTE = "0d1e2f30-4152-4637-8899-aabbccddeeff"


@pytest.mark.parametrize(
    ("failure", "transient"),
    [
        (MailFailure(reason=MailFailureClass.recipient_refused, smtp_code=451), True),
        (MailFailure(reason=MailFailureClass.other, smtp_code=421), True),
        (MailFailure(reason=MailFailureClass.auth, smtp_code=454), True),
        (MailFailure(reason=MailFailureClass.connect), True),
        (MailFailure(reason=MailFailureClass.timeout), True),
        (MailFailure(reason=MailFailureClass.disconnected), True),
        (MailFailure(reason=MailFailureClass.recipient_refused, smtp_code=550), False),
        (MailFailure(reason=MailFailureClass.auth, smtp_code=535), False),
        (MailFailure(reason=MailFailureClass.data_refused, smtp_code=554), False),
        # Обрыв с постоянным кодом не повторяется: решает код.
        (MailFailure(reason=MailFailureClass.connect, smtp_code=554), False),
        (MailFailure(reason=MailFailureClass.tls), False),
        (MailFailure(reason=MailFailureClass.smtp_off), False),
        (MailFailure(reason=MailFailureClass.other), False),
    ],
)
def test__is_transient__4xx_and_lost_connections_only(failure: MailFailure, transient: bool) -> None:
    assert is_transient(failure) is transient


def test__next_retry_at__growing_pauses_then_nothing() -> None:
    planned = [next_retry_at(n, NOW) for n in range(1, MAX_ATTEMPTS + 1)]

    assert planned[:-1] == [NOW + delay for delay in RETRY_DELAYS]
    assert planned[-1] is None
    assert MAX_ATTEMPTS == 5
    assert list(RETRY_DELAYS) == sorted(RETRY_DELAYS)
    assert next_retry_at(0, NOW) is None


def _request(**over: Any) -> MailRequest:
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


def test__link_expired__token_by_ttl_or_expiry_page_never() -> None:
    request = _request()

    assert link_expired(request, NOW, NOW + timedelta(minutes=59)) is False
    assert link_expired(request, NOW, NOW + timedelta(hours=1)) is True
    dated = _request(ttl=None, expires_at=NOW + timedelta(minutes=10))
    assert link_expired(dated, NOW - timedelta(days=1), NOW + timedelta(minutes=11)) is True
    page = MailRequest(
        template=MailTemplate.signing_reminder,
        lang=Lang.ru,
        to="anna@example.org",
        server_url=SERVER,
        origin=MailOrigin.notification,
        link_kind=MailLinkKind.page,
        link=f"{SERVER}/sign/{PROJECT}/{ROUTE}",
    )
    assert link_expired(page, NOW - timedelta(days=30), NOW) is False


def test__request_json__round_trip_keeps_the_link_and_the_note() -> None:
    request = _request(
        template=MailTemplate.project_invitation_link,
        origin=MailOrigin.project_invite,
        link=f"{SERVER}/invite/Tk-secret",
        ttl=None,
        expires_at=NOW + timedelta(days=7),
        values={"actor": "Анна", "project": "ВКР", "role": "editor", "count": 2},
        note="Привет!",
        to_user_id="u-1",
        project_id=PROJECT,
        ref_kind=MailRefKind.project_invitation,
        ref_id="inv-1",
    )

    again = MailRequest.from_json(request.to_json())

    assert again == request
    assert again.render() == request.render()


def _entry(**over: Any) -> MailLogEntry:
    fields: dict[str, Any] = {
        "id": 7,
        "at": NOW - timedelta(hours=1),
        "duration_ms": 10,
        "template": MailTemplate.signing_reminder.value,
        "lang": "ru",
        "to_email": "anna@example.org",
        "to_user_id": "u-anna",
        "subject": "Напоминание",
        "status": MailStatus.failed,
        "reason": "recipient_refused",
        "smtp_code": 550,
        "cause": MailCause.system,
        "origin": MailOrigin.signing_auto_reminder.value,
        "params": MailParams(
            values={"actor": "Анна Петрова", "project": "ВКР", "profile": "Заявление", "deadline": "15 ноября"},
            link=MailLinkKind.page,
            link_path=f"/sign/{PROJECT}/{ROUTE}",
            server="https://old.example.org",
        ),
        "template_digest": "0000000000000000",
        "project_id": PROJECT,
        "ref_kind": MailRefKind.signing_route.value,
        "ref_id": ROUTE,
    }
    fields.update(over)
    return MailLogEntry(**fields)


@pytest.mark.parametrize(
    ("over", "smtp", "resent", "block"),
    [
        ({}, True, False, None),
        ({"status": MailStatus.not_sent, "reason": "smtp_off", "smtp_code": None}, True, False, None),
        ({"status": MailStatus.sent, "reason": None, "smtp_code": None, "message_id": "<m>"}, True, False, "status"),
        ({"status": MailStatus.suppressed, "reason": "email_unverified", "smtp_code": None}, True, False, "status"),
        ({"template": "weekly_digest"}, True, False, "template_gone"),
        ({"params": MailParams(link=MailLinkKind.token)}, True, False, "token_link"),
        ({"template": MailTemplate.smtp_test.value, "params": MailParams()}, True, False, "smtp_test"),
        ({"next_attempt_at": NOW + timedelta(minutes=3)}, True, False, "retrying"),
        ({"at": NOW - RESEND_WINDOW - timedelta(seconds=1)}, True, False, "too_old"),
        ({}, True, True, "already_resent"),
        ({}, False, False, "smtp_off"),
    ],
)
def test__resend_block__general_rules(over: dict[str, Any], smtp: bool, resent: bool, block: str | None) -> None:
    found = resend_block(_entry(**over), now=NOW, smtp_enabled=smtp, resent=resent)

    assert (found.value if found else None) == block
    if found is not None:
        assert isinstance(found, ResendBlock)


def test__resend_request__page_link_on_the_current_server_and_same_values() -> None:
    entry = _entry()

    request = resend_request(entry, SERVER)
    mail = request.render()

    assert request.origin is MailOrigin.admin_resend
    assert request.link == f"{SERVER}/sign/{PROJECT}/{ROUTE}"
    assert request.ref_kind is MailRefKind.signing_route
    assert request.to_user_id == "u-anna"
    assert f'href="{SERVER}/sign/{PROJECT}/{ROUTE}"' in mail.html
    assert "old.example.org" not in mail.html
    assert "Анна Петрова" in mail.text


def test__resend_request__the_note_is_replaced_by_the_inbox_line() -> None:
    entry = _entry(
        template=MailTemplate.signing_returned.value,
        params=MailParams(
            values={"actor": "Анна Петрова", "project": "ВКР"},
            link=MailLinkKind.page,
            link_path=f"/projects/{PROJECT}/submit/cp/topic",
            note_len=40,
            server=SERVER,
        ),
    )

    request = resend_request(entry, SERVER)
    mail = request.render()

    assert request.note is None
    assert request.note_in_inbox is True
    assert "Сообщение отправителя есть во «Входящих» Студии." in mail.text
    # В журнал новая строка попадёт с этой пометкой, а карточка перерисует ту же строку.
    params = safe_params(request)
    assert params.note_in_inbox is True
    assert params.note_len == 0
    shown = rerender(_entry(template=MailTemplate.signing_returned.value, params=params))
    assert shown is not None
    assert "Сообщение отправителя есть во «Входящих» Студии." in shown.text


def test__resend_request__token_mail_cannot_be_rebuilt() -> None:
    with pytest.raises(ValueError, match="rebuilt"):
        resend_request(_entry(params=MailParams(link=MailLinkKind.token)), SERVER)


def test__resend_request__notice_with_a_fixed_page_and_no_server() -> None:
    entry = _entry(
        template=MailTemplate.passkey_added.value,
        params=MailParams(values={"name": "MacBook"}, link=MailLinkKind.page, link_path="/settings/account"),
        project_id=None,
        ref_kind=MailRefKind.passkey.value,
        ref_id="pk-1",
    )

    request = resend_request(entry, None)

    assert request.link is None
    assert request.link_kind is MailLinkKind.page
    assert "MacBook" in request.render().text
