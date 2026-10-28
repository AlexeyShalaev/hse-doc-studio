"""Состояние входа для клиента: нужен ли мастер первого запуска, способы входа, текущий пользователь."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from hse_doc_studio.core.identity.entities import AuthSettings, Session, User
from hse_doc_studio.core.identity.passwords import PASSWORD_MIN_LENGTH
from hse_doc_studio.use_cases.identity.auth_settings import AuthSettingsService
from hse_doc_studio.use_cases.identity.sessions import SessionService
from hse_doc_studio.use_cases.server_setup.state import SetupStateService

SetupState = Literal["needs_admin", "ready"]


@dataclass(frozen=True)
class BootstrapResult:
    setup_state: SetupState
    auth: AuthSettings
    smtp_enabled: bool
    password_min_length: int
    user: User | None
    session: Session | None


class BootstrapUC:
    def __init__(
        self,
        setup: SetupStateService,
        settings: AuthSettingsService,
        sessions: SessionService,
        *,
        smtp_enabled: bool = False,
    ) -> None:
        self._setup = setup
        self._settings = settings
        self._sessions = sessions
        self._smtp_enabled = smtp_enabled

    async def auth_settings(self) -> AuthSettings:
        return await self._settings.effective()

    async def execute(self, session_secret: str | None) -> BootstrapResult:
        """Пока мастер первого запуска не завершён, клиент ведёт к нему (/first-run)."""
        needs_admin = not await self._setup.is_completed()
        resolved = await self._sessions.resolve(session_secret) if session_secret else None
        return BootstrapResult(
            setup_state="needs_admin" if needs_admin else "ready",
            auth=await self.auth_settings(),
            smtp_enabled=self._smtp_enabled,
            password_min_length=PASSWORD_MIN_LENGTH,
            user=resolved.user if resolved else None,
            session=resolved.session if resolved else None,
        )
