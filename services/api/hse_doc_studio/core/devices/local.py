"""Устройство локальной Студии: стабильный идентификатор и понятное имя (docs/design/connected-devices.md, раздел 6)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

# Имя по умолчанию, когда машину назвать нечем (в контейнере имя хоста это случайный идентификатор).
GENERIC_DEVICE_NAME = "Local Studio"


@dataclass(frozen=True)
class LocalDevice:
    device_id: str
    # Имя, под которым Студию видит облако: заданное человеком или имя по умолчанию.
    name: str
    default_name: str
    # Человек задал имя сам (иначе это умолчание).
    custom: bool


class IDeviceIdentity(Protocol):
    async def get(self) -> LocalDevice: ...

    async def set_name(self, name: str | None) -> LocalDevice:
        """Пустое имя или None возвращает умолчание."""
        ...
