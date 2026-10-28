"""Почтовик по SMTP (aiosmtplib): подтверждение адреса и сброс пароля."""

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


class SmtpMailSender:
    """Любой сбой (сеть, таймаут, отказ сервера) всплывает исключением: вызывающий кладёт ссылку в outbox."""

    def __init__(self, cfg: SmtpSettings) -> None:
        self._cfg = cfg

    @property
    def enabled(self) -> bool:
        return True

    async def send(self, to: str, subject: str, body: str) -> None:
        cfg = self._cfg
        message = EmailMessage()
        message["From"] = formataddr((cfg.from_name, cfg.from_address))
        message["To"] = to
        message["Subject"] = subject
        message["Message-ID"] = make_msgid(domain=cfg.from_address.rpartition("@")[2] or None)
        message["Auto-Submitted"] = "auto-generated"
        message.set_content(body)
        await aiosmtplib.send(
            message,
            hostname=cfg.host,
            port=cfg.port,
            use_tls=cfg.security == "tls",
            start_tls=cfg.security == "starttls",
            username=cfg.username or None,
            password=cfg.password or None,
            timeout=cfg.timeout_s,
        )
