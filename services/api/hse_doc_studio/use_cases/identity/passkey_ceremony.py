"""Общее для церемоний passkey: одноразовые вызовы, политика установки и свежесть входа."""

from __future__ import annotations

import base64
import secrets
from datetime import datetime

from hse_doc_studio.core.identity.entities import AuthToken, AuthTokenKind, Session
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.normalize import hash_token
from hse_doc_studio.core.identity.passkeys import CHALLENGE_TTL, REAUTH_WINDOW, RelyingParty
from hse_doc_studio.core.identity.protocols import IAuthTokenRepository, ISessionRepository
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.use_cases.identity.auth_settings import AuthSettingsService

CHALLENGE_BYTES = 32


def challenge_text(challenge: bytes) -> str:
    """Вызов в том виде, в каком браузер кладёт его в clientDataJSON (base64url без дополнения)."""
    return base64.urlsafe_b64encode(challenge).rstrip(b"=").decode("ascii")


class PasskeyChallenges:
    """Вызов хранится хешем в `auth_tokens` и гасится атомарно: повтор ответа браузера не проходит."""

    def __init__(self, tokens: IAuthTokenRepository, clock: Clock = utc_now) -> None:
        self._tokens = tokens
        self._clock = clock

    async def issue(self, kind: AuthTokenKind, user_id: str | None) -> bytes:
        challenge = secrets.token_bytes(CHALLENGE_BYTES)
        await self._tokens.add(
            AuthToken(
                token_hash=hash_token(challenge_text(challenge)),
                kind=kind,
                user_id=user_id,
                expires_at=self._clock() + CHALLENGE_TTL,
            )
        )
        return challenge

    async def consume(self, kind: AuthTokenKind, challenge: str) -> AuthToken | None:
        return await self._tokens.consume(hash_token(challenge), kind, self._clock())


class PasskeyPolicy:
    """Passkey доступен, если админ его не выключил и адрес Студии годится для WebAuthn."""

    def __init__(self, settings: AuthSettingsService) -> None:
        self._settings = settings

    async def enabled(self) -> bool:
        return (await self._settings.effective()).passkeys_enabled

    async def require(self, party: RelyingParty | None) -> RelyingParty:
        if party is None or not await self.enabled():
            raise IdentityError(IdentityErrorCode.passkeys_disabled)
        return party


def is_recent(session: Session, now: datetime) -> bool:
    return now - session.authenticated_at <= REAUTH_WINDOW


async def require_recent_auth(sessions: ISessionRepository, id_hash: str | None, user_id: str, now: datetime) -> None:
    """Добавить или удалить ключ можно только сразу после входа или повторного подтверждения личности.

    Украденная cookie сессии одна не даёт закрепиться в аккаунте собственным ключом и не снимает ключи владельца.
    """
    session = await sessions.get(id_hash) if id_hash else None
    if session is None or session.user_id != user_id:
        raise IdentityError(IdentityErrorCode.forbidden)
    if not is_recent(session, now):
        raise IdentityError(IdentityErrorCode.reauth_required)
