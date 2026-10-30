"""Сопряжение раннера по коду устройства (device code): локальная Студия получает личный токен регистрации.

Устройство знает секретный `device_code` (в БД только хеш), человек на сайте вводит короткий `user_code`.
Подтверждение создаёт личный токен регистрации, секрет которого лежит шифртекстом в записи до выдачи
устройству; выдаётся он ровно один раз, после чего стирается.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol

from hse_doc_studio.core.jobs.runners import RunnerHostKind

DEVICE_CODE_PREFIX = "hsdc_"
USER_CODE_ALPHABET = "BCDFGHJKLMNPQRSTVWXZ23456789"
USER_CODE_HALF = 4
PAIRING_TTL = timedelta(minutes=10)
PAIRING_INTERVAL_S = 3
# Записи старше суток убирает периодический проход.
PAIRING_KEEP = timedelta(days=1)
_USER_CODE_RE = re.compile(rf"^[{USER_CODE_ALPHABET}]{{{USER_CODE_HALF * 2}}}$")


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
    return DEVICE_CODE_PREFIX + secrets.token_urlsafe(32)


def new_user_code() -> str:
    raw = "".join(secrets.choice(USER_CODE_ALPHABET) for _ in range(USER_CODE_HALF * 2))
    return f"{raw[:USER_CODE_HALF]}-{raw[USER_CODE_HALF:]}"


def normalize_user_code(value: str) -> str | None:
    """Ввод без учёта регистра, пробелов и дефиса; негодный код даёт None."""
    raw = re.sub(r"[\s-]", "", value).upper()
    if not _USER_CODE_RE.match(raw):
        return None
    return f"{raw[:USER_CODE_HALF]}-{raw[USER_CODE_HALF:]}"


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
