from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import pytest
from hse_doc_studio.infra.ai.ollama.pull_jobs import PullModelJobManager


class _FakeRuntime:
    def __init__(self, lines: list[str]) -> None:
        self._lines = lines

    async def pull_model(self, name: str) -> AsyncGenerator[str, None]:
        lines = self._lines

        async def _gen() -> AsyncGenerator[str, None]:
            for line in lines:
                yield line

        return _gen()


async def _wait_done(mgr: PullModelJobManager, name: str) -> None:
    for _ in range(200):
        job = next((j for j in mgr.list_jobs() if j.name == name), None)
        if job is not None and job.state != "running":
            return
        await asyncio.sleep(0.005)
    raise AssertionError("pull job did not finish in time")


@pytest.mark.unit
async def test__pull_job__success_lifecycle() -> None:
    mgr = PullModelJobManager(_FakeRuntime(["pulling: 50%", "pulling: 100%", "__DONE__"]))

    started = await mgr.start("qwen2.5:7b")
    assert started.state == "running"

    await _wait_done(mgr, "qwen2.5:7b")
    [job] = mgr.list_jobs()
    assert job.state == "success"
    assert job.error is None


@pytest.mark.unit
async def test__pull_job__failure_captures_error_message() -> None:
    mgr = PullModelJobManager(_FakeRuntime(["pulling: 10%", "Ошибка: model not found", "__FAILED__"]))

    await mgr.start("nope:1b")
    await _wait_done(mgr, "nope:1b")

    [job] = mgr.list_jobs()
    assert job.state == "failure"
    assert job.error == "Ошибка: model not found"


@pytest.mark.unit
async def test__pull_job__dismiss_only_finished() -> None:
    mgr = PullModelJobManager(_FakeRuntime(["__DONE__"]))

    await mgr.start("qwen2.5:7b")
    await _wait_done(mgr, "qwen2.5:7b")

    mgr.dismiss("qwen2.5:7b")
    assert mgr.list_jobs() == []


class _BlockingRuntime:
    def __init__(self) -> None:
        self.release = asyncio.Event()

    async def pull_model(self, name: str) -> AsyncGenerator[str, None]:
        ev = self.release

        async def _gen() -> AsyncGenerator[str, None]:
            await ev.wait()
            yield "__DONE__"

        return _gen()


@pytest.mark.unit
async def test__pull_job__concurrency_cap_rejects_excess() -> None:
    rt = _BlockingRuntime()
    mgr = PullModelJobManager(rt, max_concurrent=2)
    await mgr.start("a")
    await mgr.start("b")  # two running (blocked on the event)

    with pytest.raises(ValueError, match="максимум загрузок"):
        await mgr.start("c")


@pytest.mark.unit
async def test__pull_job__concurrency_cap_accepts_new_pull_after_slot_frees() -> None:
    rt = _BlockingRuntime()
    mgr = PullModelJobManager(rt, max_concurrent=2)
    await mgr.start("a")
    await mgr.start("b")
    rt.release.set()  # let the two finish
    await _wait_done(mgr, "a")
    await _wait_done(mgr, "b")

    rt.release.set()
    await mgr.start("c")
