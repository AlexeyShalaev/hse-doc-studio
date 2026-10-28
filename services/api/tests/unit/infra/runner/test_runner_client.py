from __future__ import annotations

import pytest
from hse_doc_studio.core.jobs.codec import encode_result
from hse_doc_studio.core.jobs.entities import JobResult
from hse_doc_studio.core.jobs.enums import JobStatus
from hse_doc_studio.core.jobs.files import ArtifactRef
from hse_doc_studio.core.jobs.wire import (
    ArtifactUploadRequest,
    CompleteRequest,
    PollRequest,
    RunnerRegisterRequest,
)
from hse_doc_studio.infra.runner.backoff import Backoff
from hse_doc_studio.infra.runner.client import RunnerApiError, RunnerClient, RunnerUnreachable

from tests.unit.infra.runner.fake_runner_api import (
    TOKEN,
    FakeRunnerState,
    SwitchTransport,
    create_fake_app,
    envelope_body,
)


def _client(transport: SwitchTransport, token: str = TOKEN, retries: int = 3) -> RunnerClient:
    return RunnerClient(
        "http://api",
        token,
        version="0.1",
        transport=transport,
        retries=retries,
        backoff_factory=lambda: Backoff(base_s=0.001, cap_s=0.005),
    )


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
    assert headers["authorization"] == f"Bearer {TOKEN}"
    assert headers["x-runner-version"] == "0.1"
    assert headers["x-runner-id"] == "runner-1"
    assert state.registrations[0]["tags"] == ["tex"]


async def test_empty_poll_returns_no_envelope(transport: SwitchTransport) -> None:
    client = _client(transport)
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
    client = _client(transport)
    transport.down = True
    with pytest.raises(RunnerUnreachable):
        await client.poll(PollRequest(wait_s=0))
    await client.aclose()
    assert transport.failures == 1


async def test_job_calls_carry_job_token_and_stale_attempt_is_409(
    state: FakeRunnerState, transport: SwitchTransport
) -> None:
    client = _client(transport)
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


def test_backoff_grows_caps_and_resets() -> None:
    backoff = Backoff(base_s=1.0, cap_s=5.0, jitter=0.0)
    assert [backoff.next() for _ in range(5)] == [1.0, 2.0, 4.0, 5.0, 5.0]
    backoff.reset()
    assert backoff.next() == 1.0
