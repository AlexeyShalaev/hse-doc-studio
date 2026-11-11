"""Почтовик без SMTP: письма не отправляются (в журнале писем `not_sent`), ссылки показываются на экране."""

from __future__ import annotations

from hse_doc_studio.core.mail.journal import MailFailure, MailFailureClass, MailSendError


class LinkOnlyMailSender:
    @property
    def enabled(self) -> bool:
        return False

    async def send(self, to: str, subject: str, body: str, *, html: str | None = None) -> str:
        raise MailSendError(MailFailure(reason=MailFailureClass.smtp_off, text="SMTP is not configured"))
