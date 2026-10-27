from __future__ import annotations

import asyncio
import threading

import pytest
from hse_doc_studio.use_cases.git_sync.blocking import finish_before_cancel

pytestmark = pytest.mark.unit


async def test_finish_before_cancel__cancel_waits_for_the_thread_to_end() -> None:
    started = threading.Event()
    finished = threading.Event()

    def work() -> None:
        started.set()
        finished.wait(timeout=0.3)
        finished.set()

    task = asyncio.create_task(finish_before_cancel(work))
    while not started.is_set():
        await asyncio.sleep(0.005)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert finished.is_set()


async def test_finish_before_cancel__passes_arguments_and_errors_through() -> None:
    seen: list[int] = []

    def work(value: int, *, fail: bool) -> None:
        seen.append(value)
        if fail:
            raise ValueError("boom")

    await finish_before_cancel(work, 1, fail=False)
    with pytest.raises(ValueError, match="boom"):
        await finish_before_cancel(work, 2, fail=True)
    assert seen == [1, 2]


async def test__finish_before_cancel__returns_the_result_of_the_thread() -> None:
    assert await finish_before_cancel(lambda a, b: a + b, 2, 3) == 5
