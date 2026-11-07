from __future__ import annotations

import platform
import shutil
from contextlib import suppress
from pathlib import Path

from hse_doc_studio.core.model_servers import HostResources

_MB = 1024 * 1024


class LocalHostResources:
    """Архитектура и свободное место там, где лежат тома докера (для контейнера Студии это приближение)."""

    def __init__(self, path: Path) -> None:
        self._path = path

    async def read(self) -> HostResources:
        free: int | None = None
        with suppress(OSError):
            free = int(shutil.disk_usage(self._path if self._path.exists() else Path("/")).free // _MB)
        return HostResources(platform.machine() or None, free)
