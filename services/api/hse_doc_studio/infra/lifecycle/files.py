"""Источник на диске: состояние совместной правки (`<data>/collab/<проект>/*.ystate`)."""

from __future__ import annotations

import asyncio
import contextlib
import os
import time
from datetime import datetime
from pathlib import Path

from hse_doc_studio.core.lifecycle.ports import ExpiredCount, PurgeContext, PurgeResult, SourceSize

_SUFFIX = ".ystate"


def _scan(root: Path) -> tuple[int, int]:
    total = files = 0
    with contextlib.suppress(OSError):
        for entry in os.scandir(root):
            if not entry.is_dir(follow_symlinks=False):
                continue
            with contextlib.suppress(OSError):
                for item in os.scandir(entry.path):
                    if item.is_file(follow_symlinks=False):
                        total += item.stat(follow_symlinks=False).st_size
                        files += 1
    return total, files


def _count_stale(root: Path, cutoff_ts: float, limit: int) -> int:
    """Файлы состояния, не тронутые с `cutoff_ts`, с потолком `limit`: то же правило, что у `_sweep`."""
    found = 0
    with contextlib.suppress(OSError):
        for folder in os.scandir(root):
            if not folder.is_dir(follow_symlinks=False):
                continue
            with contextlib.suppress(OSError):
                for item in os.scandir(folder.path):
                    stale = item.name.endswith(_SUFFIX) and item.is_file(follow_symlinks=False)
                    if stale and item.stat(follow_symlinks=False).st_mtime < cutoff_ts:
                        found += 1
                        if found >= limit:
                            return found
    return found


def _sweep(root: Path, cutoff_ts: float, deadline: float) -> tuple[int, bool]:
    """Удаляет файлы состояния, не тронутые с `cutoff_ts`, и опустевшие каталоги. Возвращает (удалено, не успели)."""
    removed = 0
    with contextlib.suppress(OSError):
        for folder in os.scandir(root):
            if not folder.is_dir(follow_symlinks=False):
                continue
            if time.monotonic() >= deadline:
                return removed, True
            with contextlib.suppress(OSError):
                for item in os.scandir(folder.path):
                    stale = item.name.endswith(_SUFFIX) and item.is_file(follow_symlinks=False)
                    if stale and item.stat(follow_symlinks=False).st_mtime < cutoff_ts:
                        os.unlink(item.path)
                        removed += 1
            with contextlib.suppress(OSError):
                os.rmdir(folder.path)  # только пустой: непустой каталог rmdir не тронет
    return removed, False


class CollabStateSource:
    """Состояние Yjs вторично (потерянное комната соберёт из файла проекта): без правок дольше срока его стирают."""

    key = "collab_state"

    def __init__(self, root: Path) -> None:
        self._root = root

    async def measure(self) -> SourceSize:
        size, _files = await asyncio.to_thread(_scan, self._root)
        return SourceSize(bytes=size)

    async def count_expired(self, now: datetime, cutoff: datetime | None, cap: int) -> ExpiredCount:
        if cutoff is None:
            return ExpiredCount(0)
        return ExpiredCount(await asyncio.to_thread(_count_stale, self._root, cutoff.timestamp(), cap + 1), cutoff)

    async def purge(self, ctx: PurgeContext) -> PurgeResult:
        if ctx.cutoff is None:
            return PurgeResult()
        removed, more = await asyncio.to_thread(_sweep, self._root, ctx.cutoff.timestamp(), ctx.deadline)
        return PurgeResult(removed=removed, more=more)
