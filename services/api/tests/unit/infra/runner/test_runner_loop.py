from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import pytest
from hse_doc_studio.core.jobs.entities import JobResult
from hse_doc_studio.core.jobs.enums import JobErrorCategory, JobStatus
from hse_doc_studio.core.jobs.errors import JobError, JobFailure
from hse_doc_studio.core.jobs.files import ArtifactRef
from hse_doc_studio.core.jobs.wire import JobEnvelope
from hse_doc_studio.infra.runner.backoff import Backoff
from hse_doc_studio.infra.runner.client import RunnerClient
from hse_doc_studio.infra.runner.executor import JobContext, JobOutcome, OutputFile
from hse_doc_studio.infra.runner.loop import RunnerFatalError, RunnerLoop, RunnerLoopConfig

from tests.unit.infra.runner.fake_runner_api import (
    RUNNER_TOKEN,
    TOKEN,
    FakeJob,
    FakeRunnerState,
    SwitchTransport,
    create_fake_app,
    envelope_body,
)

JOB_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
JOB_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


class FakeExecutor:
    def __init__(self) -> None:
        self.started: list[str] = []
        self.gate = asyncio.Event()
        self.block = False
        self.fail: Exception | None = None
        self.outputs: tuple[OutputFile, ...] = ()
        self.saw_cancel = False
        self.running = 0
        self.peak = 0

    async def execute(self, envelope: JobEnvelope, ctx: JobContext) -> JobOutcome:
        self.started.append(str(envelope.spec.id))
        self.running += 1
        self.peak = max(self.peak, self.running)
        try:
            ctx.log("line 1")
            ctx.log("line 2")
            if self.block:
                try:
                    await self.gate.wait()
                except asyncio.CancelledError:
                    self.saw_cancel = ctx.cancelled.is_set()
                    raise
            if self.fail is not None:
                raise self.fail
            return JobOutcome(JobResult(status=JobStatus.succeeded), self.outputs)
        finally:
            self.running -= 1


class Rig:
    def __init__(self, tmp_path: Path, concurrency: int = 1, drain_timeout_s: float = 2.0) -> None:
        self.state = FakeRunnerState()
        self.transport = SwitchTransport(create_fake_app(self.state))
        self.executor = FakeExecutor()
        self.client = RunnerClient(
            "http://api",
            TOKEN,
            version="0.1",
            transport=self.transport,
            retries=1,
            backoff_factory=lambda: Backoff(base_s=0.001, cap_s=0.005),
        )
        config = RunnerLoopConfig(
            name="r",
            version="0.1",
            concurrency=concurrency,
            poll_wait_s=0,
            log_flush_s=0.02,
            heartbeat_s=0.02,
            drain_timeout_s=drain_timeout_s,
            backoff_factory=lambda: Backoff(base_s=0.01, cap_s=0.05, jitter=0.0),
        )
        self.loop = RunnerLoop(self.client, self.executor, config)
        self.task: asyncio.Task[None] | None = None
        self.tmp_path = tmp_path

    def start(self) -> None:
        self.task = asyncio.create_task(self.loop.run())

    async def stop(self) -> None:
        self.loop.request_stop()
        assert self.task is not None
        await asyncio.wait_for(self.task, 10)
        await self.client.aclose()


async def until(predicate: object, timeout_s: float = 5.0) -> None:
    assert callable(predicate)
    async with asyncio.timeout(timeout_s):
        while not predicate():
            await asyncio.sleep(0.01)


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    return Rig(tmp_path)


def _completed(job: FakeJob) -> dict[str, object]:
    assert job.completed, "job was not completed"
    return job.completed[-1]


async def test_claim_run_log_complete(rig: Rig) -> None:
    job = rig.state.enqueue(envelope_body("compile", job_id=JOB_A))
    rig.start()
    await until(lambda: job.completed)
    await rig.stop()

    result = _completed(job)["result"]
    assert isinstance(result, dict)
    assert result["status"] == "succeeded"
    assert job.log_lines == ["line 1", "line 2"]
    assert rig.state.registrations[0]["concurrency"] == 1


async def test_failure_of_executor_is_reported_as_failed(rig: Rig) -> None:
    job = rig.state.enqueue(envelope_body("compile", job_id=JOB_A))
    rig.executor.fail = JobFailure(JobError(JobErrorCategory.invalid_input, "bad_source", "no main.tex"))
    rig.start()
    await until(lambda: job.completed)
    await rig.stop()

    result = _completed(job)["result"]
    assert isinstance(result, dict)
    assert result["status"] == "failed"
    assert result["error"] == {"category": "invalid_input", "code": "bad_source", "detail": "no main.tex"}


async def test_crash_of_executor_does_not_stop_the_loop(rig: Rig) -> None:
    first = rig.state.enqueue(envelope_body("compile", job_id=JOB_A))
    rig.executor.fail = RuntimeError("boom")
    rig.start()
    await until(lambda: first.completed)
    rig.executor.fail = None
    second = rig.state.enqueue(envelope_body("compile", job_id=JOB_B))
    await until(lambda: second.completed)
    await rig.stop()

    failed = _completed(first)["result"]
    assert isinstance(failed, dict)
    assert failed["error"]["code"] == "executor_crashed"  # type: ignore[index]
    ok = _completed(second)["result"]
    assert isinstance(ok, dict)
    assert ok["status"] == "succeeded"


async def test_outputs_are_uploaded_before_completion(rig: Rig, tmp_path: Path) -> None:
    data = b"%PDF-1.5 fake"
    path = tmp_path / "main.pdf"
    path.write_bytes(data)
    ref = ArtifactRef(path="out/main.pdf", sha256=hashlib.sha256(data).hexdigest(), size=len(data))
    rig.executor.outputs = (OutputFile(ref, path),)
    job = rig.state.enqueue(envelope_body("compile", job_id=JOB_A))
    rig.start()
    await until(lambda: job.completed)
    await rig.stop()

    assert job.artifacts[ref.sha256] == data
    assert _completed(job)["artifacts"] == [{"path": "out/main.pdf", "sha256": ref.sha256, "size": len(data)}]


async def test_cancel_flag_from_heartbeat_stops_the_job(rig: Rig) -> None:
    rig.executor.block = True
    job = rig.state.enqueue(envelope_body("compile", job_id=JOB_A))
    rig.start()
    await until(lambda: job.heartbeats >= 1)
    job.cancel = True
    await until(lambda: job.completed)
    await rig.stop()

    result = _completed(job)["result"]
    assert isinstance(result, dict)
    assert result["status"] == "cancelled"
    assert rig.executor.saw_cancel


async def test_lost_lease_abandons_the_job_without_report(rig: Rig) -> None:
    rig.executor.block = True
    job = rig.state.enqueue(envelope_body("compile", job_id=JOB_A))
    rig.start()
    await until(lambda: job.heartbeats >= 1)
    job.stale = True
    await until(lambda: rig.loop.running_jobs == 0)
    await rig.stop()

    assert job.completed == []
    assert rig.executor.running == 0


async def test_timeout_reports_timed_out(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.executor.block = True
    body = envelope_body("compile", job_id=JOB_A)
    body["timeout_s"] = 0.1
    job = rig.state.enqueue(body)
    rig.start()
    await until(lambda: job.completed)
    await rig.stop()

    result = _completed(job)["result"]
    assert isinstance(result, dict)
    assert result["status"] == "timed_out"


async def test_slots_limit_concurrency(tmp_path: Path) -> None:
    rig = Rig(tmp_path, concurrency=2)
    rig.executor.block = True
    jobs = [
        rig.state.enqueue(envelope_body("compile", job_id=f"cccccccc-cccc-4ccc-8ccc-cccccccccc0{i}")) for i in range(3)
    ]
    rig.start()
    await until(lambda: rig.executor.peak == 2)
    await asyncio.sleep(0.15)
    assert len(rig.executor.started) == 2
    rig.executor.gate.set()
    await until(lambda: all(j.completed for j in jobs))
    await rig.stop()

    assert rig.executor.peak == 2


async def test_api_down_backs_off_and_recovers(rig: Rig) -> None:
    rig.start()
    await until(lambda: rig.state.polls >= 1)
    rig.transport.down = True
    await until(lambda: rig.transport.failures >= 4)
    job = rig.state.enqueue(envelope_body("compile", job_id=JOB_A))
    rig.transport.down = False
    await until(lambda: job.completed)
    await rig.stop()

    assert len(rig.state.registrations) == 1


async def test_api_down_does_not_spend_the_registration_token_again(rig: Rig) -> None:
    rig.start()
    await until(lambda: rig.state.polls >= 1)
    rig.transport.down = True
    await until(lambda: rig.transport.failures >= 4)
    rig.transport.down = False
    await until(lambda: rig.state.polls >= 3)
    await rig.stop()

    assert len(rig.state.registrations) == 1


async def test_restored_identity_skips_registration(rig: Rig) -> None:
    rig.client.restore("runner-1", RUNNER_TOKEN)
    rig.start()
    await until(lambda: rig.state.polls >= 1)
    await rig.stop()

    assert rig.state.registrations == []


async def test_start_before_api_is_up_waits_for_registration(rig: Rig) -> None:
    rig.transport.down = True
    rig.start()
    await until(lambda: rig.transport.failures >= 3)
    assert rig.state.registrations == []
    rig.transport.down = False
    await until(lambda: rig.state.registrations)
    await rig.stop()


async def test_refused_registration_is_fatal(rig: Rig) -> None:
    rig.state.fail_register_with = 409
    rig.start()
    assert rig.task is not None
    with pytest.raises(RunnerFatalError):
        await asyncio.wait_for(rig.task, 5)
    await rig.client.aclose()


async def test_shutdown_drains_running_job(rig: Rig) -> None:
    rig.executor.block = True
    job = rig.state.enqueue(envelope_body("compile", job_id=JOB_A))
    rig.start()
    await until(lambda: rig.executor.started)
    rig.loop.request_stop()
    await asyncio.sleep(0.1)
    assert rig.task is not None
    assert not rig.task.done()
    rig.executor.gate.set()
    await asyncio.wait_for(rig.task, 5)
    await rig.client.aclose()

    result = _completed(job)["result"]
    assert isinstance(result, dict)
    assert result["status"] == "succeeded"


async def test_shutdown_cancels_job_after_drain_timeout(tmp_path: Path) -> None:
    rig = Rig(tmp_path, drain_timeout_s=0.1)
    rig.executor.block = True
    job = rig.state.enqueue(envelope_body("compile", job_id=JOB_A))
    rig.start()
    await until(lambda: rig.executor.started)
    await rig.stop()

    result = _completed(job)["result"]
    assert isinstance(result, dict)
    assert result["status"] == "cancelled"
    assert result["error"]["code"] == "runner_shutdown"  # type: ignore[index]
