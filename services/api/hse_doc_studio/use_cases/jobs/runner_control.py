"""Канал команд раннеру на сервере: постановка, долгий опрос, ход и итог, просрочка доставки, потеря раннера.

Права и аудит постановки здесь не проверяются: это делает вызывающий сценарий админки и «Моих раннеров». Здесь
только состояние команды по таблице переходов (`docs/design/storage-cleanup.md`, 5.3) и протокол `/control/*` и
`/disk` (6.2). Закрытие команды любым путём (итог раннера, остановка до доставки, просрочка, потеря) сообщается
наблюдателям ровно один раз: переход в итог делает условное обновление, и закрывает его только одна реплика.
"""

from __future__ import annotations

import builtins
import logging
import time
from collections.abc import Awaitable, Callable, Collection, Sequence
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.jobs.control import (
    COMMANDS_KEPT_PER_RUNNER,
    CONTROL_POLL_INTERVAL_S,
    IRunnerCommandObserver,
    IRunnerCommandRepository,
    IRunnerDiskStore,
    RunnerCommandBusyError,
    RunnerCommandUnsupportedError,
    RunnerControlError,
    StoredDiskAuto,
    StoredDiskBrief,
    StoredDiskReport,
)
from hse_doc_studio.core.jobs.disk import (
    COMMAND_PICKUP_TIMEOUT_S,
    COMMAND_SILENCE_TIMEOUT_S,
    DISK_AUTO_MIN_INTERVAL_S,
    DISK_AUTO_TARGETS,
    DiskAutoLast,
    DiskAutoPolicy,
    DiskCleanupPayload,
    RunnerCommand,
    RunnerCommandKind,
    RunnerCommandPayload,
    RunnerCommandState,
    RunnerDiskReport,
    can_transition,
)
from hse_doc_studio.core.jobs.enums import RunnerErrorCode
from hse_doc_studio.core.jobs.errors import RunnerAuthError
from hse_doc_studio.core.jobs.routing import RunnerScope
from hse_doc_studio.core.jobs.runners import IRunnerRepository, Runner
from hse_doc_studio.core.jobs.wire import (
    FEATURE_CONTROL,
    FEATURE_DISK,
    FEATURE_DISK_AUTO,
    CommandProgressRequest,
    CommandProgressResponse,
    ControlPollRequest,
    ControlPollResponse,
    DiskCheckRequest,
    DiskCheckResponse,
    RunnerCommandEnvelope,
)
from hse_doc_studio.use_cases.jobs.wakeup import JobWakeup

logger = logging.getLogger(__name__)

# Какая возможность нужна виду команды сверх `control`: без неё команда раннеру не ставится и не выдаётся.
_KIND_FEATURE = {RunnerCommandKind.disk_measure: FEATURE_DISK, RunnerCommandKind.disk_cleanup: FEATURE_DISK}
# Сколько раз перечитать команду, если её сдвинули между чтением и условным обновлением.
_RACE_RETRIES = 3


class RunnerCommandWakeup(JobWakeup):
    """Будильник опроса команд: отдельный от будильника задач, чтобы новая сборка не будила опросы команд."""


def _require(runner: Runner, feature: str) -> None:
    if feature not in runner.features:
        raise RunnerControlError(RunnerErrorCode.feature_not_negotiated, f"the {feature} feature is not negotiated")


def deliverable_kinds(runner: Runner) -> frozenset[RunnerCommandKind]:
    """Виды команд, которые раннер согласовал: канал `control` и возможность вида."""
    if FEATURE_CONTROL not in runner.features:
        return frozenset()
    return frozenset(kind for kind, feature in _KIND_FEATURE.items() if feature in runner.features)


class RunnerControlService:
    def __init__(  # noqa: PLR0913
        self,
        commands: IRunnerCommandRepository,
        disks: IRunnerDiskStore,
        runners: IRunnerRepository,
        wakeup: RunnerCommandWakeup,
        *,
        clock: Clock = utc_now,
        poll_interval_s: float = CONTROL_POLL_INTERVAL_S,
        observers: Sequence[IRunnerCommandObserver] = (),
    ) -> None:
        self._commands = commands
        self._disks = disks
        self._runners = runners
        self._wakeup = wakeup
        self._clock = clock
        self._interval = poll_interval_s
        self._observers = tuple(observers)

    # --- сервер: постановка, остановка, чтение ---

    async def enqueue(
        self, runner: Runner, kind: RunnerCommandKind, payload: RunnerCommandPayload, *, created_by: str
    ) -> RunnerCommand:
        """Ставит команду раннеру; права проверяет вызывающий.

        `disk.measure` при стоящем или идущем замере возвращает его, при идущей очистке не ставится
        (`RunnerCommandBusyError`): раннер сам пришлёт замер после итога. Вторая очистка тоже `RunnerCommandBusyError`.
        """
        if runner.revoked_at is not None or kind not in deliverable_kinds(runner):
            raise RunnerCommandUnsupportedError(f"runner {runner.id} has not negotiated {kind.value}")
        await self.settle(runner.id)
        if kind is RunnerCommandKind.disk_measure:
            cleanup = await self._commands.find_open(runner.id, RunnerCommandKind.disk_cleanup)
            if cleanup is not None:
                raise RunnerCommandBusyError(cleanup)
            measuring = await self._commands.find_open(runner.id, RunnerCommandKind.disk_measure)
            if measuring is not None:
                return measuring
        now = self._clock()
        command = RunnerCommand(
            id=uuid4(),
            runner_id=runner.id,
            kind=kind,
            payload=payload,
            state=RunnerCommandState.queued,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        if not await self._commands.add(command, keep=COMMANDS_KEPT_PER_RUNNER):
            raise RunnerCommandBusyError(await self._commands.find_open(runner.id, RunnerCommandKind.disk_cleanup))
        self._wakeup.notify()
        return command

    async def cancel(self, runner_id: str, command_id: UUID) -> RunnerCommand:
        """«Остановить после текущего шага»: до доставки команда сразу `cancelled`, после раннер узнаёт об остановке
        в ответе на следующий ход. Закрытая команда даёт `command_finished`."""
        command = await self.get(runner_id, command_id)
        for _ in range(_RACE_RETRIES):
            if command.state.finished:
                raise RunnerControlError(RunnerErrorCode.command_finished, f"command {command_id} is finished")
            if command.state is RunnerCommandState.cancelling:
                return command
            target = (
                RunnerCommandState.cancelled
                if command.state is RunnerCommandState.queued
                else RunnerCommandState.cancelling
            )
            moved = await self._commands.transition(command.id, expected=command.state, to=target, now=self._clock())
            if moved is not None:
                await self._closed([moved])
                return moved
            command = await self.get(runner_id, command_id)
        raise RunnerControlError(RunnerErrorCode.command_finished, f"command {command_id} keeps changing")

    async def get(self, runner_id: str, command_id: UUID) -> RunnerCommand:
        """Команда раннера с проверкой сроков при чтении; чужая неотличима от несуществующей."""
        await self.settle(runner_id)
        command = await self._commands.get(command_id)
        if command is None or command.runner_id != runner_id:
            raise RunnerControlError(RunnerErrorCode.command_not_found, f"command {command_id} not found")
        return command

    async def recent(self, runner_id: str, *, limit: int = COMMANDS_KEPT_PER_RUNNER) -> builtins.list[RunnerCommand]:
        """Последние команды раннера, новые первыми, с проверкой сроков при чтении."""
        await self.settle(runner_id)
        return await self._commands.list_for_runner(runner_id, limit=limit)

    async def disk(self, runner_id: str) -> StoredDiskReport | None:
        return await self._disks.get_disk(runner_id)

    async def disk_auto(self, runner_id: str) -> StoredDiskAuto | None:
        return await self._disks.get_auto(runner_id)

    async def set_disk_auto(self, runner_id: str, policy: DiskAutoPolicy) -> bool:
        return await self._disks.set_auto_policy(runner_id, policy)

    async def disks(self) -> dict[str, StoredDiskReport]:
        return await self._disks.list_disks()

    async def disk_briefs(self, runner_ids: Collection[str] | None = None) -> dict[str, StoredDiskBrief]:
        """Проекция замеров для списков, сводки и метрики: отчёты целиком не читаются."""
        return await self._disks.list_disk_briefs(runner_ids)

    async def settle(self, runner_id: str | None = None) -> int:
        """Просрочка доставки и потеря раннера: у одного раннера при чтении, у всех в `runner_commands_reaper`."""
        now = self._clock()
        closed = await self._commands.expire_queued(
            before=now - timedelta(seconds=COMMAND_PICKUP_TIMEOUT_S), now=now, runner_id=runner_id
        )
        closed += await self._commands.lose(
            silent_before=now - timedelta(seconds=COMMAND_SILENCE_TIMEOUT_S), now=now, runner_id=runner_id
        )
        await self._closed(closed)
        return len(closed)

    # --- протокол раннера ---

    async def poll(
        self, runner: Runner, request: ControlPollRequest, *, gone: Callable[[], Awaitable[bool]] | None = None
    ) -> ControlPollResponse:
        """Долгий опрос команд: ответ сразу, как появилась команда для этого раннера, иначе пусто через `wait_s`.

        `touch` раннера не делает (живость меряет опрос задач). Пауза раннера команды не держит: она про задачи.
        """
        _require(runner, FEATURE_CONTROL)
        deadline = time.monotonic() + request.wait_s
        started = self._clock()
        while True:
            if gone is not None and await gone():
                return ControlPollResponse()
            current = await self._runners.get(runner.id)
            if current is None or _poll_over(current, runner, started):
                return ControlPollResponse()
            now = self._clock()
            command = await self._commands.claim(
                runner.id,
                deliverable_kinds(current),
                now=now,
                not_before=now - timedelta(seconds=COMMAND_PICKUP_TIMEOUT_S),
            )
            if command is not None:
                return ControlPollResponse(
                    command=RunnerCommandEnvelope(
                        id=command.id, kind=command.kind, payload=command.payload, issued_at=command.created_at
                    )
                )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return ControlPollResponse()
            await self._wakeup.wait(min(remaining, self._interval))

    async def progress(
        self, runner: Runner, command_id: UUID, request: CommandProgressRequest
    ) -> CommandProgressResponse:
        """Ход или итог команды. Итог закрывает её, повтор того же итога безвреден; ход по закрытой (`expired`,
        `lost`, другой итог) даёт `command_finished`, и раннер бросает выполнение после текущего шага."""
        _require(runner, FEATURE_CONTROL)
        command = await self._commands.get(command_id)
        for _ in range(_RACE_RETRIES):
            target = _progress_target(runner, command_id, command, request.state)
            if target is None or command is None:
                return CommandProgressResponse(cancel=False)
            moved = await self._commands.transition(
                command.id, expected=command.state, to=target, now=self._clock(), progress=request.progress
            )
            if moved is not None:
                if moved.state.finished:
                    await self._closed([moved])
                return CommandProgressResponse(cancel=moved.state is RunnerCommandState.cancelling)
            command = await self._commands.get(command_id)
        raise RunnerControlError(RunnerErrorCode.command_finished, f"command {command_id} keeps changing")

    async def report_disk(self, runner: Runner, report: RunnerDiskReport) -> None:
        """Последний замер раннера: строка обновляется на месте. Личный раннер тоже: его диск видит владелец."""
        _require(runner, FEATURE_DISK)
        if not await self._disks.set_disk(runner.id, report, self._clock()):
            raise RunnerAuthError(RunnerErrorCode.runner_unauthorized)

    async def disk_check(self, runner: Runner, request: DiskCheckRequest) -> DiskCheckResponse:
        """Автоочистка по порогу места (storage-cleanup.md, 14.3): команда, если её пора начать, иначе пусто.

        Пора, если раннер общий, автоочистка у него включена, свободно меньше порога, очистка не идёт и прошлая
        автоочистка началась не меньше часа назад. Команда вставляется сразу `delivered`: раннер получает её в ответе.
        """
        _require(runner, FEATURE_DISK_AUTO)
        policy = await self._auto_due(runner, request)
        if policy is None:
            return DiskCheckResponse()
        now = self._clock()
        not_after = now - timedelta(seconds=DISK_AUTO_MIN_INTERVAL_S)
        if not await self._disks.claim_auto(runner.id, now=now, not_after=not_after):
            return DiskCheckResponse()
        command = RunnerCommand(
            id=uuid4(),
            runner_id=runner.id,
            kind=RunnerCommandKind.disk_cleanup,
            payload=DiskCleanupPayload(targets=DISK_AUTO_TARGETS, auto=True),
            state=RunnerCommandState.delivered,
            # Запустил не человек: в «Диске» подпись «Автоочистка», в аудите актор `null`.
            created_by="",
            created_at=now,
            updated_at=now,
            delivered_at=now,
        )
        if not await self._commands.add(command, keep=COMMANDS_KEPT_PER_RUNNER):
            # Ручная очистка успела раньше: интервал потрачен, следующая проверка через час.
            return DiskCheckResponse()
        await self._auto_started(command, request, policy)
        return DiskCheckResponse(
            command=RunnerCommandEnvelope(
                id=command.id, kind=command.kind, payload=command.payload, issued_at=command.created_at
            )
        )

    async def _auto_due(self, runner: Runner, request: DiskCheckRequest) -> DiskAutoPolicy | None:
        """Настройка раннера, если автоочистку пора начать по месту и занятости (интервал проверяет `claim_auto`)."""
        if runner.scope is not RunnerScope.shared or not {FEATURE_CONTROL, FEATURE_DISK} <= runner.features:
            return None
        stored = await self._disks.get_auto(runner.id)
        if stored is None or not stored.policy.enabled:
            return None
        if not stored.policy.below(request.free_bytes, request.total_bytes):
            return None
        await self.settle(runner.id)
        if await self._commands.find_open(runner.id, RunnerCommandKind.disk_cleanup) is not None:
            return None
        return stored.policy

    async def _auto_started(self, command: RunnerCommand, request: DiskCheckRequest, policy: DiskAutoPolicy) -> None:
        last = DiskAutoLast(
            command_id=command.id,
            state=command.state,
            started_at=command.created_at,
            finished_at=None,
            freed_bytes=0,
            free_bytes=request.free_bytes,
            total_bytes=request.total_bytes,
        )
        await self._disks.set_auto_last(command.runner_id, last)
        logger.info(
            "runner %s: disk auto cleanup %s, %d of %d bytes free",
            command.runner_id,
            command.id,
            request.free_bytes,
            request.total_bytes,
        )
        for observer in self._observers:
            try:
                await observer.auto_started(
                    command,
                    free_bytes=request.free_bytes,
                    total_bytes=request.total_bytes,
                    percent=policy.min_free_percent,
                )
            except Exception:
                logger.exception("runner command observer failed on auto start %s", command.id)

    async def _auto_finished(self, command: RunnerCommand) -> None:
        """Итог автоочистки переписывает `disk_auto_last`, если там ещё она (а не начало следующей)."""
        stored = await self._disks.get_auto(command.runner_id)
        if stored is None or stored.last is None or stored.last.command_id != command.id:
            return
        progress = command.progress
        last = DiskAutoLast(
            command_id=command.id,
            state=command.state,
            started_at=stored.last.started_at,
            finished_at=command.finished_at,
            freed_bytes=progress.freed_bytes if progress is not None else 0,
            free_bytes=stored.last.free_bytes,
            total_bytes=stored.last.total_bytes,
        )
        await self._disks.set_auto_last(command.runner_id, last, only_command=command.id)

    async def _closed(self, commands: Sequence[RunnerCommand]) -> None:
        for command in commands:
            if not command.state.finished:
                continue
            if isinstance(command.payload, DiskCleanupPayload) and command.payload.auto:
                try:
                    await self._auto_finished(command)
                except Exception:
                    logger.exception("runner %s: auto cleanup result not saved", command.runner_id)
            for observer in self._observers:
                try:
                    await observer.command_finished(command)
                except Exception:
                    logger.exception("runner command observer failed on %s", command.id)


def _poll_over(current: Runner, snapshot: Runner, started: datetime) -> bool:
    """Опрос больше некому отвечать: раннер отозван, ушёл через `/offline` после начала опроса или сменил токен."""
    if current.revoked_at is not None or current.token_hash != snapshot.token_hash:
        return True
    return current.offline_at is not None and current.offline_at >= started


def _progress_target(
    runner: Runner, command_id: UUID, command: RunnerCommand | None, reported: RunnerCommandState
) -> RunnerCommandState | None:
    """Куда сдвинуть команду по ходу раннера; None: повтор уже записанного итога, двигать нечего."""
    if command is None or command.runner_id != runner.id or command.state is RunnerCommandState.queued:
        raise RunnerControlError(RunnerErrorCode.command_not_found, f"command {command_id} not found")
    if command.state.finished:
        if command.state is reported:
            return None
        raise RunnerControlError(RunnerErrorCode.command_finished, f"command {command_id} is {command.state.value}")
    # Остановку раннер узнаёт в ответе: пока он шлёт `running`, команда остаётся `cancelling`.
    if command.state is RunnerCommandState.cancelling and reported is RunnerCommandState.running:
        return RunnerCommandState.cancelling
    if not can_transition(command.state, reported):
        raise RunnerControlError(
            RunnerErrorCode.command_finished, f"command {command_id} cannot go {command.state} -> {reported}"
        )
    return reported
