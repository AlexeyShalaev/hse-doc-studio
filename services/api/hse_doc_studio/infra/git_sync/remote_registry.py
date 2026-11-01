"""Папки проектов с подключённым удалённым репозиторием (порт IGitRemoteRegistry).

Список нужен фоновой выборке: без подключённых репозиториев она не запускает ни git, ни сеть. Известные папки
(локальный индекс или каталог в БД, как отвечает IProjectLocator) просматриваются один раз при первом
обращении (в config хранилища ищется секция remote), дальше список ведут подключение, отключение, перенос и
удаление проекта. Просмотр читает текстовый файл и git не запускает.
"""

from __future__ import annotations

import asyncio
import re
import threading
from collections.abc import Callable
from pathlib import Path

import structlog

from hse_doc_studio.core.projects.locator import IProjectLocator
from hse_doc_studio.infra.vcs.git_vcs_service import store_git_dir

logger = structlog.get_logger()

_ORIGIN_SECTION = re.compile(r'^\s*\[\s*remote\s+"origin"\s*\]', re.IGNORECASE | re.MULTILINE)
_MAX_CONFIG_BYTES = 1_000_000


def store_has_remote(folder: Path) -> bool:
    """В config хранилища проекта есть адрес origin; сам git не запускается."""
    config = store_git_dir(folder) / "config"
    try:
        if config.stat().st_size > _MAX_CONFIG_BYTES:
            return False
        text = config.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return _ORIGIN_SECTION.search(text) is not None


class ConfigScanRemoteRegistry:
    def __init__(self, locator: IProjectLocator) -> None:
        self._locator = locator
        self._folders: dict[Path, Path] = {}
        # Снятые до первого просмотра: иначе просмотр вернул бы папку, у которой подключение уже убрали.
        self._removed: set[Path] = set()
        self._scanned = False
        self._scan_lock = asyncio.Lock()
        self._lock = threading.RLock()
        self._listeners: list[Callable[[], None]] = []

    def subscribe(self, listener: Callable[[], None]) -> None:
        with self._lock:
            self._listeners.append(listener)

    def add(self, folder: Path) -> None:
        with self._lock:
            self._removed.discard(folder.resolve())
            self._folders[folder.resolve()] = folder
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener()
            except Exception:  # noqa: BLE001 — чужой обработчик не должен срывать подключение проекта
                logger.warning("git remotes: a listener failed", exc_info=True)

    def consider(self, folder: Path) -> None:
        """Папка, открытая из готового проекта: подключение, записанное в её хранилище, надо учесть без перезапуска."""
        if store_has_remote(folder):
            self.add(folder)

    def remove(self, folder: Path) -> None:
        with self._lock:
            key = folder.resolve()
            self._folders.pop(key, None)
            if not self._scanned:
                self._removed.add(key)

    async def list(self) -> list[Path]:
        await self._scan()
        with self._lock:
            return sorted(self._folders.values())

    def _is_scanned(self) -> bool:
        return self._scanned

    async def _scan(self) -> None:
        if self._is_scanned():
            return
        async with self._scan_lock:
            if self._is_scanned():
                return
            try:
                known = await self._locator.list_all()
            except Exception as exc:  # noqa: BLE001 — нечитаемый список проектов не должен ронять опрос
                logger.warning("git remotes: project list is unreadable", exc=str(exc))
                return
            connected = await asyncio.to_thread(lambda: [folder for folder in known if store_has_remote(folder)])
            with self._lock:
                for folder in connected:
                    key = folder.resolve()
                    if key not in self._removed:
                        self._folders.setdefault(key, folder)
                self._removed.clear()
                self._scanned = True
