"""Порты подключённых устройств."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from hse_doc_studio.core.devices.entities import ConnectedDevice, DeviceReport


class IDeviceRepository(Protocol):
    async def upsert(self, device: ConnectedDevice) -> None:
        """Заводит устройство или обновляет последний сигнал; `first_seen_at` существующей записи не меняется."""
        ...

    async def list_for_user(self, user_id: str) -> list[ConnectedDevice]:
        """Устройства человека, свежие первыми."""
        ...

    async def get(self, user_id: str, device_id: str) -> ConnectedDevice | None: ...

    async def list_for_project(self, project_id: UUID) -> list[ConnectedDevice]:
        """Устройства любых людей, сообщивших этот проект. Права на показ проверяет вызывающий."""
        ...

    async def delete(self, user_id: str, device_id: str) -> bool: ...

    async def purge_older_than(self, horizon: datetime) -> int: ...


class IPresenceRegistry(Protocol):
    """Свежее время сигнала в памяти процесса (реализация в `infra.devices`)."""

    def observe(self, user_id: str, report: DeviceReport, now: datetime, persist_interval_s: int) -> bool:
        """Запоминает сигнал; True, если его нужно записать в БД сейчас."""
        ...

    def last_seen(self, user_id: str, device_id: str) -> datetime | None: ...

    def forget(self, user_id: str, device_id: str) -> None: ...

    def prune(self, horizon: datetime) -> None: ...
