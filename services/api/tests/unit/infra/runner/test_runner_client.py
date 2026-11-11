from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest
from hse_doc_studio.core.jobs.codec import decode, encode_result
from hse_doc_studio.core.jobs.disk import (
    CommandProgress,
    DiskCleanupPayload,
    DiskTarget,
    RunnerCommandState,
    RunnerDiskReport,
)
from hse_doc_studio.core.jobs.entities import JobResult
from hse_doc_studio.core.jobs.enums import JobStatus
from hse_doc_studio.core.jobs.files import ArtifactRef
from hse_doc_studio.core.jobs.wire import (
    ArtifactUploadRequest,
    CommandProgressRequest,
    CompleteRequest,
    ControlPollRequest,
    PollRequest,
    RunnerRegisterRequest,
)
from hse_doc_studio.infra.runner.backoff import Backoff
from hse_doc_studio.infra.runner.client import (
    RunnerApiError,
    RunnerClient,
    RunnerCommandRejected,
    RunnerUnreachable,
    StorageUnreachable,
)

from tests.unit.infra.runner.fake_runner_api import (
    RUNNER_TOKEN,
    TOKEN,
    FakeRunnerState,
    SwitchTransport,
    create_fake_app,
    envelope_body,
)


def _client(
    transport: SwitchTransport, token: str = TOKEN, retries: int = 3, *, registered: bool = False
) -> RunnerClient:
    client = RunnerClient(
        "http://api",
        token,
        version="0.1",
        transport=transport,
        retries=retries,
        backoff_factory=lambda: Backoff(base_s=0.001, cap_s=0.005),
    )
    if registered:
        client.restore("runner-1", RUNNER_TOKEN)
    return client


@pytest.fixture
def state() -> FakeRunnerState:
    return FakeRunnerState()


@pytest.fixture
def transport(state: FakeRunnerState) -> SwitchTransport:
    return SwitchTransport(create_fake_app(state))


_REGISTER = RunnerRegisterRequest(name="r", protocol=1, version="0.1", tags=frozenset({"tex"}), concurrency=2)


async def test_register_then_poll_returns_envelope(state: FakeRunnerState, transport: SwitchTransport) -> None:
    client = _client(transport)
    registered = await client.register(_REGISTER)
    state.enqueue(envelope_body("compile", job_id="11111111-1111-4111-8111-111111111111"))
    polled = await client.poll(PollRequest(wait_s=1, free_slots=2))
    await client.aclose()

    assert registered.runner_id == "runner-1"
    assert polled.envelope is not None
    assert str(polled.envelope.spec.id) == "11111111-1111-4111-8111-111111111111"
    headers = state.headers_seen[-1]
    assert headers["authorization"] == f"Bearer {RUNNER_TOKEN}"
    assert headers["x-runner-version"] == "0.1"
    assert headers["x-runner-id"] == "runner-1"
    assert state.registrations[0]["tags"] == ["tex"]


async def test_empty_poll_returns_no_envelope(transport: SwitchTransport) -> None:
    client = _client(transport, registered=True)
    assert (await client.poll(PollRequest(wait_s=0))).envelope is None
    await client.aclose()


async def test_bad_token_is_api_error_with_code(transport: SwitchTransport) -> None:
    client = _client(transport, token="wrong")
    with pytest.raises(RunnerApiError) as caught:
        await client.register(_REGISTER)
    await client.aclose()
    assert caught.value.status == 401
    assert caught.value.code == "runner_unauthorized"


async def test_transient_failures_are_retried(state: FakeRunnerState, transport: SwitchTransport) -> None:
    client = _client(transport)
    transport.fail_next = 2
    transport.status_next = 1
    await client.register(_REGISTER)
    await client.aclose()
    assert transport.failures == 2
    assert transport.status_calls == 1
    assert len(state.registrations) == 1


async def test_exhausted_retries_raise_unreachable(transport: SwitchTransport) -> None:
    client = _client(transport, retries=2)
    transport.down = True
    with pytest.raises(RunnerUnreachable):
        await client.register(_REGISTER)
    await client.aclose()
    assert transport.failures == 3


async def test_poll_is_not_retried_by_client(transport: SwitchTransport) -> None:
    client = _client(transport, registered=True)
    transport.down = True
    with pytest.raises(RunnerUnreachable):
        await client.poll(PollRequest(wait_s=0))
    await client.aclose()
    assert transport.failures == 1


async def test_job_calls_carry_job_token_and_stale_attempt_is_409(
    state: FakeRunnerState, transport: SwitchTransport
) -> None:
    client = _client(transport, registered=True)
    job = state.enqueue(envelope_body("compile", attempt=1))
    ref = ArtifactRef(path="out/main.pdf", sha256="a" * 64, size=3)
    slot = await client.announce_artifact(job.job_id, "jt", ArtifactUploadRequest(attempt=1, artifact=ref))
    await client.put_artifact(job.job_id, "jt", ref.sha256, b"pdf")
    assert slot.url is None
    assert job.artifacts[ref.sha256] == b"pdf"
    assert state.headers_seen[-1]["x-job-token"] == "jt"

    job.stale = True
    with pytest.raises(RunnerApiError) as caught:
        await client.complete(
            job.job_id, "jt", CompleteRequest(attempt=1, result=encode_result(JobResult(status=JobStatus.cancelled)))
        )
    await client.aclose()
    assert caught.value.code == "stale_attempt"


async def test_finishing_a_job_outlasts_an_api_restart(state: FakeRunnerState, transport: SwitchTransport) -> None:
    """Выкатка api (Recreate, одна реплика): несколько секунд отказов и 503, а готовый PDF не теряется."""
    client = _client(transport, registered=True)
    job = state.enqueue(envelope_body("compile", attempt=1))
    ref = ArtifactRef(path="out/main.pdf", sha256="a" * 64, size=3)

    transport.fail_next, transport.status_next = 4, 2
    await client.announce_artifact(job.job_id, "jt", ArtifactUploadRequest(attempt=1, artifact=ref))
    transport.fail_next = 6
    await client.put_artifact(job.job_id, "jt", ref.sha256, b"pdf")
    transport.fail_next = 8
    await client.complete(
        job.job_id, "jt", CompleteRequest(attempt=1, result=encode_result(JobResult(status=JobStatus.succeeded)))
    )
    await client.aclose()

    assert job.artifacts[ref.sha256] == b"pdf"
    assert transport.failures == 18


def test_backoff_grows_caps_and_resets() -> None:
    backoff = Backoff(base_s=1.0, cap_s=5.0, jitter=0.0)
    assert [backoff.next() for _ in range(5)] == [1.0, 2.0, 4.0, 5.0, 5.0]
    backoff.reset()
    assert backoff.next() == 1.0


async def test_put_to_url_connect_error_names_the_storage_origin_without_the_signature(
    transport: SwitchTransport,
) -> None:
    client = _client(transport, registered=True)
    transport.unroutable_hosts.add("minio.tech.svc")

    with pytest.raises(StorageUnreachable) as caught:
        await client.put_to_url("http://minio.tech.svc:80/studio/k?X-Amz-Signature=deadbeef", b"pdf")
    await client.aclose()

    message = str(caught.value)
    assert caught.value.origin == "http://minio.tech.svc:80"
    assert "HSE_STUDIO__S3__PUBLIC_ENDPOINT" in message
    assert "HSE_STUDIO__S3__OUTSIDE_RUNNER_ACCESS=proxy" in message
    assert "deadbeef" not in message
    assert isinstance(caught.value, RunnerUnreachable)


async def test_put_to_url_server_error_is_not_a_storage_reachability_problem(transport: SwitchTransport) -> None:
    client = _client(transport, registered=True)

    with pytest.raises(RunnerApiError):
        await client.put_to_url("http://testserver/nope", b"pdf")
    await client.aclose()


_FIXTURES = Path(__file__).resolve().parents[6] / "contracts" / "runner" / "fixtures"
_COMMAND = "7d3f1a2b-4c5d-4e6f-8a9b-0c1d2e3f4a5b"


def _fixture(schema: str, name: str) -> dict[str, object]:
    return json.loads((_FIXTURES / schema / f"{name}.json").read_text(encoding="utf-8"))


async def test_control_poll_decodes_the_command_and_is_not_retried(
    state: FakeRunnerState, transport: SwitchTransport
) -> None:
    client = _client(transport, registered=True)
    state.commands.append(_fixture("ControlPollResponseBody", "cleanup")["command"])  # type: ignore[arg-type]

    polled = await client.control_poll(ControlPollRequest(wait_s=0))
    empty = await client.control_poll(ControlPollRequest(wait_s=0))
    transport.down = True
    with pytest.raises(RunnerUnreachable):
        await client.control_poll(ControlPollRequest(wait_s=0))
    await client.aclose()

    assert polled.command is not None
    assert polled.command.id == UUID(_COMMAND)
    assert isinstance(polled.command.payload, DiskCleanupPayload)
    assert DiskTarget.runner_cache in polled.command.payload.targets
    assert empty.command is None
    assert transport.failures == 1


async def test_control_poll_unknown_command_is_rejected_with_its_id(
    state: FakeRunnerState, transport: SwitchTransport
) -> None:
    client = _client(transport, registered=True)
    state.commands.append({"id": _COMMAND, "kind": "node.reboot", "payload": {}, "issued_at": "2026-11-11T09:31:00Z"})

    with pytest.raises(RunnerCommandRejected) as caught:
        await client.control_poll(ControlPollRequest(wait_s=0))
    await client.aclose()

    assert caught.value.command_id == UUID(_COMMAND)


async def test_command_progress_returns_cancel_and_the_result_is_retried(
    state: FakeRunnerState, transport: SwitchTransport
) -> None:
    client = _client(transport, registered=True)
    state.cancel_commands.add(_COMMAND)
    running = CommandProgressRequest(RunnerCommandState.running, CommandProgress(steps=(), freed_bytes=0, error=None))
    done = CommandProgressRequest(RunnerCommandState.done, CommandProgress(steps=(), freed_bytes=0, error=None))

    reply = await client.command_progress(UUID(_COMMAND), running)
    state.progress_unavailable = 1
    with pytest.raises(RunnerUnreachable):
        await client.command_progress(UUID(_COMMAND), running)
    state.progress_unavailable = 5
    await client.command_progress(UUID(_COMMAND), done, final=True)
    state.progress_errors[_COMMAND] = (409, "command_finished")
    with pytest.raises(RunnerApiError) as caught:
        await client.command_progress(UUID(_COMMAND), done, final=True)
    await client.aclose()

    assert reply.cancel is True
    assert [entry["state"] for entry in state.progress[_COMMAND]] == ["running", "done"]
    assert caught.value.code == "command_finished"


async def test_report_disk_posts_the_contract_body(state: FakeRunnerState, transport: SwitchTransport) -> None:
    client = _client(transport, registered=True)
    report = decode(RunnerDiskReport, _fixture("RunnerDiskReportBody", "docker"))

    await client.report_disk(report)
    await client.aclose()

    (posted,) = state.disks
    assert decode(RunnerDiskReport, posted) == report
