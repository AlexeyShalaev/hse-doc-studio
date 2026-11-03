"""Устройство локальной Студии: `data_dir/device.json` (идентификатор и имя, заданное человеком). Секретов нет."""

from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
from collections.abc import Callable
from pathlib import Path

import structlog

from hse_doc_studio.core.devices.entities import DEVICE_ID_RE, sanitize_name
from hse_doc_studio.core.devices.local import GENERIC_DEVICE_NAME, LocalDevice

logger = structlog.get_logger(__name__)

FILE = "device.json"
# Имя хоста внутри контейнера это идентификатор контейнера: человеку оно ничего не говорит.
_CONTAINER_ID = re.compile(r"[0-9a-f]{12}([0-9a-f]{52})?")


def default_device_name(configured: str | None, hostname: Callable[[], str]) -> str:
    """Имя из настройки, иначе имя машины без `.local`, иначе общее имя (если имя хоста выглядит как id контейнера)."""
    for candidate in (configured, hostname()):
        name = sanitize_name(candidate or "")
        name = re.sub(r"\.(local|lan|home|localdomain)$", "", name, flags=re.IGNORECASE)
        if name and not _CONTAINER_ID.fullmatch(name.lower()):
            return name
    return GENERIC_DEVICE_NAME


class JsonDeviceIdentity:
    def __init__(self, data_dir: Path, *, configured_name: str | None, hostname: Callable[[], str]) -> None:
        self._path = data_dir / FILE
        self._configured = configured_name
        self._hostname = hostname
        self._lock = asyncio.Lock()

    async def get(self) -> LocalDevice:
        async with self._lock:
            return await asyncio.to_thread(self._load)

    async def set_name(self, name: str | None) -> LocalDevice:
        async with self._lock:
            return await asyncio.to_thread(self._set, name)

    def _read(self) -> tuple[str | None, str | None]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None, None
        except (OSError, ValueError):
            logger.warning("device.json unreadable, a new identity will be created")
            return None, None
        if not isinstance(data, dict):
            return None, None
        device_id = data.get("device_id")
        name = data.get("name")
        return (
            device_id if isinstance(device_id, str) and DEVICE_ID_RE.fullmatch(device_id) else None,
            name if isinstance(name, str) and name else None,
        )

    def _load(self) -> LocalDevice:
        device_id, name = self._read()
        if device_id is None:
            device_id = secrets.token_hex(16)
            self._write(device_id, name)
        return self._view(device_id, name)

    def _set(self, name: str | None) -> LocalDevice:
        device_id, _ = self._read()
        device_id = device_id or secrets.token_hex(16)
        clean = sanitize_name(name or "") or None
        self._write(device_id, clean)
        return self._view(device_id, clean)

    def _view(self, device_id: str, custom: str | None) -> LocalDevice:
        default = default_device_name(self._configured, self._hostname)
        return LocalDevice(device_id=device_id, name=custom or default, default_name=default, custom=custom is not None)

    def _write(self, device_id: str, name: str | None) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".json.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"device_id": device_id, "name": name}, handle, ensure_ascii=False)
        tmp.replace(self._path)
