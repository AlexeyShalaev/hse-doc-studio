"""Персональные токены доступа: выпуск, список, смена прав, отзыв. Сам токен виден один раз, в хранилище лежит его хеш.

Какие права можно дать токену, решает одно правило `require_grantable` и при выпуске, и при смене прав:
`mcp:admin` только админу установки (M7 в docs/design/mcp.md), токену устройства (device flow) только git.
Остальные права (`packs`, `sign`) выдаются любому: доступ к разделу и ключу проверяется на каждом запросе.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import timedelta

from hse_doc_studio.core.identity.entities import ApiToken, ApiTokenOrigin, TokenScope
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.normalize import hash_token, new_pat, pat_display_prefix
from hse_doc_studio.core.identity.protocols import IApiTokenRepository, IAuditLog
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.uow import IUnitOfWork

# Права, которые даёт только админ установки самому себе: админские тулы MCP.
ADMIN_ONLY_SCOPES: frozenset[TokenScope] = frozenset({TokenScope.mcp_admin})
# Токен устройства выдаётся для git (device flow) и остаётся токеном для git.
DEVICE_SCOPES: frozenset[TokenScope] = frozenset({TokenScope.git_read, TokenScope.git_write})


def require_grantable(scopes: frozenset[TokenScope], *, instance_admin: bool, origin: ApiTokenOrigin) -> None:
    """Отказ `token_scope_not_allowed`, если среди прав есть недоступное человеку или виду токена."""
    if not scopes:
        raise IdentityError(IdentityErrorCode.token_scope_not_allowed)
    if origin is ApiTokenOrigin.device and not scopes <= DEVICE_SCOPES:
        raise IdentityError(IdentityErrorCode.token_scope_not_allowed)
    if not instance_admin and scopes & ADMIN_ONLY_SCOPES:
        raise IdentityError(IdentityErrorCode.token_scope_not_allowed)


def _scope_names(scopes: frozenset[TokenScope]) -> list[str]:
    return sorted(s.value for s in scopes)


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
        instance_admin: bool = False,
    ) -> CreatedApiToken:
        require_grantable(scopes, instance_admin=instance_admin, origin=origin)
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
        details: dict[str, object] = {"name": token.name, "scopes": _scope_names(scopes)}
        if origin is not ApiTokenOrigin.manual:
            details["origin"] = origin.value
        async with self._uow.begin():
            await self._tokens.add(token)
            await self._audit.record("pat.create", actor_id=user_id, target=token.id, details=details)
        return CreatedApiToken(secret=secret, item=token)


def _require_change_grantable(
    token: ApiToken, scopes: frozenset[TokenScope], added: frozenset[TokenScope], *, instance_admin: bool
) -> None:
    """Убрать можно любое право, проверяем только добавленные: у бывшего админа `mcp:admin` не мешает дать токену
    другое право. У токена устройства весь набор остаётся только git. Пустой набор не принимается."""
    if not scopes:
        raise IdentityError(IdentityErrorCode.token_scope_not_allowed)
    if token.origin is ApiTokenOrigin.device:
        require_grantable(scopes, instance_admin=instance_admin, origin=token.origin)
    elif added:
        require_grantable(added, instance_admin=instance_admin, origin=token.origin)


@dataclass(frozen=True)
class ApiTokenScopesChange:
    item: ApiToken
    added: frozenset[TokenScope]
    removed: frozenset[TokenScope]

    @property
    def changed(self) -> bool:
        return bool(self.added or self.removed)


class UpdateApiTokenScopesUC:
    """Смена прав существующего токена: значение токена то же, клиентам не нужно его менять.

    Зовёт только маршрут с сессией (токен прав токенам не меняет). Новые права проходят то же правило, что при
    выпуске; убрать можно любое. Истёкший токен не правится, отозванного нет вовсе (`not_found`).
    Резолвер читает токен из базы на каждый запрос, поэтому новые права действуют со следующего запроса.
    """

    def __init__(self, tokens: IApiTokenRepository, audit: IAuditLog, uow: IUnitOfWork, clock: Clock = utc_now) -> None:
        self._tokens = tokens
        self._audit = audit
        self._uow = uow
        self._clock = clock

    async def execute(
        self, user_id: str, token_id: str, scopes: frozenset[TokenScope], *, instance_admin: bool = False
    ) -> ApiTokenScopesChange:
        async with self._uow.begin():
            token = await self._tokens.get(user_id, token_id)
            if token is None:
                raise IdentityError(IdentityErrorCode.not_found)
            if token.expires_at is not None and self._clock() >= token.expires_at:
                raise IdentityError(IdentityErrorCode.api_token_expired)
            added = scopes - token.scopes
            removed = token.scopes - scopes
            if not added and not removed:
                return ApiTokenScopesChange(item=token, added=added, removed=removed)
            _require_change_grantable(token, scopes, added, instance_admin=instance_admin)
            if not await self._tokens.set_scopes(user_id, token_id, scopes):
                raise IdentityError(IdentityErrorCode.not_found)
            await self._audit.record(
                "pat.scopes_update",
                actor_id=user_id,
                target=token_id,
                details={
                    "name": token.name,
                    "added": _scope_names(added),
                    "removed": _scope_names(removed),
                    "scopes": _scope_names(scopes),
                },
            )
        return ApiTokenScopesChange(item=replace(token, scopes=scopes), added=added, removed=removed)


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
