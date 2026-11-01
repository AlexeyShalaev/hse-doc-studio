"""Замер места: тома, на которых живут данные api, и размер базы Postgres."""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import text

from hse_doc_studio.core.lifecycle.ports import VolumeUsage
from hse_doc_studio.infra.db.session import SessionProvider


def _existing(path: Path) -> Path:
    probe = path
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    return probe


def _measure(named: Sequence[tuple[str, Path]]) -> list[VolumeUsage]:
    """Один том под несколькими путями считается один раз: имена склеиваются через `+`."""
    by_device: dict[int, tuple[list[str], Path]] = {}
    for name, path in named:
        real = _existing(path)
        with contextlib.suppress(OSError):
            device = os.stat(real).st_dev
            names, first = by_device.setdefault(device, ([], real))
            if name not in names:
                names.append(name)
            by_device[device] = (names, first)
    volumes: list[VolumeUsage] = []
    for names, path in by_device.values():
        with contextlib.suppress(OSError):
            usage = shutil.disk_usage(path)
            volumes.append(VolumeUsage("+".join(names), usage.used, usage.total, usage.free))
    return volumes


class StorageProbe:
    def __init__(
        self, sessions: SessionProvider, paths: Sequence[tuple[str, Path]], *, db_size_limit_bytes: int = 0
    ) -> None:
        self._sessions = sessions
        self._paths = list(paths)
        self._db_limit = db_size_limit_bytes

    async def volumes(self) -> list[VolumeUsage]:
        found = await asyncio.to_thread(_measure, self._paths)
        size = await self.database_bytes()
        found.append(
            VolumeUsage("database", size, self._db_limit or None, (self._db_limit - size) if self._db_limit else None)
        )
        return found

    async def database_bytes(self) -> int:
        async with self._sessions.use() as db:
            return int((await db.execute(text("SELECT pg_database_size(current_database())"))).scalar_one())
