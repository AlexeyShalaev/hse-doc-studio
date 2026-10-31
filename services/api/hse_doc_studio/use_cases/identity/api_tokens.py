"""Персональные токены доступа: выпуск, список, отзыв. Сам токен виден один раз, в хранилище лежит его хеш."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta

from hse_doc_studio.core.identity.entities import ApiToken, ApiTokenOrigin, TokenScope
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.normalize import hash_token, new_pat, pat_display_prefix
from hse_doc_studio.core.identity.protocols import IApiTokenRepository, IAuditLog
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.uow import IUnitOfWork


@dataclass(frozen=True)
class CreatedApiToken:
    # Открытое значение токена: после ответа его не получить.
    secret: str
    item: ApiToken


class ListApiTokensUC:
    def __init__(self, tokens: IApiTokenRepository) -> None:
        self._tokens = tokens

    async def execute(self, user_id: str) -> list[ApiToken]:
        return await self._tokens.list_for_user(user_id)


class CreateApiTokenUC:
    def __init__(self, tokens: IApiTokenRepository, audit: IAuditLog, uow: IUnitOfWork, clock: Clock = utc_now) -> None:
        self._tokens = tokens
        self._audit = audit
        self._uow = uow
        self._clock = clock

    async def execute(  # noqa: PLR0913 — происхождение и устройство приходят только из device flow
        self,
        user_id: str,
        name: str,
        scopes: frozenset[TokenScope],
        expires_in_days: int | None,
        *,
        origin: ApiTokenOrigin = ApiTokenOrigin.manual,
        client_name: str | None = None,
        client_kind: str | None = None,
    ) -> CreatedApiToken:
        now = self._clock()
        secret = new_pat()
        token = ApiToken(
            id=f"pat_{uuid.uuid4().hex}",
            user_id=user_id,
            name=name.strip(),
            token_hash=hash_token(secret),
            prefix=pat_display_prefix(secret),
            scopes=scopes,
            created_at=now,
            expires_at=now + timedelta(days=expires_in_days) if expires_in_days else None,
            origin=origin,
            client_name=client_name,
            client_kind=client_kind,
        )
        details: dict[str, object] = {"name": token.name, "scopes": sorted(s.value for s in scopes)}
        if origin is not ApiTokenOrigin.manual:
            details["origin"] = origin.value
        async with self._uow.begin():
            await self._tokens.add(token)
            await self._audit.record("pat.create", actor_id=user_id, target=token.id, details=details)
        return CreatedApiToken(secret=secret, item=token)


class RevokeApiTokenUC:
    def __init__(self, tokens: IApiTokenRepository, audit: IAuditLog, uow: IUnitOfWork) -> None:
        self._tokens = tokens
        self._audit = audit
        self._uow = uow

    async def execute(self, user_id: str, token_id: str) -> None:
        """Чужой токен неотличим от несуществующего: оба дают `not_found`."""
        async with self._uow.begin():
            if not await self._tokens.delete(user_id, token_id):
                raise IdentityError(IdentityErrorCode.not_found)
            await self._audit.record("pat.revoke", actor_id=user_id, target=token_id)
