"""Почтовик без SMTP: письма не отправляются, ссылки уходят в outbox и показываются на экране."""

from __future__ import annotations


class LinkOnlyMailSender:
    @property
    def enabled(self) -> bool:
        return False

    async def send(self, to: str, subject: str, body: str) -> None:
        raise RuntimeError("SMTP is not configured")
