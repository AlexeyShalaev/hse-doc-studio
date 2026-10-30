"""Учёт места проекта на сервере и предел его размера.

Размер проекта складывается из рабочего дерева, git-стора на томе и объектов проекта в S3. Предел один на
проект (из настроек сервера), предупреждение включается с доли предела. Квоты пользователя и организации
строятся на тех же данных позже. Запись сверх предела отклоняется, а чтение и удаление работают всегда,
чтобы пользователь мог освободить место.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

PROJECT_QUOTA_EXCEEDED = "project_quota_exceeded"


@dataclass(frozen=True)
class ProjectUsage:
    project_id: UUID
    bytes_tree: int
    bytes_git: int
    bytes_s3: int
    measured_at: datetime

    @property
    def total(self) -> int:
        return self.bytes_tree + self.bytes_git + self.bytes_s3


@dataclass(frozen=True)
class QuotaPolicy:
    """Предел проекта в байтах; 0 значит «без предела». Предупреждение с доли warn_ratio от предела."""

    limit_bytes: int
    warn_ratio: float = 0.8

    @property
    def enabled(self) -> bool:
        return self.limit_bytes > 0


@dataclass(frozen=True)
class ProjectStorageStatus:
    used_bytes: int
    limit_bytes: int
    warning: bool
    exceeded: bool
    measured_at: datetime


class ProjectQuotaExceededError(Exception):
    """Запись отклонена: проект превысил бы предел размера. Роутеры отвечают 413 с кодом project_quota_exceeded."""

    def __init__(self, project_id: UUID, used_bytes: int, limit_bytes: int, needed_bytes: int) -> None:
        super().__init__(f"project {project_id} over quota: used {used_bytes} + {needed_bytes} > {limit_bytes}")
        self.project_id = project_id
        self.used_bytes = used_bytes
        self.limit_bytes = limit_bytes
        self.needed_bytes = needed_bytes


class IProjectUsageStore(Protocol):
    async def get(self, project_id: UUID) -> ProjectUsage | None: ...

    async def save(self, usage: ProjectUsage) -> None:
        """Записывает результат полного измерения; строки нет, значит создаётся."""
        ...

    async def add_tree(self, project_id: UUID, delta_bytes: int, now: datetime) -> None:
        """Сдвигает размер дерева на delta (не ниже нуля); строки нет, значит создаётся."""
        ...

    async def stale(self, older_than: datetime, limit: int) -> list[UUID]:
        """Живые проекты без измерения или с измерением старше older_than, самые давние первыми."""
        ...


class IProjectUsageMeasurer(Protocol):
    async def measure(self, project_id: UUID) -> ProjectUsage:
        """Полный обход дерева, git-стора и префикса S3 проекта; в хранилище не пишет."""
        ...


class IProjectQuota(Protocol):
    @property
    def enabled(self) -> bool: ...

    async def check_write(self, project_id: UUID, delta_bytes: int) -> None:
        """Пропускает запись, которая меняет размер на delta; сверх предела ProjectQuotaExceededError.
        Запись, не увеличивающая размер, проходит всегда."""
        ...

    async def record_change(self, project_id: UUID, delta_bytes: int) -> None:
        """Учитывает уже выполненную запись."""
        ...

    async def status(self, project_id: UUID) -> ProjectStorageStatus | None:
        """Занятое место и предупреждение; None, если предел не ведётся (локальный режим)."""
        ...


class NoopProjectQuota:
    """Локальный режим: места не считаем и ничего не отклоняем."""

    @property
    def enabled(self) -> bool:
        return False

    async def check_write(self, project_id: UUID, delta_bytes: int) -> None:
        return None

    async def record_change(self, project_id: UUID, delta_bytes: int) -> None:
        return None

    async def status(self, project_id: UUID) -> ProjectStorageStatus | None:
        return None
