"""Периодическая чистка устаревших записей аутентификации.

Просроченные сессии, одноразовые токены, письма outbox (в них лежат ссылки сброса и подтверждения) и
счётчики неудачных входов сами не исчезают: без чистки таблицы растут, а старые ссылки остаются в дампе БД.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import structlog

from hse_doc_studio.core.identity.protocols import (
    IAuthTokenRepository,
    ILoginAttemptRepository,
    IMailOutboxRepository,
    ISessionRepository,
)
from hse_doc_studio.core.identity.session_policy import MAX_LOGIN_DELAY, Clock, utc_now

logger = structlog.get_logger(__name__)

# Счётчик нужен, пока может действовать задержка входа; с запасом, чтобы не снять блокировку раньше срока.
LOGIN_ATTEMPT_TTL = MAX_LOGIN_DELAY * 4


@dataclass
class AuthCleanupReport:
    sessions: int = 0
    auth_tokens: int = 0
    mail_outbox: int = 0
    login_attempts: int = 0


class AuthCleanupService:
    def __init__(
        self,
        sessions: ISessionRepository,
        auth_tokens: IAuthTokenRepository,
        outbox: IMailOutboxRepository,
        attempts: ILoginAttemptRepository,
        *,
        attempt_ttl: timedelta = LOGIN_ATTEMPT_TTL,
        clock: Clock = utc_now,
    ) -> None:
        self._sessions = sessions
        self._auth_tokens = auth_tokens
        self._outbox = outbox
        self._attempts = attempts
        self._attempt_ttl = attempt_ttl
        self._clock = clock

    async def run(self) -> AuthCleanupReport:
        """Удаляет просроченное; сбой одной таблицы не мешает остальным, но не скрывается."""
        now = self._clock()
        report = AuthCleanupReport()
        failed = 0
        for name, delete in (
            ("sessions", lambda: self._sessions.delete_expired(now)),
            ("auth_tokens", lambda: self._auth_tokens.delete_expired(now)),
            ("mail_outbox", lambda: self._outbox.delete_expired(now)),
            ("login_attempts", lambda: self._attempts.delete_stale(now - self._attempt_ttl)),
        ):
            try:
                setattr(report, name, await delete())
            except Exception:
                failed += 1
                logger.exception("auth_cleanup_step_failed", step=name)
        if failed:
            raise RuntimeError(f"auth cleanup: шагов с ошибкой {failed}")
        logger.info("auth_cleanup_done", **vars(report))
        return report
