"""Письма доставки: тема, текст и HTML на языке получателя, срок действия, экранирование имён."""

from __future__ import annotations

from datetime import timedelta

import pytest
from hse_doc_studio.core.i18n import set_interface_language
from hse_doc_studio.core.identity.entities import MailKind
from hse_doc_studio.use_cases.identity.mail import LinkDelivery

from .conftest import T0, FakeSender, World

SERVER = "https://studio.test"


def _delivery(world: World, sender: FakeSender) -> LinkDelivery:
    return LinkDelivery(sender, world.outbox, public_url=SERVER)


@pytest.fixture(autouse=True)
def _reset_language() -> None:
    set_interface_language(None)


@pytest.mark.parametrize(
    ("locale", "subject", "lead"),
    [("ru", "Подтвердите e-mail", "Осталось подтвердить"), ("en", "Confirm your email", "One step left")],
)
async def test__verify_mail__language_of_the_account_with_html_and_ttl(
    world: World, locale: str, subject: str, lead: str
) -> None:
    sender = FakeSender(enabled=True)

    shown = await _delivery(world, sender).deliver(
        MailKind.verify_email, "ann@example.org", f"{SERVER}/verify/tok", T0, locale=locale, ttl=timedelta(hours=48)
    )

    assert shown is None
    [(to, got_subject, body)] = sender.sent
    [html] = sender.html
    assert (to, got_subject) == ("ann@example.org", subject)
    assert lead in body
    assert html is not None
    assert lead in html
    assert f'href="{SERVER}/verify/tok"' in html
    assert f"\n{SERVER}/verify/tok\n" in body


async def test__language__without_account_locale_follows_the_interface_language_of_the_request() -> None:
    world_sender = FakeSender(enabled=True)
    set_interface_language("en")

    class _Outbox:
        async def add(self, entry: object) -> None: ...

    await LinkDelivery(world_sender, _Outbox(), public_url=SERVER).deliver(  # type: ignore[arg-type]
        MailKind.invite, "new@example.org", f"{SERVER}/invite/t", T0, params={"inviter": "Anna"}
    )

    assert world_sender.sent[0][1] == "Invitation to the Studio"
    assert "Anna invites you to the Studio" in world_sender.sent[0][2]


async def test__language__account_locale_wins_over_the_request_language(world: World) -> None:
    sender = FakeSender(enabled=True)
    set_interface_language("en")

    await _delivery(world, sender).deliver(
        MailKind.reset_password, "ann@example.org", f"{SERVER}/reset/t", T0, locale="ru"
    )

    assert sender.sent[0][1] == "Сброс пароля"


async def test__language__default_is_russian(world: World) -> None:
    sender = FakeSender(enabled=True)

    await _delivery(world, sender).deliver(MailKind.reset_password, "ann@example.org", f"{SERVER}/reset/t", T0)

    assert sender.sent[0][1] == "Сброс пароля"


async def test__notice__escapes_the_passkey_name_in_html_and_keeps_it_in_text(world: World) -> None:
    sender = FakeSender(enabled=True)

    sent = await _delivery(world, sender).notify(
        MailKind.passkey_added, "ann@example.org", locale="en", params={"name": '<img src=x onerror="a()">'}
    )

    assert sent is True
    [html] = sender.html
    assert html is not None
    assert "<img" not in html
    assert "&lt;img src=x onerror=&quot;a()&quot;&gt;" in html
    assert '<img src=x onerror="a()">' in sender.sent[0][2]


async def test__notice__reset_notice_has_no_link_and_points_to_the_administrator(world: World) -> None:
    sender = FakeSender(enabled=True)

    await _delivery(world, sender).notify(MailKind.reset_notice, "ann@example.org", locale="en")

    [(_, subject, body)] = sender.sent
    assert subject == "An administrator issued a password reset link"
    assert "contact the administrator" in body
    assert "/reset" not in (sender.html[0] or "")


async def test__no_smtp__nothing_is_rendered_or_sent_and_the_link_is_returned(world: World) -> None:
    sender = FakeSender(enabled=False)

    shown = await _delivery(world, sender).deliver(
        MailKind.reset_password, "ann@example.org", f"{SERVER}/reset/t", T0, ttl=timedelta(hours=1)
    )

    assert shown == f"{SERVER}/reset/t"
    assert sender.sent == []
