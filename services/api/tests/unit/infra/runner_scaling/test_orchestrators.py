"""Оркестраторы раннеров: подпись webhook, ошибки сети и кода ответа, команда docker compose."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime

import httpx
import pytest
from hse_doc_studio.api.config.autoscale import AutoscaleConfig
from hse_doc_studio.core.jobs.autoscale import (
    AutoscaleMode,
    AutoscalePolicy,
    OrchestratorError,
    QueueMetrics,
    ScaleRequest,
)
from hse_doc_studio.infra.runner_scaling.compose import ComposeOrchestrator
from hse_doc_studio.infra.runner_scaling.factory import OrchestratorFactory
from hse_doc_studio.infra.runner_scaling.webhook import SIGNATURE_HEADER, WebhookOrchestrator
from pydantic import SecretStr

REQUEST = ScaleRequest(
    4, 2, "queue_depth", QueueMetrics(queued=9, runners_online=2, slots_total=4), datetime(2026, 11, 10, tzinfo=UTC)
)


def _client(handler) -> object:  # type: ignore[no-untyped-def]
    return lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test__webhook__posts_signed_json_body() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(202)

    await WebhookOrchestrator("https://orch.example/scale", "s3cret", _client(handler)).scale_to(REQUEST)  # type: ignore[arg-type]

    (request,) = seen
    body = json.loads(request.content)
    assert (body["event"], body["desired"], body["current"], body["reason"]) == ("scale", 4, 2, "queue_depth")
    assert body["metrics"]["queued"] == 9
    expected = "sha256=" + hmac.new(b"s3cret", request.content, hashlib.sha256).hexdigest()
    assert request.headers[SIGNATURE_HEADER] == expected


async def test__webhook__without_secret_sends_no_signature() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    await WebhookOrchestrator("https://orch.example/scale", None, _client(handler)).scale_to(REQUEST)  # type: ignore[arg-type]

    assert SIGNATURE_HEADER not in seen[0].headers


async def test__webhook__error_status_and_network_failure_are_orchestrator_errors() -> None:
    def refuse(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    def broken(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    with pytest.raises(OrchestratorError, match="503"):
        await WebhookOrchestrator("https://o/s", None, _client(refuse)).scale_to(REQUEST)  # type: ignore[arg-type]
    with pytest.raises(OrchestratorError, match="unreachable"):
        await WebhookOrchestrator("https://o/s", None, _client(broken)).scale_to(REQUEST)  # type: ignore[arg-type]


class _Commands:
    def __init__(self, code: int = 0, output: str = "") -> None:
        self.calls: list[list[str]] = []
        self.code = code
        self.output = output

    async def __call__(self, argv: object, timeout_s: float) -> tuple[int, str]:
        self.calls.append(list(argv))  # type: ignore[call-overload]
        return self.code, self.output


async def test__compose__scales_one_service_without_recreating_or_touching_dependencies() -> None:
    run = _Commands()
    orchestrator = ComposeOrchestrator("runner", project="studio", compose_file="/srv/compose.yml", runner=run)

    await orchestrator.scale_to(REQUEST)

    assert run.calls == [
        [
            "docker",
            "compose",
            "-p",
            "studio",
            "-f",
            "/srv/compose.yml",
            "up",
            "-d",
            "--no-recreate",
            "--no-deps",
            "--scale",
            "runner=4",
            "runner",
        ]
    ]


async def test__compose__failure_carries_exit_code_and_output_tail() -> None:
    with pytest.raises(OrchestratorError, match="exited with 1.*no such service"):
        await ComposeOrchestrator("runner", runner=_Commands(1, "no such service")).scale_to(REQUEST)


async def test__compose__current_counts_running_containers() -> None:
    assert await ComposeOrchestrator("runner", runner=_Commands(0, "abc\ndef\n\n")).current() == 2
    assert await ComposeOrchestrator("runner", runner=_Commands(1, "boom")).current() is None


def test__factory__picks_adapter_by_mode_and_off_gives_none() -> None:
    factory = OrchestratorFactory(AutoscaleConfig(webhook_secret=SecretStr("x")), lambda: httpx.AsyncClient())

    assert factory.create(AutoscalePolicy()) is None
    assert isinstance(factory.create(AutoscalePolicy(mode=AutoscaleMode.compose)), ComposeOrchestrator)
    hook = factory.create(AutoscalePolicy(mode=AutoscaleMode.webhook, webhook_url="https://o/s"))
    assert isinstance(hook, WebhookOrchestrator)
