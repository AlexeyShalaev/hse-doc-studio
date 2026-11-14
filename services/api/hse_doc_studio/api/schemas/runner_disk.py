"""«Диск» раннера в админке и в «Моих раннерах» (`docs/design/storage-cleanup.md`, 9.1).

Формы совпадают с эталонами `contracts/server/fixtures/RunnerDisk*`. Отчёт раннера и ход команды берутся из моделей
протокола раннера (`api/schemas/runner.py`): это те же данные, которые раннер прислал и сервер проверил схемой.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from hse_doc_studio.api.schemas.common import StrictModel
from hse_doc_studio.api.schemas.runner import (
    CommandProgressBody,
    DiskTargetName,
    RunnerCommandKindName,
    RunnerDiskReportBody,
)

RunnerCommandStateName = Literal[
    "queued", "delivered", "running", "cancelling", "done", "cancelled", "error", "expired", "lost"
]


class RunnerDiskPerson(StrictModel):
    id: str
    name: str


class RunnerDiskBrief(StrictModel):
    """Поле `disk` строки списка раннеров (`RunnerInfo`, `MyRunner`); `null` у отозванного раннера."""

    supported: bool
    # Пусто, пока раннер не прислал замер.
    cleanable_bytes: int | None
    measured_at: datetime | None


class RunnerDiskCommand(StrictModel):
    """Команда раннеру; у `disk.measure` целей нет и откат `false`. `auto`: автоочистка по порогу места."""

    id: str
    kind: RunnerCommandKindName
    state: RunnerCommandStateName
    targets: list[DiskTargetName]
    include_rollback: bool
    created_at: datetime
    finished_at: datetime | None
    # Кто запустил; `null`, если человека уже нет в установке или это автоочистка.
    created_by: RunnerDiskPerson | None
    progress: CommandProgressBody | None
    auto: bool


class RunnerDiskAutoLast(StrictModel):
    """Последняя автоочистка: начало, итог (`finished_at` пусто, пока идёт) и место на момент проверки."""

    command_id: str
    state: RunnerCommandStateName
    started_at: datetime
    finished_at: datetime | None
    freed_bytes: int = Field(ge=0)
    free_bytes: int = Field(ge=0)
    total_bytes: int = Field(ge=0)


class RunnerDiskAuto(StrictModel):
    """Автоочистка общего раннера по порогу места (storage-cleanup.md, 14.5)."""

    supported: bool
    # Почему не поддержана: старая версия, Kubernetes, локальная Студия или выключено на самом раннере.
    reason: Literal["outdated", "kubernetes", "managed_locally", "runner_disabled"] | None
    min_version: str
    enabled: bool
    min_free_percent: int = Field(ge=1, le=50)
    interval_min: int
    last: RunnerDiskAutoLast | None


class RunnerDiskAutoRequest(StrictModel):
    """Настройка автоочистки; процент вне 1..50 сервер отвергает как `input_invalid`."""

    enabled: bool
    min_free_percent: int


class RunnerDiskView(StrictModel):
    runner_id: str
    supported: bool
    # Почему диска нет: раннер старой версии. Отозванный раннер даёт 404.
    reason: Literal["outdated"] | None
    min_version: str
    online: bool
    last_seen_at: datetime | None
    report: RunnerDiskReportBody | None
    received_at: datetime | None
    stale: bool
    # Незавершённая очистка или последняя завершённая за 24 часа.
    command: RunnerDiskCommand | None
    measuring: bool
    can_clean: bool
    can_include_rollback: bool
    # Только в админке и только у личного раннера.
    personal_owner: RunnerDiskPerson | None
    # Только в админке и только у общего раннера.
    auto: RunnerDiskAuto | None


class RunnerDiskCleanupRequest(StrictModel):
    """Цели очистки: пустой список, повторы и откат без старых версий сервер отвергает как `input_invalid`."""

    targets: list[DiskTargetName] = Field(max_length=6)
    include_rollback: bool


class RunnerDiskSummaryRunner(StrictModel):
    runner_id: str
    name: str
    cleanable_bytes: int
    measured_at: datetime


class RunnerDiskSummary(StrictModel):
    reporting: int
    outdated: int
    min_version: str
    cleanable_bytes: int
    top: list[RunnerDiskSummaryRunner] = Field(max_length=3)
