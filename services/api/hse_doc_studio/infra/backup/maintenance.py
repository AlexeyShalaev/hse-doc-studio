"""Режим обслуживания api: на время восстановления из админки приложение не трогает базу и диск."""

from __future__ import annotations

import asyncio
import json
import os
import signal
from collections.abc import Mapping
from pathlib import Path

import structlog
from sqlalchemy.ext.asyncio import AsyncEngine

from hse_doc_studio.core.background import BackgroundTaskRunner

logger = structlog.get_logger()

MARKER_NAME = "restore-in-progress.json"
DRAIN_S = 2.0


def marker_path(data_dir: Path) -> Path:
    # tmp/ не входит в бэкап и не переименовывается при восстановлении.
    return data_dir / "tmp" / MARKER_NAME


class MaintenanceController:
    def __init__(self, engine: AsyncEngine, marker: Path, *, restart: bool = True, drain_s: float = DRAIN_S) -> None:
        self._engine = engine
        self._marker = marker
        self._restart = restart
        self._drain_s = drain_s
        self._background: BackgroundTaskRunner | None = None
        self._active = False
        self._status: dict[str, object] = {}

    def bind(self, background: BackgroundTaskRunner) -> None:
        self._background = background

    @property
    def active(self) -> bool:
        return self._active

    @property
    def writing(self) -> bool:
        """Идёт запись: ручки админки закрыты, потому что им нужна база."""
        return self._active and self._status.get("phase") == "applying"

    def status(self) -> dict[str, object]:
        return {"active": self._active, **self._status}

    def publish(self, status: Mapping[str, object]) -> None:
        self._status = dict(status)

    async def enter(self, *, reason: str) -> None:
        self._marker.parent.mkdir(parents=True, exist_ok=True)
        self._marker.write_text(json.dumps({"reason": reason}), encoding="utf-8")
        self._active = True
        logger.warning("maintenance mode on", reason=reason)
        await asyncio.sleep(self._drain_s)  # начатые запросы успевают закончить
        if self._background is not None:
            await self._background.stop()
        await self._engine.dispose()

    async def leave(self) -> None:
        self._active = False
        self._marker.unlink(missing_ok=True)
        if self._background is not None and not self._background.running:
            self._background.start()
        logger.warning("maintenance mode off")

    async def adopt_marker(self) -> bool:
        """Прошлый процесс умер посреди записи: остаёмся в режиме обслуживания, пока оператор не доведёт дело."""
        if not self._marker.exists():
            return False
        self._active = True
        self._status = {"phase": "failed", "error_code": "backup_restore_interrupted", "wrote": True}
        if self._background is not None:
            await self._background.stop()
        logger.error("a restore did not finish: maintenance mode stays on", marker=str(self._marker))
        return True

    def request_restart(self, *, delay_s: float) -> bool:
        if not self._restart:
            return False
        self._marker.unlink(missing_ok=True)
        asyncio.get_running_loop().call_later(delay_s, os.kill, os.getpid(), signal.SIGTERM)
        return True
