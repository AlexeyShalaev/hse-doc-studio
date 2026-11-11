"""Фоновая доставка писем: запрос не ждёт SMTP, сбой виден в журнале писем без ссылки."""

from __future__ import annotations

import asyncio

from hse_doc_studio.core.access.context import set_current_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.entities import MailKind
from hse_doc_studio.core.mail.journal import MailCause, MailOrigin, MailStatus
from hse_doc_studio.use_cases.identity.mail import LinkDelivery

from .conftest import FakeSender, World


class _SlowSender(FakeSender):
    def __init__(self, release: asyncio.Event, *, fail: bool = False) -> None:
        super().__init__(enabled=True, fail=fail)
        self._release = release

    async def send(self, to: str, subject: str, body: str, *, html: str | None = None) -> str:
        await self._release.wait()
        return await super().send(to, subject, body, html=html)


async def test_background_delivery_does_not_wait_for_smtp(world: World) -> None:
    release = asyncio.Event()
    sender = _SlowSender(release)
    delivery = LinkDelivery(world.dispatcher(sender), background=True)

    result = await asyncio.wait_for(
        delivery.deliver(
            MailKind.reset_password, "ann@example.org", "https://studio.test/reset/t", origin=MailOrigin.forgot_password
        ),
        timeout=1,
    )

    assert result is None
    assert sender.sent == []
    release.set()
    await delivery.drain()
    assert [to for to, _s, _b in sender.sent] == ["ann@example.org"]


async def test_background_failure_is_logged_without_the_link(world: World) -> None:
    release = asyncio.Event()
    release.set()
    delivery = LinkDelivery(world.dispatcher(_SlowSender(release, fail=True)), background=True)

    result = await delivery.deliver(
        MailKind.reset_password,
        "ann@example.org",
        "https://studio.test/reset/secret-t",
        origin=MailOrigin.forgot_password,
    )
    await delivery.drain()

    assert result is None
    (entry,) = world.mail_log.entries
    assert (entry.template, entry.status, entry.origin) == (
        MailKind.reset_password,
        MailStatus.failed,
        "forgot_password",
    )
    assert "secret-t" not in repr(entry)


async def test_background_send_keeps_the_caller_of_the_request(world: World) -> None:
    """Задача отправки копирует контекст запроса: в журнале тот, кто вызвал письмо, а не «фоновая задача»."""
    release = asyncio.Event()
    release.set()
    delivery = LinkDelivery(world.dispatcher(_SlowSender(release)), background=True)

    async def request() -> None:
        # Своя копия контекста, как у запроса: актор не утекает в другие тесты.
        set_current_actor(Actor.user("admin", is_instance_admin=True))
        await delivery.deliver(
            MailKind.invite, "new@example.org", "https://studio.test/invite/t", origin=MailOrigin.admin_invite
        )

    await asyncio.create_task(request())
    await delivery.drain()

    (entry,) = world.mail_log.entries
    assert (entry.status, entry.cause, entry.actor_user_id) == (MailStatus.sent, MailCause.user, "admin")
