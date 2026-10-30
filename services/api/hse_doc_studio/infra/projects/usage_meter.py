"""Измерение места проекта, проверка предела при записи и фоновое переизмерение.

Полный обход дерева дорогой, поэтому он выполняется редко: по расписанию пачкой самых давних проектов,
при первой записи в проект без измерения и при отказе по пределу (место могли освободить). Обычная запись
только сдвигает счётчик дерева на размер изменения.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import structlog

from hse_doc_studio.core.projects.usage import (
    IProjectUsageMeasurer,
    IProjectUsageStore,
    ProjectQuotaExceededError,
    ProjectStorageStatus,
    ProjectUsage,
    QuotaPolicy,
)
from hse_doc_studio.core.projects.volume import IProjectVolume
from hse_doc_studio.core.storage import IObjectStore
from hse_doc_studio.infra.vcs.git_vcs_service import store_git_dir

logger = structlog.get_logger()


def project_objects_prefix(project_id: UUID | str) -> str:
    return f"artifacts/{project_id}/"


def _file_size(entry: os.DirEntry[str]) -> int:
    try:
        return entry.stat(follow_symlinks=False).st_size if entry.is_file(follow_symlinks=False) else 0
    except OSError:
        return 0  # файл исчез между перечислением и stat


def _dir_size(root: Path) -> int:
    """Сумма размеров обычных файлов под root без перехода по симлинкам."""
    total = 0
    stack = [root]
    while stack:
        try:
            with os.scandir(stack.pop()) as it:
                for entry in it:
                    if entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(Path(entry.path))
                    else:
                        total += _file_size(entry)
        except OSError:
            continue
    return total


def _measure_folder(folder: Path) -> tuple[int, int]:
    git = _dir_size(store_git_dir(folder))
    return _dir_size(folder) - git, git


class VolumeUsageMeasurer:
    def __init__(
        self, volume: IProjectVolume, store: IObjectStore, clock: Callable[[], datetime] | None = None
    ) -> None:
        self._volume = volume
        self._store = store
        self._clock = clock or (lambda: datetime.now(tz=timezone.utc))

    async def measure(self, project_id: UUID) -> ProjectUsage:
        folder = self._volume.path_of(project_id)
        tree, git = await asyncio.to_thread(_measure_folder, folder)
        objects = await self._store.list_objects(project_objects_prefix(project_id))
        return ProjectUsage(project_id, tree, git, sum(obj.size for obj in objects), self._clock())


class ProjectQuotaService:
    def __init__(
        self,
        store: IProjectUsageStore,
        measurer: IProjectUsageMeasurer,
        policy: QuotaPolicy,
        *,
        remeasure_min_s: float = 2.0,
        clock: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._store = store
        self._measurer = measurer
        self._policy = policy
        self._remeasure_min_s = remeasure_min_s
        self._clock = clock or (lambda: datetime.now(tz=timezone.utc))
        self._monotonic = monotonic
        self._last_remeasure: dict[UUID, float] = {}

    @property
    def enabled(self) -> bool:
        return self._policy.enabled

    async def check_write(self, project_id: UUID, delta_bytes: int) -> None:
        if not self._policy.enabled or delta_bytes <= 0:
            return
        usage = await self._usage(project_id)
        if usage.total + delta_bytes <= self._policy.limit_bytes:
            return
        # Место могли освободить удалением: перед отказом сверяемся с диском, но не чаще, чем раз в пару секунд.
        if self._may_remeasure(project_id):
            usage = await self._remeasure(project_id)
            if usage.total + delta_bytes <= self._policy.limit_bytes:
                return
        raise ProjectQuotaExceededError(project_id, usage.total, self._policy.limit_bytes, delta_bytes)

    async def record_change(self, project_id: UUID, delta_bytes: int) -> None:
        if not self._policy.enabled or delta_bytes == 0:
            return
        if await self._store.get(project_id) is None:
            await self._remeasure(project_id)
            return
        await self._store.add_tree(project_id, delta_bytes, self._clock())

    async def status(self, project_id: UUID) -> ProjectStorageStatus | None:
        if not self._policy.enabled:
            return None
        usage = await self._usage(project_id)
        limit = self._policy.limit_bytes
        return ProjectStorageStatus(
            used_bytes=usage.total,
            limit_bytes=limit,
            warning=usage.total >= limit * self._policy.warn_ratio,
            exceeded=usage.total >= limit,
            measured_at=usage.measured_at,
        )

    async def _usage(self, project_id: UUID) -> ProjectUsage:
        usage = await self._store.get(project_id)
        return usage if usage is not None else await self._remeasure(project_id)

    def _may_remeasure(self, project_id: UUID) -> bool:
        last = self._last_remeasure.get(project_id)
        return last is None or self._monotonic() - last >= self._remeasure_min_s

    async def _remeasure(self, project_id: UUID) -> ProjectUsage:
        self._last_remeasure[project_id] = self._monotonic()
        usage = await self._measurer.measure(project_id)
        await self._store.save(usage)
        return usage


class ProjectUsageSweeper:
    """Фоновое измерение: за прогон берёт пачку самых давних проектов и делает паузу между ними."""

    def __init__(
        self,
        store: IProjectUsageStore,
        measurer: IProjectUsageMeasurer,
        *,
        max_age: timedelta,
        batch_size: int,
        pause_s: float = 0.2,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._measurer = measurer
        self._max_age = max_age
        self._batch_size = batch_size
        self._pause_s = pause_s
        self._clock = clock or (lambda: datetime.now(tz=timezone.utc))

    async def run(self) -> int:
        ids = await self._store.stale(self._clock() - self._max_age, self._batch_size)
        done = 0
        for project_id in ids:
            try:
                await self._store.save(await self._measurer.measure(project_id))
                done += 1
            except Exception as exc:  # noqa: BLE001 — папки может не быть; остальные проекты измеряем дальше
                logger.warning("project usage: measure failed", project_id=str(project_id), exc=str(exc))
            if self._pause_s:
                await asyncio.sleep(self._pause_s)
        return done
