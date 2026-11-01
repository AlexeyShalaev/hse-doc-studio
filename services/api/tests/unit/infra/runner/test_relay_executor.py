"""Исполнитель ai.relay в цикле раннера против поддельного api и поддельной модели."""

from __future__ import annotations

import asyncio
import base64
import hashlib
from typing import Any

import pytest
from hse_doc_studio.core.jobs.codec import decode_envelope
from hse_doc_studio.core.jobs.relay import AiEndpointFlavor
from hse_doc_studio.core.jobs.runners import DeclaredAiEndpoint, RunnerHostKind
from hse_doc_studio.infra.runner.backoff import Backoff
from hse_doc_studio.infra.runner.client import RunnerClient
from hse_doc_studio.infra.runner.compile_executor import RoutingJobExecutor
from hse_doc_studio.infra.runner.loop import RunnerLoop, RunnerLoopConfig
from hse_doc_studio.infra.runner.relay_executor import AiEndpoint, AiRelayExecutor, relay_url

from tests.unit.infra.runner.fake_openai import FakeOpenAI
from tests.unit.infra.runner.fake_runner_api import (
    TOKEN,
    FakeJob,
    FakeRunnerState,
    SwitchTransport,
    create_fake_app,
    envelope_body,
)
from tests.unit.infra.runner.test_runner_loop import JOB_B, FakeExecutor, until

_BODY = b'{"model":"fake-model","stream":true,"messages":[]}'
_ENDPOINT = AiEndpoint("ollama", "http://localhost:11434/v1", AiEndpointFlavor.ollama, api_key=lambda: "sk-local")


def relay_envelope(*, path: str = "chat/completions", method: str = "POST", body: bytes = _BODY) -> dict[str, Any]:
    envelope = envelope_body("relay", job_id=JOB_B)
    payload = envelope["spec"]["payload"]
    payload.update(path=path, method=method, head_timeout_s=1.0, idle_timeout_s=1.0)
    if method == "GET":
        payload.update(content_type=None, body_sha256=None, body_size=0)
    else:
        payload.update(body_sha256=hashlib.sha256(body).hexdigest(), body_size=len(body))
    return envelope


class Rig:
    def __init__(self, model: FakeOpenAI, *, endpoints: tuple[AiEndpoint, ...] = (_ENDPOINT,), max_bytes: int = 10**6):
        self.state = FakeRunnerState()
        self.model = model
        self.client = RunnerClient(
            "http://api",
            TOKEN,
            version="0.3",
            transport=SwitchTransport(create_fake_app(self.state)),
            retries=1,
            backoff_factory=lambda: Backoff(base_s=0.001, cap_s=0.005),
        )
        relay = AiRelayExecutor(self.client, endpoints, max_response_bytes=max_bytes, transport=model.transport())
        self.loop = RunnerLoop(
            self.client,
            RoutingJobExecutor(FakeExecutor(), FakeExecutor(), relay),
            RunnerLoopConfig(
                name="MacBook",
                version="0.3",
                poll_wait_s=0,
                heartbeat_s=0.05,
                log_flush_s=0.02,
                drain_timeout_s=2.0,
                backoff_factory=lambda: Backoff(base_s=0.01, cap_s=0.05, jitter=0.0),
                ai_concurrency=2,
                host_kind=RunnerHostKind.cli,
                ai_endpoints=(DeclaredAiEndpoint("ollama", AiEndpointFlavor.ollama),),
            ),
        )
        self.task: asyncio.Task[None] | None = None

    def enqueue(self, envelope: dict[str, Any], body: bytes = _BODY) -> FakeJob:
        job = self.state.enqueue(envelope)
        job.relay_body = body
        return job

    async def run_until_done(self, job: FakeJob) -> dict[str, Any]:
        self.task = asyncio.create_task(self.loop.run())
        await until(lambda: job.completed)
        self.loop.request_stop()
        await asyncio.wait_for(self.task, 10)
        await self.client.aclose()
        return job.completed[-1]["result"]


def _events(job: FakeJob) -> list[dict[str, Any]]:
    return [event for batch in job.relay_batches for event in batch["events"]]


def _payload(job: FakeJob) -> bytes:
    return b"".join(base64.b64decode(e["data"]) for e in _events(job) if e["kind"] == "data")


async def test__relay__streams_the_model_answer_and_reports_success() -> None:
    model = FakeOpenAI()
    rig = Rig(model)
    job = rig.enqueue(relay_envelope())

    result = await rig.run_until_done(job)

    kinds = [event["kind"] for event in _events(job)]
    assert kinds[0] == "head"
    assert kinds[-1] == "end"
    assert _events(job)[0]["status"] == 200
    assert b"data: [DONE]" in _payload(job)
    assert [batch["seq"] for batch in job.relay_batches] == list(range(len(job.relay_batches)))
    assert result["status"] == "succeeded"
    assert result["data"]["status_code"] == 200
    assert result["data"]["bytes_out"] == len(_payload(job))
    (request,) = model.requests
    assert str(request.url) == "http://localhost:11434/v1/chat/completions"
    assert model.bodies == [_BODY]
    assert request.headers["authorization"] == "Bearer sk-local"
    assert request.headers["accept"] == "text/event-stream"
    assert "x-job-token" not in request.headers


async def test__relay__get_models_sends_no_body() -> None:
    model = FakeOpenAI()
    rig = Rig(model)
    job = rig.enqueue(relay_envelope(path="models", method="GET"), body=b"")

    result = await rig.run_until_done(job)

    assert result["status"] == "succeeded"
    assert b"fake-model" in _payload(job)
    assert model.bodies == [b""]


async def test__relay__unknown_endpoint__failed_endpoint_unknown() -> None:
    model = FakeOpenAI()
    rig = Rig(model, endpoints=())
    job = rig.enqueue(relay_envelope())

    result = await rig.run_until_done(job)

    assert result["status"] == "failed"
    assert result["error"]["code"] == "endpoint_unknown"
    assert model.requests == []


async def test__relay__model_down__error_event_and_failed() -> None:
    rig = Rig(FakeOpenAI(mode="down"))
    job = rig.enqueue(relay_envelope())

    result = await rig.run_until_done(job)

    assert _events(job)[-1] == {
        "kind": "error",
        "status": None,
        "content_type": None,
        "data": None,
        "code": "upstream_unreachable",
    }
    assert result["error"]["code"] == "upstream_unreachable"


async def test__relay__no_head_in_time__upstream_timeout() -> None:
    rig = Rig(FakeOpenAI(mode="hang"))
    job = rig.enqueue(relay_envelope())

    result = await rig.run_until_done(job)

    assert result["error"]["code"] == "upstream_timeout"


async def test__relay__http_500_is_forwarded_as_is() -> None:
    rig = Rig(FakeOpenAI(mode="error500"))
    job = rig.enqueue(relay_envelope())

    result = await rig.run_until_done(job)

    assert _events(job)[0]["status"] == 500
    assert result["status"] == "succeeded"
    assert result["data"]["status_code"] == 500


async def test__relay__redirect_is_not_followed() -> None:
    model = FakeOpenAI(mode="redirect")
    rig = Rig(model)
    job = rig.enqueue(relay_envelope())

    await rig.run_until_done(job)

    assert len(model.requests) == 1
    assert _events(job)[0]["status"] == 302


async def test__relay__answer_over_the_runner_limit__response_too_large() -> None:
    model = FakeOpenAI(mode="huge")
    rig = Rig(model, max_bytes=100_000)
    job = rig.enqueue(relay_envelope())

    result = await rig.run_until_done(job)

    assert result["error"]["code"] == "response_too_large"
    assert model.closed == 1


async def test__relay__cancel_in_ack__closes_the_model_connection() -> None:
    model = FakeOpenAI(mode="slow", tokens=[f"t{i}" for i in range(50)], delay_s=0.05)
    rig = Rig(model)
    job = rig.enqueue(relay_envelope())
    job.relay_cancel = True

    result = await rig.run_until_done(job)

    assert result["status"] == "cancelled"
    assert model.closed == 1
    assert model.sent_chunks < 50


async def test__relay__cancel_in_the_ack_of_end__still_succeeded() -> None:
    rig = Rig(FakeOpenAI())
    job = rig.enqueue(relay_envelope())
    job.relay_cancel_on_end = True

    result = await rig.run_until_done(job)

    assert _events(job)[-1]["kind"] == "end"
    assert result["status"] == "succeeded"


async def test__relay__cancel_by_heartbeat_before_any_batch() -> None:
    model = FakeOpenAI(mode="hang")
    rig = Rig(model)
    envelope = relay_envelope()
    envelope["spec"]["payload"]["head_timeout_s"] = 30.0
    job = rig.enqueue(envelope)
    job.cancel = True

    result = await rig.run_until_done(job)

    assert result["status"] == "cancelled"


async def test__relay__body_hash_mismatch__refuses_to_send() -> None:
    model = FakeOpenAI()
    rig = Rig(model)
    job = rig.enqueue(relay_envelope(), body=b'{"model":"other"}')

    result = await rig.run_until_done(job)

    assert result["error"]["code"] == "relay_unavailable"
    assert model.requests == []


@pytest.mark.parametrize("path", ["../admin", "models/../../x", "//evil.host/v1", "models?key=1", "http://x/y"])
def test__relay_url__rejects_paths_that_escape_the_endpoint(path: str) -> None:
    with pytest.raises(ValueError, match="not allowed|escapes"):
        relay_url("http://localhost:11434/v1", path)


def test__envelope__path_outside_the_whitelist_is_not_even_decoded() -> None:
    envelope = relay_envelope()
    envelope["spec"]["payload"]["path"] = "../admin"

    with pytest.raises(ValueError, match="admin"):
        decode_envelope(envelope)
