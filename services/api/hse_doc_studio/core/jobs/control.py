"""Канал команд раннеру на сервере: порты хранения команд и замера диска, ошибки канала.

Команды и последний замер живут в Postgres, а не в памяти api: опрос раннера и запрос админа могут прийти на разные
реплики (`docs/design/storage-cleanup.md`, S4). Переходы команды проверяет `COMMAND_TRANSITIONS` из `disk.py`;
хранилище делает переход условным обновлением, поэтому две реплики не закроют одну команду дважды.
"""

from __future__ import annotations

import builtins
from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from hse_doc_studio.core.jobs.disk import (
    CommandProgress,
    DiskAutoLast,
    DiskAutoPolicy,
    RunnerCommand,
    RunnerCommandKind,
    RunnerCommandState,
    RunnerDiskReport,
)
from hse_doc_studio.core.jobs.enums import RunnerErrorCode

# Сколько команд раннера хранится: завершённые сверх этого числа последних стираются при вставке (S13, `on_write`).
COMMANDS_KEPT_PER_RUNNER = 20
# Опрос команд перепроверяет таблицу с этим шагом: пробуждение мгновенно только в реплике, принявшей команду.
CONTROL_POLL_INTERVAL_S = 2.0
# Фоновая `runner_commands_reaper` (под лидерским замком): просрочка доставки и потеря раннера.
COMMANDS_REAPER_INTERVAL_S = 60.0


@dataclass(frozen=True)
class StoredDiskReport:
    """Последний замер раннера и когда сервер его принял (`runners.disk`, `runners.disk_at`)."""

    report: RunnerDiskReport
    received_at: datetime


@dataclass(frozen=True)
class StoredDiskBrief:
    """Проекция последнего замера для списков и сводки: сколько можно освободить (9.3) и когда мерили.

    Читается без разбора всего отчёта (до 64 КБ на раннер), поэтому годится для списка из сотен раннеров.
    """

    cleanable_bytes: int
    measured_at: datetime
    received_at: datetime


@dataclass(frozen=True)
class StoredDiskAuto:
    """Автоочистка раннера (`runners.disk_auto_*`): настройка, начало последней и её итог."""

    policy: DiskAutoPolicy
    started_at: datetime | None
    last: DiskAutoLast | None


class IRunnerCommandRepository(Protocol):
    async def add(self, command: RunnerCommand, *, keep: int = COMMANDS_KEPT_PER_RUNNER) -> bool:
        """Вставляет команду и стирает завершённые команды раннера сверх `keep` последних.

        False: у раннера уже есть незавершённая `disk.cleanup` (частичный уникальный индекс).
        """
        ...

    async def get(self, command_id: UUID) -> RunnerCommand | None: ...
    async def list_for_runner(self, runner_id: str, *, limit: int) -> builtins.list[RunnerCommand]:
        """Команды раннера, новые первыми."""
        ...

    async def find_open(self, runner_id: str, kind: RunnerCommandKind) -> RunnerCommand | None:
        """Незавершённая команда этого вида у раннера, самая новая."""
        ...

    async def claim(
        self, runner_id: str, kinds: Collection[RunnerCommandKind], *, now: datetime, not_before: datetime
    ) -> RunnerCommand | None:
        """Самая старая `queued` команда раннера из `kinds`, поставленная не раньше `not_before`, становится
        `delivered`; две реплики одну команду не выдают."""
        ...

    async def transition(
        self,
        command_id: UUID,
        *,
        expected: RunnerCommandState,
        to: RunnerCommandState,
        now: datetime,
        progress: CommandProgress | None = None,
    ) -> RunnerCommand | None:
        """Переход из `expected` в `to`, если команда всё ещё в `expected`; иначе None (её успели сдвинуть).

        `progress=None` оставляет прежний ход. `delivered_at` ставится при `to=delivered`, `finished_at` при итоге.
        """
        ...

    async def expire_queued(
        self, *, before: datetime, now: datetime, runner_id: str | None = None
    ) -> builtins.list[RunnerCommand]:
        """`queued`, поставленные раньше `before`, становятся `expired`; возвращает закрытые."""
        ...

    async def lose(
        self, *, silent_before: datetime, now: datetime, runner_id: str | None = None
    ) -> builtins.list[RunnerCommand]:
        """Доставленные и идущие команды становятся `lost`, если хода не было с `silent_before`, раннер отозван или
        прислал `/offline` после последнего хода; возвращает закрытые."""
        ...


class IRunnerDiskStore(Protocol):
    async def set_disk(self, runner_id: str, report: RunnerDiskReport, now: datetime) -> bool:
        """Запоминает замер на месте прежнего; False, если раннера нет или он отозван."""
        ...

    async def get_disk(self, runner_id: str) -> StoredDiskReport | None: ...
    async def list_disks(self) -> dict[str, StoredDiskReport]:
        """Последние замеры всех раннеров, приславших `/disk`, целиком."""
        ...

    async def list_disk_briefs(self, runner_ids: Collection[str] | None = None) -> dict[str, StoredDiskBrief]:
        """Проекция замеров (`disk_cleanable_bytes`, время замера и приёма) раннеров из `runner_ids` или всех:
        списки раннеров, сводка «Хранилища» и метрика читают её, а не отчёты целиком."""
        ...

    async def get_auto(self, runner_id: str) -> StoredDiskAuto | None:
        """Настройка и итог автоочистки; None, если раннера нет."""
        ...

    async def set_auto_policy(self, runner_id: str, policy: DiskAutoPolicy) -> bool:
        """Новая настройка; False, если раннера нет или он отозван."""
        ...

    async def claim_auto(self, runner_id: str, *, now: datetime, not_after: datetime) -> bool:
        """`disk_auto_at = now`, если прошлая автоочистка началась не позже `not_after` (или не было ни одной).

        Условное обновление: из двух реплик, проверивших один раннер одновременно, начинает одна.
        """
        ...

    async def set_auto_last(self, runner_id: str, last: DiskAutoLast, *, only_command: UUID | None = None) -> bool:
        """Итог автоочистки на месте прежнего; с `only_command` только если там та же команда (итог не затирает
        начало следующей)."""
        ...


class IRunnerCommandObserver(Protocol):
    async def command_finished(self, command: RunnerCommand) -> None:
        """Команда закрыта (итог раннера, остановка до доставки, просрочка, потеря): аудит, уведомление, метрика.

        Сбой наблюдателя переход не отменяет: он уже записан.
        """
        ...

    async def auto_started(self, command: RunnerCommand, *, free_bytes: int, total_bytes: int, percent: int) -> None:
        """Сервер поставил автоочистку по порогу места: аудит начала. Сбой команду не отменяет."""
        ...


class RunnerControlError(Exception):
    """Отказ протокола канала команд с кодом `RunnerErrorCode`: статус по коду (`RUNNER_ERROR_STATUS`)."""

    def __init__(self, code: RunnerErrorCode, detail: str = "") -> None:
        super().__init__(detail or code.value)
        self.code = code
        self.detail = detail or code.value


class RunnerCommandUnsupportedError(Exception):
    """Раннер не согласовал `control` и нужную виду команды возможность: команду ему не поставить."""


class RunnerCommandBusyError(Exception):
    """У раннера уже идёт очистка: вторая `disk.cleanup` (и `disk.measure` поверх неё) не ставится."""

    def __init__(self, command: RunnerCommand | None = None) -> None:
        super().__init__("the runner is already cleaning its disk")
        self.command = command
