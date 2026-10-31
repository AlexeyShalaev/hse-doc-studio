"""Сопряжение раннера по коду устройства (device code): локальная Студия получает личный токен регистрации.

Устройство знает секретный `device_code` (в БД только хеш), человек на сайте вводит короткий `user_code`.
Подтверждение создаёт личный токен регистрации, секрет которого лежит шифртекстом в записи до выдачи
устройству; выдаётся он ровно один раз, после чего стирается.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol

from hse_doc_studio.core.device_codes import (
    USER_CODE_ALPHABET,
    USER_CODE_HALF,
    new_device_secret,
    new_user_code,
    normalize_user_code,
)
from hse_doc_studio.core.jobs.runners import RunnerHostKind

__all__ = [
    "DEVICE_CODE_PREFIX",
    "PAIRING_INTERVAL_S",
    "PAIRING_KEEP",
    "PAIRING_TTL",
    "USER_CODE_ALPHABET",
    "USER_CODE_HALF",
    "IRunnerPairingRepository",
    "PairingStatus",
    "RunnerPairing",
    "new_device_code",
    "new_user_code",
    "normalize_user_code",
]

DEVICE_CODE_PREFIX = "hsdc_"
PAIRING_TTL = timedelta(minutes=10)
PAIRING_INTERVAL_S = 3
# Записи старше суток убирает периодический проход.
PAIRING_KEEP = timedelta(days=1)


class PairingStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    denied = "denied"
    # Устройство получило токен: дальше опрос даёт expired.
    delivered = "delivered"
    expired = "expired"


@dataclass(frozen=True)
class RunnerPairing:
    id: str
    device_code_hash: str
    user_code: str
    name: str
    host_kind: RunnerHostKind
    client_ip: str | None
    status: PairingStatus
    created_at: datetime
    expires_at: datetime
    user_id: str | None = None
    token_id: str | None = None
    token_secret_enc: str | None = None
    decided_at: datetime | None = None

    def expired_at(self, now: datetime) -> bool:
        return self.expires_at <= now


def new_device_code() -> str:
    return new_device_secret(DEVICE_CODE_PREFIX)


class IRunnerPairingRepository(Protocol):
    async def add(self, pairing: RunnerPairing) -> None: ...
    async def get_by_user_code(self, user_code: str) -> RunnerPairing | None: ...
    async def get_by_device_hash(self, device_code_hash: str) -> RunnerPairing | None: ...
    async def decide(
        self,
        pairing_id: str,
        status: PairingStatus,
        *,
        user_id: str,
        now: datetime,
        token_id: str | None = None,
        token_secret_enc: str | None = None,
    ) -> bool:
        """Переводит pending в approved или denied; False, если запись уже не pending."""
        ...

    async def deliver(self, pairing_id: str) -> bool:
        """approved -> delivered со стиранием шифртекста; False, если выдача уже была."""
        ...

    async def purge(self, older_than: datetime) -> int: ...
