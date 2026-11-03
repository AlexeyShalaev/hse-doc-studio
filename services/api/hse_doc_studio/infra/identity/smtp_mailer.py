"""Почтовик по SMTP (aiosmtplib): письма Студии, текстом или multipart/alternative с HTML."""

from __future__ import annotations

from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Literal

import aiosmtplib


@dataclass(frozen=True)
class SmtpSettings:
    host: str
    port: int = 587
    security: Literal["starttls", "tls", "none"] = "starttls"
    username: str | None = None
    password: str | None = None
    from_address: str = "no-reply@localhost"
    from_name: str = "HSE Doc Studio"
    timeout_s: float = 10.0
    local_hostname: str | None = None


class SmtpMailSender:
    """Любой сбой (сеть, таймаут, отказ сервера) всплывает исключением: вызывающий кладёт ссылку в outbox."""

    def __init__(self, cfg: SmtpSettings) -> None:
        self._cfg = cfg

    @property
    def enabled(self) -> bool:
        return True

    async def send(self, to: str, subject: str, body: str, *, html: str | None = None) -> None:
        cfg = self._cfg
        message = EmailMessage()
        message["From"] = formataddr((cfg.from_name, cfg.from_address))
        message["To"] = to
        # Перевод строки в теме дал бы подмену заголовков: письма Студии его не содержат, но не полагаемся на это.
        message["Subject"] = " ".join(subject.split())
        message["Message-ID"] = make_msgid(domain=cfg.from_address.rpartition("@")[2] or None)
        message["Auto-Submitted"] = "auto-generated"
        message.set_content(body)
        if html is not None:
            message.add_alternative(html, subtype="html")
        await aiosmtplib.send(
            message,
            hostname=cfg.host,
            port=cfg.port,
            use_tls=cfg.security == "tls",
            start_tls=cfg.security == "starttls",
            username=cfg.username or None,
            password=cfg.password or None,
            timeout=cfg.timeout_s,
            # без этого aiosmtplib зовёт socket.getfqdn() (обратный DNS), который может висеть дольше timeout
            local_hostname=cfg.local_hostname or cfg.from_address.rpartition("@")[2] or "localhost",
        )
