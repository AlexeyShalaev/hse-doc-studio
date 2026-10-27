"""Папки проектов с подключённым удалённым репозиторием (порт IGitRemoteRegistry).

Список нужен фоновой выборке: без подключённых репозиториев она не запускает ни git, ни сеть. Известные папки
просматриваются один раз при первом обращении (в config хранилища ищется секция remote), дальше список ведут
подключение, отключение, перенос и удаление проекта. Просмотр читает текстовый файл и git не запускает.
"""

from __future__ import annotations

import re
import threading
from collections.abc import Callable
from pathlib import Path

import structlog

from hse_doc_studio.core.repositories import IProjectIndexRepository
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
    def __init__(self, project_index: IProjectIndexRepository) -> None:
        self._index = project_index
        self._folders: dict[Path, Path] = {}
        self._scanned = False
        self._lock = threading.RLock()
        self._listeners: list[Callable[[], None]] = []

    def subscribe(self, listener: Callable[[], None]) -> None:
        with self._lock:
            self._listeners.append(listener)

    def add(self, folder: Path) -> None:
        with self._lock:
            self._scan()
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
            self._scan()
            self._folders.pop(folder.resolve(), None)

    def list(self) -> list[Path]:
        with self._lock:
            self._scan()
            return sorted(self._folders.values())

    def _scan(self) -> None:
        if self._scanned:
            return
        self._scanned = True
        try:
            known = self._index.list_known()
        except Exception as exc:  # noqa: BLE001 — битый индекс не должен ронять подключение проекта
            logger.warning("git remotes: project index is unreadable", exc=str(exc))
            return
        for folder in known:
            if store_has_remote(folder):
                self._folders.setdefault(folder.resolve(), folder)
