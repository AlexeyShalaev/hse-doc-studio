"""Вход устройства по коду (device flow) для git сервера: начало, опрос, страница /device, решение человека.

Подтверждает только вошедший по сессии (не токеном): украденный токен не должен выдавать новые токены.
Выданный токен это обычный токен доступа (`api_tokens`, origin = device) со scope только git и сроком 90 дней.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field, replace
from datetime import timedelta

from hse_doc_studio.core.access.entities import Actor, ActorSource
from hse_doc_studio.core.device_codes import new_device_secret, new_user_code, normalize_user_code
from hse_doc_studio.core.git_remote.device import (
    DEVICE_CODE_PREFIX,
    DEVICE_INTERVAL_S,
    DEVICE_KEEP,
    DEVICE_TOKEN_DAYS,
    DEVICE_TTL,
    DeviceAuthorization,
    DeviceClientKind,
    DeviceStatus,
    DeviceTokenErrorCode,
    IDeviceAuthorizationRepository,
)
from hse_doc_studio.core.git_remote.entities import GIT_SCOPES
from hse_doc_studio.core.git_sync.protocols import ISecretCipher
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.identity.entities import ApiTokenOrigin, TokenScope
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.protocols import IAuditLog
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.secrets import column_aad
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.identity.api_tokens import CreateApiTokenUC, RevokeApiTokenUC

_MAX_USER_CODE_ATTEMPTS = 5
# Опрос немного чаще интервала прощается: часы и сеть неточны.
_POLL_SLACK = timedelta(seconds=0.5)


@dataclass(frozen=True)
class DeviceStarted:
    device_code: str = field(repr=False)
    user_code: str
    expires_in: int
    interval: int


@dataclass(frozen=True)
class DevicePoll:
    access_token: str | None = field(default=None, repr=False)
    scopes: tuple[str, ...] = ()
    expires_in: int = 0
    error: DeviceTokenErrorCode | None = None


def _hash(device_code: str) -> str:
    return hashlib.sha256(device_code.encode("utf-8")).hexdigest()


def _aad(item_id: str) -> str:
    return column_aad("device_authorizations", "token_secret_enc", item_id)


def _ordered(scopes: set[str]) -> tuple[str, ...]:
    return tuple(sorted(scopes))


class DeviceFlowService:
    def __init__(  # noqa: PLR0913 — порты одного сценария
        self,
        items: IDeviceAuthorizationRepository,
        create_token: CreateApiTokenUC,
        revoke_token: RevokeApiTokenUC,
        cipher: ISecretCipher,
        audit: IAuditLog,
        uow: IUnitOfWork,
        *,
        clock: Clock = utc_now,
    ) -> None:
        self._items = items
        self._create_token = create_token
        self._revoke_token = revoke_token
        self._cipher = cipher
        self._audit = audit
        self._uow = uow
        self._clock = clock

    async def start(
        self, client_name: str, client_kind: DeviceClientKind, scopes: list[str], client_ip: str | None
    ) -> DeviceStarted:
        requested = set(scopes)
        if not requested or not requested <= GIT_SCOPES:
            raise IdentityError(IdentityErrorCode.device_scope_invalid)
        requested.add(TokenScope.git_read.value)
        now = self._clock()
        for _ in range(_MAX_USER_CODE_ATTEMPTS):
            user_code = new_user_code()
            if await self._items.get_by_user_code(user_code) is None:
                break
        else:
            raise RuntimeError("could not allocate a free user code")
        device_code = new_device_secret(DEVICE_CODE_PREFIX)
        await self._items.add(
            DeviceAuthorization(
                id=uuid.uuid4().hex,
                device_code_hash=_hash(device_code),
                user_code=user_code,
                client_name=" ".join(client_name.split())[:128] or "device",
                client_kind=client_kind,
                requested_scopes=_ordered(requested),
                status=DeviceStatus.pending,
                created_at=now,
                expires_at=now + DEVICE_TTL,
                client_ip=client_ip,
            )
        )
        return DeviceStarted(device_code, user_code, int(DEVICE_TTL.total_seconds()), DEVICE_INTERVAL_S)

    async def poll(self, device_code: str) -> DevicePoll:
        """Токен выдаётся ровно один раз; опрос чаще интервала даёт `slow_down` (RFC 8628, 3.5)."""
        item = await self._items.get_by_device_hash(_hash(device_code))
        now = self._clock()
        if item is None:
            return DevicePoll(error=DeviceTokenErrorCode.expired_token)
        too_soon = (
            item.last_polled_at is not None
            and now - item.last_polled_at < timedelta(seconds=DEVICE_INTERVAL_S) - _POLL_SLACK
        )
        await self._items.touch_poll(item.id, now)
        if too_soon:
            return DevicePoll(error=DeviceTokenErrorCode.slow_down)
        if item.status is DeviceStatus.approved and item.token_secret_enc is not None:
            return await self._deliver(item)
        if item.status is DeviceStatus.denied:
            return DevicePoll(error=DeviceTokenErrorCode.access_denied)
        if item.status is DeviceStatus.pending and not item.expired_at(now):
            return DevicePoll(error=DeviceTokenErrorCode.authorization_pending)
        return DevicePoll(error=DeviceTokenErrorCode.expired_token)

    async def _deliver(self, item: DeviceAuthorization) -> DevicePoll:
        assert item.token_secret_enc is not None  # noqa: S101 — проверено вызывающим
        secret = self._cipher.decrypt(item.token_secret_enc, aad=_aad(item.id)).reveal()
        if not await self._items.deliver(item.id):
            return DevicePoll(error=DeviceTokenErrorCode.expired_token)
        return DevicePoll(
            access_token=secret,
            scopes=item.granted_scopes or (),
            expires_in=int(timedelta(days=DEVICE_TOKEN_DAYS).total_seconds()),
        )

    async def info(self, actor: Actor, user_code: str) -> DeviceAuthorization:
        owner = self._owner(actor)
        item = await self._find(user_code)
        if item.status is not DeviceStatus.pending and item.user_id != owner:
            raise IdentityError(IdentityErrorCode.device_code_invalid)
        if item.status is DeviceStatus.pending and item.expired_at(self._clock()):
            raise IdentityError(IdentityErrorCode.device_code_expired)
        return self._view(item)

    async def decide(self, actor: Actor, user_code: str, *, approve: bool, scopes: list[str]) -> DeviceAuthorization:
        owner = self._owner(actor)
        item = await self._find(user_code)
        now = self._clock()
        if item.status is not DeviceStatus.pending:
            raise IdentityError(IdentityErrorCode.device_code_used)
        if item.expired_at(now):
            raise IdentityError(IdentityErrorCode.device_code_expired)
        details = {"client_name": item.client_name, "client_kind": item.client_kind.value, "ip": item.client_ip}
        if not approve:
            async with self._uow.begin():
                if not await self._items.decide(item.id, DeviceStatus.denied, user_id=owner, now=now):
                    raise IdentityError(IdentityErrorCode.device_code_used)
                await self._audit.record("device.deny", actor_id=owner, target=None, details=details)
            return self._view(await self._find(user_code))
        granted = self._granted(item, scopes)
        created = await self._create_token.execute(
            owner,
            item.client_name,
            frozenset(TokenScope(s) for s in granted),
            DEVICE_TOKEN_DAYS,
            origin=ApiTokenOrigin.device,
            client_name=item.client_name,
            client_kind=item.client_kind.value,
        )
        secret_enc = self._cipher.encrypt(Secret(created.secret), aad=_aad(item.id))
        async with self._uow.begin():
            decided = await self._items.decide(
                item.id,
                DeviceStatus.approved,
                user_id=owner,
                now=now,
                granted_scopes=granted,
                token_id=created.item.id,
                token_secret_enc=secret_enc,
            )
            if decided:
                await self._audit.record(
                    "device.approve", actor_id=owner, target=created.item.id, details={**details, "scopes": granted}
                )
        if not decided:
            # Гонка двух решений: токен, который никто не получит, сразу отзывается.
            await self._revoke_token.execute(owner, created.item.id)
            raise IdentityError(IdentityErrorCode.device_code_used)
        return self._view(await self._find(user_code))

    @staticmethod
    def _granted(item: DeviceAuthorization, scopes: list[str]) -> tuple[str, ...]:
        """Права подмножество запрошенных; чтение есть всегда, без него токен бесполезен."""
        chosen = set(scopes) | {TokenScope.git_read.value}
        if not chosen <= set(item.requested_scopes):
            raise IdentityError(IdentityErrorCode.device_scope_invalid)
        return _ordered(chosen)

    async def purge(self) -> int:
        return await self._items.purge(self._clock() - DEVICE_KEEP)

    @staticmethod
    def _owner(actor: Actor) -> str:
        if actor.id is None:
            raise IdentityError(IdentityErrorCode.auth_required)
        if actor.source is not ActorSource.session:
            # Подтверждать может только человек в браузере, не токен.
            raise IdentityError(IdentityErrorCode.forbidden)
        return actor.id

    async def _find(self, user_code: str) -> DeviceAuthorization:
        code = normalize_user_code(user_code)
        item = await self._items.get_by_user_code(code) if code is not None else None
        if item is None:
            raise IdentityError(IdentityErrorCode.device_code_invalid)
        return item

    def _view(self, item: DeviceAuthorization) -> DeviceAuthorization:
        status = item.status
        if status is DeviceStatus.pending and item.expired_at(self._clock()):
            status = DeviceStatus.expired
        return replace(item, device_code_hash="", token_secret_enc=None, status=status)
