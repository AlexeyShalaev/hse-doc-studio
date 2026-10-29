"""Почтовик по настройкам установки: окружение, иначе правка админа. Новые настройки действуют без перезапуска."""

from __future__ import annotations

import time

from hse_doc_studio.core.identity.smtp_settings import SmtpParams
from hse_doc_studio.infra.identity.smtp_mailer import SmtpMailSender, SmtpSettings
from hse_doc_studio.use_cases.identity.smtp_settings import SmtpSettingsService

# Другой экземпляр сервера узнаёт о правке не позже чем через столько секунд.
_REFRESH_AFTER_S = 30.0


def _as_settings(params: SmtpParams) -> SmtpSettings:
    return SmtpSettings(
        host=params.host,
        port=params.port,
        security=params.security,
        username=params.username,
        password=params.password,
        from_address=params.from_address,
        from_name=params.from_name,
        timeout_s=params.timeout_s,
    )


class ConfiguredMailSender:
    """`enabled` читается без ожидания, поэтому держит последнее известное состояние; `refresh` его обновляет."""

    def __init__(self, service: SmtpSettingsService) -> None:
        self._service = service
        self._sender: SmtpMailSender | None = None
        self._loaded_at = 0.0

    @property
    def enabled(self) -> bool:
        return self._sender is not None

    async def refresh(self) -> None:
        params = await self._service.params()
        self._sender = SmtpMailSender(_as_settings(params)) if params is not None else None
        self._loaded_at = time.monotonic()

    async def send(self, to: str, subject: str, body: str) -> None:
        if time.monotonic() - self._loaded_at > _REFRESH_AFTER_S:
            await self.refresh()
        if self._sender is None:
            raise RuntimeError("SMTP is not configured")
        await self._sender.send(to, subject, body)
