"""Вход устройства в git сервера по коду (device flow, RFC 8628 по смыслу): типы и порт хранилища.

Устройство (локальная Студия, CLI) знает секретный `device_code` (в БД только хеш), человек на сайте вводит
короткий `user_code` и выбирает права. Подтверждение выпускает токен доступа `origin = device` со scope только
git; его секрет лежит шифртекстом до выдачи устройству и выдаётся ровно один раз.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol

DEVICE_CODE_PREFIX = "hsdv_"
DEVICE_TTL = timedelta(minutes=10)
DEVICE_INTERVAL_S = 5
# RFC 8628: после slow_down клиент добавляет к интервалу 5 секунд.
DEVICE_SLOW_DOWN_S = 5
DEVICE_TOKEN_DAYS = 90
DEVICE_KEEP = timedelta(days=1)


class DeviceStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    denied = "denied"
    delivered = "delivered"
    # Вычисляется: pending после срока.
    expired = "expired"


class DeviceClientKind(StrEnum):
    desktop = "desktop"
    cli = "cli"


class DeviceTokenErrorCode(StrEnum):
    authorization_pending = "authorization_pending"
    slow_down = "slow_down"
    access_denied = "access_denied"
    expired_token = "expired_token"  # noqa: S105 — код протокола, не секрет


@dataclass(frozen=True)
class DeviceAuthorization:
    id: str
    device_code_hash: str
    user_code: str
    client_name: str
    client_kind: DeviceClientKind
    requested_scopes: tuple[str, ...]
    status: DeviceStatus
    created_at: datetime
    expires_at: datetime
    client_ip: str | None = None
    granted_scopes: tuple[str, ...] | None = None
    user_id: str | None = None
    token_id: str | None = None
    token_secret_enc: str | None = None
    decided_at: datetime | None = None
    last_polled_at: datetime | None = None

    def expired_at(self, now: datetime) -> bool:
        return self.expires_at <= now


class IDeviceAuthorizationRepository(Protocol):
    async def add(self, item: DeviceAuthorization) -> None: ...
    async def get_by_user_code(self, user_code: str) -> DeviceAuthorization | None: ...
    async def get_by_device_hash(self, device_code_hash: str) -> DeviceAuthorization | None: ...
    async def touch_poll(self, item_id: str, now: datetime) -> None: ...
    async def decide(  # noqa: PLR0913 — поля решения
        self,
        item_id: str,
        status: DeviceStatus,
        *,
        user_id: str,
        now: datetime,
        granted_scopes: tuple[str, ...] | None = None,
        token_id: str | None = None,
        token_secret_enc: str | None = None,
    ) -> bool:
        """pending -> approved или denied; False, если запись уже не pending."""
        ...

    async def deliver(self, item_id: str) -> bool:
        """approved -> delivered со стиранием шифртекста; False, если выдача уже была."""
        ...

    async def purge(self, older_than: datetime) -> int: ...
