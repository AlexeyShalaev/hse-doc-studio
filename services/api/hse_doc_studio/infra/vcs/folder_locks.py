from __future__ import annotations

import asyncio
from pathlib import Path


class VcsFolderLocks:
    """Per-project-folder async locks serializing VCS write operations.

    All git index-mutating operations (commit / snapshot / restore, and the
    compile-success auto-commit) acquire the lock for their project folder, so
    concurrent writes can't corrupt the index. Read-only operations don't lock.
    App-scoped so the lock map is shared across requests and the compile task.
    """

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}

    def for_folder(self, folder: Path) -> asyncio.Lock:
        try:
            key = str(folder.resolve())
        except OSError:
            key = str(folder)
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock
