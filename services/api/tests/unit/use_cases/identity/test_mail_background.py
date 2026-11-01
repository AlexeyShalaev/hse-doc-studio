"""Фоновая доставка писем: запрос не ждёт SMTP, сбой оставляет ссылку в outbox."""

from __future__ import annotations

import asyncio

from hse_doc_studio.core.identity.entities import MailKind
from hse_doc_studio.use_cases.identity.mail import LinkDelivery

from .conftest import T0, FakeSender, World


class _SlowSender(FakeSender):
    def __init__(self, release: asyncio.Event, *, fail: bool = False) -> None:
        super().__init__(enabled=True, fail=fail)
        self._release = release

    async def send(self, to: str, subject: str, body: str) -> None:
        await self._release.wait()
        await super().send(to, subject, body)


async def test_background_delivery_does_not_wait_for_smtp(world: World) -> None:
    release = asyncio.Event()
    sender = _SlowSender(release)
    delivery = LinkDelivery(sender, world.outbox, background=True)

    result = await asyncio.wait_for(
        delivery.deliver(MailKind.reset_password, "ann@example.org", "https://studio.test/reset/t", T0), timeout=1
    )

    assert result is None
    assert sender.sent == []
    release.set()
    await delivery.drain()
    assert [to for to, _s, _b in sender.sent] == ["ann@example.org"]


async def test_background_failure_keeps_the_link_in_outbox(world: World) -> None:
    release = asyncio.Event()
    release.set()
    delivery = LinkDelivery(_SlowSender(release, fail=True), world.outbox, background=True)

    result = await delivery.deliver(MailKind.reset_password, "ann@example.org", "https://studio.test/reset/t", T0)
    await delivery.drain()

    assert result is None
    assert [(e.kind, e.link) for e in await world.outbox.list_active(T0)] == [(MailKind.reset_password, "")]
