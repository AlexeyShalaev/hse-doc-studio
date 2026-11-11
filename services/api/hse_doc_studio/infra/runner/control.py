"""Канал команд раннера: долгий опрос `/control/poll`, ход и итог команд, отчёт о диске (storage-cleanup.md, 6.2, 6.3).

`RunnerControlLoop` живёт рядом с опросом задач отдельными задачами asyncio: слоты сборок, шлюз и пульс задач его
не касаются, а он их. Запускает его `RunnerLoop` после `/announce`, только если сервер согласовал и `control`, и
`disk`: со старым сервером канала нет и в журнале о нём ни слова.

Команды:

- `disk.measure`: свежий замер, `POST /disk`, затем итог `done` без шагов (или `error` с причиной);
- `disk.cleanup`: `RunnerDiskService.cleanup` в фоне; ход уходит своей задачей не чаще раза в секунду (последний
  снимок, промежуточные схлопываются) и раз в минуту повтором, пока шаг идёт долго (иначе сервер через 3 минуты
  тишины сочтёт раннер пропавшим); итог с повторами, как `complete` задачи; `cancel` в ответе на ход и закрытая на
  сервере команда (`command_finished`, `command_not_found`) останавливают очистку после текущего шага. После итога
  раннер сразу присылает новый замер.

Отчёт о диске раннер шлёт и сам: сразу после запуска канала (то есть после `/announce`), раз в 6 часов и после
каждой очистки. Повторно доставленная команда (тот же id) второй раз не выполняется: идущая продолжается, по
завершённой повторяется её итог.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import OrderedDict
from collections.abc import Callable, Coroutine, Iterable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from hse_doc_studio.core.jobs.disk import (
    DISK_REPORT_EVERY_S,
    MAX_STEP_ERROR,
    CommandProgress,
    DiskCleanupPayload,
    RunnerCommandKind,
    RunnerCommandState,
)
from hse_doc_studio.core.jobs.enums import RunnerErrorCode
from hse_doc_studio.core.jobs.wire import (
    MAX_POLL_WAIT_S,
    CommandProgressRequest,
    ControlPollRequest,
    RunnerCommandEnvelope,
)
from hse_doc_studio.infra.runner.backoff import Backoff
from hse_doc_studio.infra.runner.client import RunnerApiError, RunnerClient, RunnerCommandRejected, RunnerUnreachable
from hse_doc_studio.infra.runner.disk import DiskCleanupBusyError, DiskCleanupRun, RunnerDiskService

logger = logging.getLogger(__name__)

# Ход команды не чаще раза в секунду; пока шаг идёт дольше, тот же ход повторяется раз в минуту (сервер считает
# команду потерянной после 3 минут без хода, `COMMAND_SILENCE_TIMEOUT_S`).
PROGRESS_MIN_INTERVAL_S = 1.0
PROGRESS_KEEPALIVE_S = 60.0
# Неудачный отчёт о диске повторяется раньше, чем через 6 часов.
DISK_REPORT_RETRY_S = 300.0
BUSY_ERROR = "another disk cleanup is already running on this runner"
# Сколько id команд помнить, чтобы повторная доставка не запустила очистку второй раз.
_SEEN_LIMIT = 64
# Запас на снятие очистки и доставку итога после принудительной остановки.
_FORCE_GRACE_S = 5.0
# Сервер закрыл канал (откатился на версию без него или забыл возможность): опрос прекращается до нового `/announce`.
_CHANNEL_GONE_CODES = frozenset({RunnerErrorCode.feature_not_negotiated.value})
# Команда закрыта на сервере (истекла, потеряна, удалена): выполнение бросается после текущего шага.
_COMMAND_GONE_CODES = frozenset({RunnerErrorCode.command_finished.value, RunnerErrorCode.command_not_found.value})

_Final = tuple[RunnerCommandState, CommandProgress]


@dataclass(frozen=True)
class ControlLoopConfig:
    wait_s: int = MAX_POLL_WAIT_S
    # Пустой ответ быстрее этого (сервер держит опрос меньше, `wait_s=0`) ждёт остаток: без вращения вхолостую.
    min_poll_interval_s: float = 1.0
    progress_interval_s: float = PROGRESS_MIN_INTERVAL_S
    progress_keepalive_s: float = PROGRESS_KEEPALIVE_S
    report_every_s: float = DISK_REPORT_EVERY_S
    report_retry_s: float = DISK_REPORT_RETRY_S
    # Сколько ждать при остановке, пока идущая очистка доведёт шаг и доставит итог `cancelled`.
    stop_timeout_s: float = 30.0
    backoff_factory: Callable[[], Backoff] = field(default=lambda: Backoff(base_s=0.5, cap_s=30.0))


def _one_line(text: str) -> str:
    line = " ".join(text.split())
    return line[:MAX_STEP_ERROR] or "error"


def _empty(error: str | None = None) -> CommandProgress:
    return CommandProgress(steps=(), freed_bytes=0, error=_one_line(error) if error else None)


class RunnerControlLoop:
    """Опрос команд, исполнение `disk.*` и отчёт о диске; `start` после согласования, `stop` при остановке раннера."""

    def __init__(
        self, client: RunnerClient, disk: RunnerDiskService, config: ControlLoopConfig | None = None
    ) -> None:
        self._client = client
        self._disk = disk
        self._config = config or ControlLoopConfig()
        self._stopping = asyncio.Event()
        self._report_now = asyncio.Event()
        self._measure_lock = asyncio.Lock()
        self._poll_task: asyncio.Task[None] | None = None
        self._report_task: asyncio.Task[None] | None = None
        self._handlers: set[asyncio.Task[None]] = set()
        self._runs: dict[UUID, DiskCleanupRun] = {}
        # id команды: None пока выполняется, итог после завершения (повтор доставки повторяет итог).
        self._seen: OrderedDict[UUID, _Final | None] = OrderedDict()
        self._next_report = 0.0

    @property
    def running(self) -> bool:
        return self._poll_task is not None and not self._poll_task.done()

    def start(self) -> None:
        """Открыть канал: опрос команд и отчёт о диске (первый сразу)."""
        if self.running:
            return
        self._stopping.clear()
        self._next_report = time.monotonic()
        self._poll_task = asyncio.create_task(self._poll_loop())
        if self._report_task is None or self._report_task.done():
            self._report_task = asyncio.create_task(self._report_loop())

    def request_report(self) -> None:
        """Прислать замер вне расписания (повторный `/announce`)."""
        self._report_now.set()

    async def stop(self) -> None:
        """Мягкая остановка: опрос прекращается, идущая очистка доводит шаг и доставляет итог `cancelled`."""
        self._stopping.set()
        for run in list(self._runs.values()):
            run.cancel()
        background = [task for task in (self._poll_task, self._report_task) if task is not None]
        for task in background:
            task.cancel()
        await asyncio.gather(*background, return_exceptions=True)
        if not self._handlers:
            return
        _, pending = await asyncio.wait(set(self._handlers), timeout=self._config.stop_timeout_s)
        if not pending:
            return
        logger.warning("disk command did not finish in time, stopping it")
        for run in list(self._runs.values()):
            if run.task is not None:
                run.task.cancel()
        _, pending = await asyncio.wait(pending, timeout=_FORCE_GRACE_S)
        await _cancel_all(pending)

    async def abort(self) -> None:
        """Жёсткая остановка (раннер падает): всё снимается без доставки итога."""
        self._stopping.set()
        for run in list(self._runs.values()):
            if run.task is not None:
                run.task.cancel()
        tasks = [task for task in (self._poll_task, self._report_task, *self._handlers) if task is not None]
        await _cancel_all(tasks)

    # ------------------------------------------------------------------ опрос

    async def _poll_loop(self) -> None:
        backoff = self._config.backoff_factory()
        while not self._stopping.is_set():
            started = time.monotonic()
            try:
                response = await self._client.control_poll(ControlPollRequest(wait_s=self._config.wait_s))
            except RunnerCommandRejected as exc:
                backoff.reset()
                logger.warning("runner command rejected: %s", exc.reason)
                if exc.command_id is not None:
                    self._spawn(self._reject(exc.command_id, exc.reason))
                continue
            except RunnerApiError as exc:
                if exc.status in (404, 405) or exc.code in _CHANNEL_GONE_CODES:
                    logger.info("server closed the command channel (%s), waiting for the next announce", exc)
                    if self._report_task is not None:
                        self._report_task.cancel()
                    return
                logger.warning("control poll rejected: %s", exc)
                await self._sleep_or_stop(backoff.next())
                continue
            except RunnerUnreachable as exc:
                logger.debug("control poll: api unreachable (%s)", exc)
                await self._sleep_or_stop(backoff.next())
                continue
            backoff.reset()
            if response.command is not None:
                self._accept(response.command)
                continue
            idle = self._config.min_poll_interval_s - (time.monotonic() - started)
            if idle > 0:
                await self._sleep_or_stop(idle)

    def _accept(self, envelope: RunnerCommandEnvelope) -> None:
        if envelope.id in self._seen:
            final = self._seen[envelope.id]
            logger.info("command %s delivered again, not running it twice", envelope.id)
            if final is not None:
                self._spawn(self._deliver_final(envelope.id, *final))
            return
        self._remember(envelope.id, None)
        logger.info("runner command %s: %s", envelope.id, envelope.kind.value)
        if envelope.kind is RunnerCommandKind.disk_measure:
            self._spawn(self._measure_command(envelope.id))
        elif isinstance(envelope.payload, DiskCleanupPayload):
            self._spawn(self._cleanup_command(envelope.id, envelope.payload))

    def _remember(self, command_id: UUID, final: _Final | None) -> None:
        self._seen[command_id] = final
        self._seen.move_to_end(command_id)
        while len(self._seen) > _SEEN_LIMIT:
            self._seen.popitem(last=False)

    def _spawn(self, coro: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(coro)
        self._handlers.add(task)
        task.add_done_callback(self._on_handler_done)

    def _on_handler_done(self, task: asyncio.Task[None]) -> None:
        self._handlers.discard(task)
        if not task.cancelled() and (exc := task.exception()) is not None:
            logger.error("runner command task crashed", exc_info=exc)

    # ------------------------------------------------------------------ команды

    async def _reject(self, command_id: UUID, reason: str) -> None:
        if command_id in self._seen:
            return
        final = (RunnerCommandState.error, _empty(reason))
        self._remember(command_id, final)
        await self._deliver_final(command_id, *final)

    async def _measure_command(self, command_id: UUID) -> None:
        error = await self._report_disk()
        final = (RunnerCommandState.done if error is None else RunnerCommandState.error, _empty(error))
        self._remember(command_id, final)
        await self._deliver_final(command_id, *final)

    async def _cleanup_command(self, command_id: UUID, payload: DiskCleanupPayload) -> None:
        reporter = _ProgressReporter(self._client, command_id, self._config)
        try:
            try:
                run = self._disk.cleanup(payload, reporter.observe)
            except DiskCleanupBusyError:
                logger.warning("command %s: %s", command_id, BUSY_ERROR)
                final = (RunnerCommandState.error, _empty(BUSY_ERROR))
                self._remember(command_id, final)
                await reporter.finish(*final)
                return
            reporter.bind(run)
            self._runs[command_id] = run
            try:
                outcome = await run.wait()
            finally:
                self._runs.pop(command_id, None)
            self._remember(command_id, (outcome.state, outcome.progress))
            logger.info(
                "runner command %s: %s, freed %d bytes", command_id, outcome.state.value, outcome.progress.freed_bytes
            )
            await reporter.finish(outcome.state, outcome.progress)
        finally:
            reporter.close()
        if not self._stopping.is_set():
            # Новый замер сразу после итога: экран показывает, что осталось.
            self._report_now.set()

    async def _deliver_final(self, command_id: UUID, state: RunnerCommandState, progress: CommandProgress) -> None:
        try:
            await self._client.command_progress(command_id, CommandProgressRequest(state, progress), final=True)
        except (RunnerApiError, RunnerUnreachable) as exc:
            logger.warning("command %s: result not delivered: %s", command_id, exc)

    # ------------------------------------------------------------------ отчёт о диске

    async def _report_loop(self) -> None:
        while not self._stopping.is_set():
            delay = max(0.0, self._next_report - time.monotonic())
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._report_now.wait(), delay)
            if self._stopping.is_set():
                return
            self._report_now.clear()
            await self._report_disk()

    async def _report_disk(self) -> str | None:
        """Замер и `POST /disk`; причина одной строкой при сбое. Замеры идут по одному: `docker system df` до 90 с."""
        async with self._measure_lock:
            try:
                report = await self._disk.measure()
            except Exception as exc:  # noqa: BLE001 — сбой замера закрывает команду ошибкой, раннер работает дальше
                logger.warning("disk measure failed", exc_info=True)
                self._next_report = time.monotonic() + self._config.report_retry_s
                return f"disk measure failed: {type(exc).__name__}"
            try:
                await self._client.report_disk(report)
            except (RunnerApiError, RunnerUnreachable) as exc:
                logger.warning("disk report not delivered: %s", exc)
                self._next_report = time.monotonic() + self._config.report_retry_s
                return f"disk report not delivered: {exc}"
            self._next_report = time.monotonic() + self._config.report_every_s
            return None

    async def _sleep_or_stop(self, delay_s: float) -> None:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._stopping.wait(), delay_s)


class _ProgressReporter:
    """Доставка хода одной очистки своей задачей: наблюдатель очистки только кладёт снимок и не ждёт сеть.

    Последний снимок уходит не чаще `progress_interval_s` (итог без ожидания), пока шаг идёт долго, тот же ход
    повторяется раз в `progress_keepalive_s`. `cancel` в ответе останавливает очистку после текущего шага; закрытая
    на сервере команда тоже, и ход по ней больше не шлётся.
    """

    def __init__(self, client: RunnerClient, command_id: UUID, config: ControlLoopConfig) -> None:
        self._client = client
        self._id = command_id
        self._interval = config.progress_interval_s
        self._keepalive = config.progress_keepalive_s
        # До первого шага (замер Docker идёт до 90 с) повтор хода шлёт пустой `running`: команда не потеряется.
        self._latest: _Final = (RunnerCommandState.running, _empty())
        self._changed = asyncio.Event()
        self._final = asyncio.Event()
        self._run: DiskCleanupRun | None = None
        self._abandoned = False
        self._task = asyncio.create_task(self._send_loop())

    def bind(self, run: DiskCleanupRun) -> None:
        self._run = run

    async def observe(self, state: RunnerCommandState, progress: CommandProgress) -> None:
        if self._final.is_set():
            return
        self._latest = (state, progress)
        self._changed.set()
        if state is not RunnerCommandState.running:
            self._final.set()

    async def finish(self, state: RunnerCommandState, progress: CommandProgress) -> None:
        """Итог (если наблюдатель его ещё не получил) и ожидание его доставки."""
        await self.observe(state, progress)
        await self._task

    def close(self) -> None:
        """Снять доставку, если выполнение команды сняли раньше итога."""
        self._task.cancel()

    async def _send_loop(self) -> None:
        last: float | None = None
        while True:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._changed.wait(), self._keepalive)
            if not self._final.is_set() and last is not None:
                delay = self._interval - (time.monotonic() - last)
                if delay > 0:
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(self._final.wait(), delay)
            self._changed.clear()
            state, progress = self._latest
            last = time.monotonic()
            final = state is not RunnerCommandState.running
            await self._send(state, progress, final=final)
            if final or self._abandoned:
                return

    async def _send(self, state: RunnerCommandState, progress: CommandProgress, *, final: bool) -> None:
        try:
            response = await self._client.command_progress(
                self._id, CommandProgressRequest(state, progress), final=final
            )
        except RunnerApiError as exc:
            if exc.code in _COMMAND_GONE_CODES:
                logger.warning("command %s is closed on the server (%s), stopping after the current step", self._id, exc)
                self._abandoned = True
                self._cancel_run()
            else:
                logger.warning("command %s: progress rejected: %s", self._id, exc)
            return
        except RunnerUnreachable as exc:
            # Ход повторится со следующим шагом или повтором; итог клиент уже повторял.
            logger.warning("command %s: progress not delivered: %s", self._id, exc)
            return
        if response.cancel:
            logger.info("command %s: stop requested, stopping after the current step", self._id)
            self._cancel_run()

    def _cancel_run(self) -> None:
        if self._run is not None:
            self._run.cancel()


async def _cancel_all(tasks: Iterable[asyncio.Task[None]]) -> None:
    pending = [task for task in tasks if not task.done()]
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


__all__ = [
    "BUSY_ERROR",
    "DISK_REPORT_RETRY_S",
    "PROGRESS_KEEPALIVE_S",
    "PROGRESS_MIN_INTERVAL_S",
    "ControlLoopConfig",
    "RunnerControlLoop",
]
