from __future__ import annotations

import asyncio
from contextlib import suppress

from hse_doc_studio.infra.update.auto_update_scheduler import AutoUpdateScheduler
from hse_doc_studio.use_cases.system.auto_update import AutoUpdateOutcome, AutoUpdateResult

_TICK_S = 0.01


async def _run_briefly(scheduler: AutoUpdateScheduler, seconds: float = 0.1) -> None:
    task = asyncio.create_task(scheduler.loop())
    await asyncio.sleep(seconds)
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


async def test__loop__ticks_repeatedly() -> None:
    calls = 0

    async def tick() -> AutoUpdateResult:
        nonlocal calls
        calls += 1
        return AutoUpdateResult(AutoUpdateOutcome.up_to_date)

    await _run_briefly(AutoUpdateScheduler(tick, interval_s=_TICK_S, startup_delay_s=0))

    assert calls > 1


async def test__loop__failing_tick__keeps_the_loop_alive() -> None:
    # Упавший цикл не поднимется до перезапуска приложения, и обновления тихо
    # перестанут приходить — самый неприятный из возможных исходов.
    calls = 0

    async def tick() -> AutoUpdateResult:
        nonlocal calls
        calls += 1
        msg = "docker недоступен"
        raise RuntimeError(msg)

    await _run_briefly(AutoUpdateScheduler(tick, interval_s=_TICK_S, startup_delay_s=0))

    assert calls > 1


async def test__loop__startup_delay__is_respected() -> None:
    # Подменять контейнер, который пользователь только что поднял, — плохой
    # первый опыт; первый тик обязан подождать.
    calls = 0

    async def tick() -> AutoUpdateResult:
        nonlocal calls
        calls += 1
        return AutoUpdateResult(AutoUpdateOutcome.up_to_date)

    await _run_briefly(
        AutoUpdateScheduler(tick, interval_s=_TICK_S, startup_delay_s=10),
        seconds=0.05,
    )

    assert calls == 0


async def test__loop__cancellation__is_not_swallowed() -> None:
    # `suppress(Exception)` вокруг тика не должен глотать отмену: иначе задача
    # переживала бы shutdown приложения.
    async def tick() -> AutoUpdateResult:
        await asyncio.sleep(10)
        return AutoUpdateResult(AutoUpdateOutcome.up_to_date)

    scheduler = AutoUpdateScheduler(tick, interval_s=_TICK_S, startup_delay_s=0)
    task = asyncio.create_task(scheduler.loop())
    await asyncio.sleep(0.02)
    task.cancel()

    with suppress(asyncio.CancelledError):
        await task
    assert task.cancelled()
