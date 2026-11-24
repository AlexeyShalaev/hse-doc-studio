"""Обновление всех раннеров установки разом: что устарело, как каждый обновляется и ход общего запуска.

Устарел раннер установки (не личный), чья версия ниже версии самой Студии (`is_outdated`). Как его обновить, решает
то, чем он поставлен: из админки (Docker рядом, Deployment в кластере), по SSH с сохранённым доступом, всё прочее
(чарт Helm, `docker run`, служба на хосте) Студия безопасно обновить не может, такой раннер идёт в списке как
«обновить вручную» с подсказкой.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

# Сколько общих запусков помнит память процесса (как у `InstallJobStore`).
MAX_BATCHES = 10


class FleetKind(StrEnum):
    """Чем обновляется раннер: `manual` значит, что Студия его сама не обновит."""

    docker = "docker"
    kubernetes = "kubernetes"
    ssh = "ssh"
    manual = "manual"


class ManualReason(StrEnum):
    """Почему раннер нельзя обновить отсюда; по причине интерфейс даёт подсказку, что сделать руками."""

    helm = "helm"
    container = "container"
    host = "host"
    unknown = "unknown"


class FleetItemState(StrEnum):
    pending = "pending"
    # Раннер занят сборкой: его обновят, когда он освободится.
    waiting = "waiting"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    skipped = "skipped"


class FleetBatchState(StrEnum):
    running = "running"
    finished = "finished"


@dataclass(frozen=True, slots=True)
class FleetCandidate:
    """Устаревший раннер установки и способ его обновить."""

    runner_id: str
    name: str
    kind: FleetKind
    version: str
    target_version: str
    status: str
    running_jobs: int
    manual_reason: ManualReason | None = None
    # Адрес установки для хоста: имя Deployment или контейнера, либо id сохранённого доступа SSH. В ответах не уходит.
    ref: str = ""

    @property
    def upgradable(self) -> bool:
        return self.kind is not FleetKind.manual


@dataclass(slots=True)
class FleetItem:
    """Строка общего запуска: раннер, его состояние и причина, если он не обновлён."""

    runner_id: str
    name: str
    kind: FleetKind
    from_version: str
    ref: str
    state: FleetItemState = FleetItemState.pending
    # Код причины для `failed` и `skipped`: busy, cancelled, install_busy, reconnect_timeout и коды установки.
    code: str | None = None
    detail: str = ""
    # Версия раннера после обновления (по его сигналу), пока не известна пусто.
    to_version: str = ""
    job_id: str | None = None
    # Неудачное обновление: вернули ли прежнюю версию (None, если откатывать было нечего или откат не предусмотрен).
    rolled_back: bool | None = None


@dataclass(slots=True)
class FleetBatch:
    id: str
    created_by: str
    created_at: datetime
    target_version: str
    items: list[FleetItem]
    state: FleetBatchState = FleetBatchState.running
    finished_at: datetime | None = None
    cancel_requested: bool = False

    def count(self, state: FleetItemState) -> int:
        return sum(1 for item in self.items if item.state is state)


@dataclass(frozen=True, slots=True)
class FleetPlan:
    """Что видит админ: устаревшие раннеры, нужно ли предложение и идущий (или последний) запуск."""

    server_version: str
    items: tuple[FleetCandidate, ...]
    # Версия Студии, для которой предложение отклонено; пусто, если не отклонялось.
    dismissed_version: str | None = None
    batch: FleetBatch | None = field(default=None)

    @property
    def upgradable(self) -> tuple[FleetCandidate, ...]:
        return tuple(i for i in self.items if i.upgradable)

    @property
    def offer(self) -> bool:
        """Есть что обновлять и предложение не отклонено для этой версии; идущий запуск виден всегда."""
        if self.batch is not None and self.batch.state is FleetBatchState.running:
            return True
        return bool(self.upgradable) and self.dismissed_version != self.server_version
