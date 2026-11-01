"""Замок папки проекта, который сначала сбрасывает на диск несохранённый текст открытых комнат.

Подменяет `IVcsFolderLocks` на сервере: синхронизация, снимок, восстановление, приём push и сборка берут этот
замок, и перед ними комната записывает всё, что набрали участники. Так операция над папкой видит свежий текст,
а не тот, что был 800 мс назад.
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from pathlib import Path
from types import TracebackType

from hse_doc_studio.core.collab.ports import IFolderFlush
from hse_doc_studio.core.vcs.protocols import IVcsFolderLocks


class FlushHub:
    """Мост между замком и менеджером комнат: замок создаётся раньше менеджера, менеджер подключается позже."""

    def __init__(self) -> None:
        self._target: IFolderFlush | None = None

    def attach(self, target: IFolderFlush) -> None:
        self._target = target

    async def flush_folder(self, folder: Path) -> None:
        if self._target is not None:
            await self._target.flush_folder(folder)


class _FlushingLock:
    def __init__(self, inner: AbstractAsyncContextManager[None], hub: FlushHub, folder: Path) -> None:
        self._inner = inner
        self._hub = hub
        self._folder = folder

    async def __aenter__(self) -> None:
        await self._hub.flush_folder(self._folder)
        await self._inner.__aenter__()

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> bool | None:
        return await self._inner.__aexit__(exc_type, exc, tb)


class CollabAwareFolderLocks:
    def __init__(self, inner: IVcsFolderLocks, hub: FlushHub) -> None:
        self._inner = inner
        self._hub = hub

    def for_folder(self, folder: Path) -> AbstractAsyncContextManager[None]:
        return _FlushingLock(self._inner.for_folder(folder), self._hub, folder)
