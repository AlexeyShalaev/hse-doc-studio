"""Cleanup job lifecycle: step order, error isolation, cancellation, busy-lock."""

from __future__ import annotations

import asyncio

import pytest
from hse_doc_studio.infra.docker.cleanup_jobs import (
    CleanupBusyError,
    CleanupStep,
    DockerCleanupJobManager,
)
from hse_doc_studio.infra.docker.system_manager import CleanupResult


class _FakeSystemManager:
    """Scriptable stand-in: records call order, optionally blocks per step."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.gate: asyncio.Event | None = None
        self.fail_refs: set[str] = set()

    async def _maybe_wait(self) -> None:
        if self.gate is not None:
            await self.gate.wait()

    async def prune_build_cache(self) -> CleanupResult:
        self.calls.append("build_cache")
        await self._maybe_wait()
        return CleanupResult(target="build_cache", freed_bytes=1_000)

    async def prune_dangling_images(self) -> CleanupResult:
        self.calls.append("dangling_images")
        return CleanupResult(target="dangling_images", freed_bytes=200)

    async def remove_images(self, references: list[str], target: str = "unused_images") -> CleanupResult:
        ref = references[0]
        self.calls.append(f"image:{ref}")
        if ref in self.fail_refs:
            return CleanupResult(target=target, freed_bytes=0, errors=[f"{ref}: boom"])
        return CleanupResult(target=target, freed_bytes=50, removed=[ref])

    async def remove_stopped_managed_container(self, name: str) -> CleanupResult:
        self.calls.append(f"container:{name}")
        return CleanupResult(target="container", freed_bytes=10, removed=[name])


async def _wait_finished(jobs: DockerCleanupJobManager) -> None:
    job = jobs.current()
    assert job is not None
    assert job.task is not None
    await job.task


async def test__run__executes_steps_in_order_and_accumulates_freed_bytes() -> None:
    fake = _FakeSystemManager()
    jobs = DockerCleanupJobManager(fake)  # type: ignore[arg-type]

    await jobs.start(
        [
            CleanupStep(kind="build_cache"),
            CleanupStep(kind="dangling_images"),
            CleanupStep(kind="image", ref="texlive/texlive:TL2023"),
            CleanupStep(kind="container", ref="hse-ollama"),
        ]
    )
    await _wait_finished(jobs)

    job = jobs.current()
    assert job is not None
    assert job.status == "done"
    assert job.freed_bytes == 1_000 + 200 + 50 + 10
    assert fake.calls == [
        "build_cache",
        "dangling_images",
        "image:texlive/texlive:TL2023",
        "container:hse-ollama",
    ]
    assert all(step.status == "done" for step in job.steps)


async def test__run__step_error_is_isolated_and_marks_job_error() -> None:
    fake = _FakeSystemManager()
    fake.fail_refs = {"bad:ref"}
    jobs = DockerCleanupJobManager(fake)  # type: ignore[arg-type]

    await jobs.start(
        [
            CleanupStep(kind="image", ref="bad:ref"),
            CleanupStep(kind="image", ref="good:ref"),
        ]
    )
    await _wait_finished(jobs)

    job = jobs.current()
    assert job is not None
    assert job.status == "error"
    assert job.steps[0].status == "error"
    assert job.steps[0].error is not None
    # The failure of one step must not stop the rest of the plan.
    assert job.steps[1].status == "done"
    assert job.freed_bytes == 50


async def test__cancel__skips_pending_steps_after_the_current_one_finishes() -> None:
    fake = _FakeSystemManager()
    fake.gate = asyncio.Event()
    jobs = DockerCleanupJobManager(fake)  # type: ignore[arg-type]

    await jobs.start(
        [
            CleanupStep(kind="build_cache"),
            CleanupStep(kind="image", ref="never:touched"),
        ]
    )
    await asyncio.sleep(0.02)  # let the first step start and block on the gate

    cancelled = jobs.cancel()
    assert cancelled is not None
    assert cancelled.status == "cancelling"

    fake.gate.set()
    await _wait_finished(jobs)

    job = jobs.current()
    assert job is not None
    assert job.status == "cancelled"
    # The in-flight step completed (its freed space is real)…
    assert job.steps[0].status == "done"
    assert job.freed_bytes == 1_000
    # …but the pending one was never started.
    assert job.steps[1].status == "skipped"
    assert "image:never:touched" not in fake.calls


async def test__start__refuses_a_second_job_while_one_is_active() -> None:
    fake = _FakeSystemManager()
    fake.gate = asyncio.Event()
    jobs = DockerCleanupJobManager(fake)  # type: ignore[arg-type]

    await jobs.start([CleanupStep(kind="build_cache")])

    with pytest.raises(CleanupBusyError):
        await jobs.start([CleanupStep(kind="dangling_images")])

    fake.gate.set()
    await _wait_finished(jobs)

    # After the first finishes a new job is accepted (and replaces the old one).
    second = await jobs.start([CleanupStep(kind="dangling_images")])
    await _wait_finished(jobs)
    assert jobs.current() is not None
    assert jobs.current().id == second.id  # type: ignore[union-attr]
