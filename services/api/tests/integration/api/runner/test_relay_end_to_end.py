"""Ретрансляция целиком в одном процессе: api, настоящий цикл раннера, поддельная модель и OpenAI SDK.

Маршруты раннера настоящие, раннер ходит в них через ASGI-транспорт, модель в «сети раннера» отвечает только
ему (MockTransport исполнителя), у api к ней доступа нет. `/announce` здесь заглушка: его ручку делает трек core.
"""

from __future__ import annotations

import asyncio
import dataclasses
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from fastapi import FastAPI
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.guards import install_exception_handlers
from hse_doc_studio.api.routers.server_routers import include_server_routers
from hse_doc_studio.api.schemas.runner import RunnerAnnounceRequestBody
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.agent.entities import AgentMessage
from hse_doc_studio.core.entities import AIProvider
from hse_doc_studio.core.enums import AIProviderType
from hse_doc_studio.core.jobs.enums import JobState
from hse_doc_studio.core.jobs.relay import AiEndpointFlavor, RelayErrorCode
from hse_doc_studio.core.jobs.runners import DeclaredAiEndpoint, JobTokenSigner, RunnerHostKind
from hse_doc_studio.core.jobs.wire import RUNNER_PROTOCOL_VERSION, SERVER_FEATURES
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.infra.ai.agent.sdk_agent_provider import SdkAgentProvider
from hse_doc_studio.infra.ai.sdk_model_lister import SdkAIModelLister
from hse_doc_studio.infra.jobs.relay_hub import RelayHub
from hse_doc_studio.infra.jobs.storage_fs import FsJobBlobStore, FsJobLogSink, FsJobOutputIngest
from hse_doc_studio.infra.runner.backoff import Backoff
from hse_doc_studio.infra.runner.client import RunnerClient
from hse_doc_studio.infra.runner.compile_executor import RoutingJobExecutor
from hse_doc_studio.infra.runner.loop import RunnerLoop, RunnerLoopConfig
from hse_doc_studio.infra.runner.relay_executor import AiEndpoint, AiRelayExecutor
from hse_doc_studio.use_cases.ai_relay.client import AiRelayClient, AiRelayError, RelayLimits, relay_error_of
from hse_doc_studio.use_cases.ai_relay.request_store import RelayRequestStore
from hse_doc_studio.use_cases.ai_relay.runner_side import RelayRunnerService
from hse_doc_studio.use_cases.jobs.queue_service import JobQueueService
from hse_doc_studio.use_cases.jobs.runner_io import RunnerJobIoService
from hse_doc_studio.use_cases.jobs.runner_jobs import RunnerJobService
from hse_doc_studio.use_cases.jobs.runners import RunnerRegistry
from hse_doc_studio.use_cases.jobs.terminal import JobTerminalBroadcaster
from hse_doc_studio.use_cases.jobs.wakeup import JobWakeup

from tests.fakes.auth import InMemoryAuditLog
from tests.fakes.job_queue import InMemoryJobQueue
from tests.fakes.runners import InMemoryRegistrationTokenRepository, InMemoryRunnerRepository
from tests.fixtures.actors import as_actor
from tests.unit.infra.runner.fake_openai import FakeOpenAI
from tests.unit.infra.runner.test_runner_loop import FakeExecutor
from tests.unit.use_cases.ai_relay.helpers import OWNER_ID, make_personal_runner

_ADMIN = Actor(kind="user", id="admin", is_instance_admin=True)
_ANNA = Actor.user(OWNER_ID, "Анна")


class _Uow:
    @asynccontextmanager
    async def begin(self) -> AsyncIterator[None]:
        yield


@dataclass
class _Sink:
    deltas: list[tuple[float, str]] = field(default_factory=list)

    def on_text_delta(self, text: str) -> None:
        self.deltas.append((time.monotonic(), text))

    def on_tool_call_start(self, index: int, call_id: str, name: str) -> None:
        return None

    def on_tool_call_args_delta(self, index: int, args_fragment: str) -> None:
        return None


@dataclass
class _Stack:
    api: httpx.AsyncClient
    queue: InMemoryJobQueue
    relay: AiRelayClient
    model: FakeOpenAI
    loop: RunnerLoop
    runner_client: RunnerClient
    provider: AIProvider
    task: asyncio.Task[None] | None = None

    def start_runner(self) -> None:
        self.task = asyncio.create_task(self.loop.run())

    async def stop_runner(self) -> None:
        if self.task is None:
            return
        self.loop.request_stop()
        await asyncio.wait_for(self.task, 10)
        self.task = None


@pytest_asyncio.fixture
async def stack(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AsyncIterator[_Stack]:
    monkeypatch.setattr(settings, "mode", StudioMode.server)
    queue = InMemoryJobQueue()
    runners = InMemoryRunnerRepository()
    registry = RunnerRegistry(runners, InMemoryRegistrationTokenRepository(), InMemoryAuditLog(), _Uow())
    signer = JobTokenSigner([b"k" * 32])
    hub = RelayHub()
    terminal = JobTerminalBroadcaster()
    terminal.add(hub)
    wakeup = JobWakeup()
    service = JobQueueService(queue, terminal=terminal, wakeup=wakeup)
    poll = RunnerJobService(queue, service, runners, signer, wakeup, lease_s=45.0, timeout_grace_s=15.0)
    io = RunnerJobIoService(
        queue,
        service,
        runners,
        signer,
        FsJobBlobStore(tmp_path),
        FsJobOutputIngest(tmp_path, max_bytes=1000),
        FsJobLogSink(tmp_path, max_bytes=1000),
    )
    store = RelayRequestStore()
    relay = AiRelayClient(queue, service, runners, hub, store, wakeup, limits=RelayLimits(pickup_s=1.5))
    side = RelayRunnerService(io, store, hub)

    class _Provider(Provider):
        scope = Scope.APP

        @provide
        def registry_(self) -> RunnerRegistry:
            return registry

        @provide
        def poll_(self) -> RunnerJobService:
            return poll

        @provide
        def io_(self) -> RunnerJobIoService:
            return io

        @provide
        def side_(self) -> RelayRunnerService:
            return side

    app = FastAPI()

    @app.post("/api/runner/v1/announce")
    async def announce(body: RunnerAnnounceRequestBody) -> dict[str, object]:
        # Заглушка ручки трека core: пересечение возможностей, раннер личный.
        return {
            "runner_id": "x",
            "server_features": sorted(set(body.features) & SERVER_FEATURES),
            "owner_kind": "user",
            "paused": False,
            "relay_keepalive_s": 2,
        }

    include_server_routers(app)
    install_exception_handlers(app)
    container = make_async_container(_Provider(), FastapiProvider())
    setup_dishka(container, app)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://api") as api:
        created = await registry.create_registration_token(_ADMIN)
        registered = (
            await api.post(
                "/api/runner/v1/register",
                json={
                    "name": "MacBook",
                    "protocol": RUNNER_PROTOCOL_VERSION,
                    "version": "0.3.0",
                    "tags": ["ai"],
                    "concurrency": 1,
                    "resource_class": "standard",
                },
                headers={"Authorization": f"Bearer {created.secret}"},
            )
        ).json()
        record = await runners.get(registered["runner_id"])
        assert record is not None
        personal = make_personal_runner(record.id, last_seen_at=datetime.now(UTC))
        await runners.add(dataclasses.replace(personal, token_hash=record.token_hash))

        model = FakeOpenAI(mode="slow", delay_s=0.25)
        runner_client = RunnerClient(
            "http://api",
            "",
            version="0.3.0",
            transport=transport,
            retries=1,
            backoff_factory=lambda: Backoff(base_s=0.01, cap_s=0.05),
        )
        runner_client.restore(registered["runner_id"], registered["runner_token"])
        executor = AiRelayExecutor(
            runner_client,
            (AiEndpoint("ollama", "http://localhost:11434/v1", AiEndpointFlavor.ollama),),
            max_response_bytes=10**6,
            transport=model.transport(),
        )
        loop = RunnerLoop(
            runner_client,
            RoutingJobExecutor(FakeExecutor(), FakeExecutor(), executor),
            RunnerLoopConfig(
                name="MacBook",
                version="0.3.0",
                poll_wait_s=1,
                heartbeat_s=0.2,
                drain_timeout_s=2.0,
                backoff_factory=lambda: Backoff(base_s=0.01, cap_s=0.05, jitter=0.0),
                ai_concurrency=2,
                host_kind=RunnerHostKind.desktop,
                ai_endpoints=(DeclaredAiEndpoint("ollama", AiEndpointFlavor.ollama),),
            ),
        )
        provider = AIProvider(
            id=uuid4(),
            name="Ollama на ноутбуке",
            type=AIProviderType.runner,
            api_key="",
            base_url="",
            models=["fake-model"],
            created_at=datetime.now(UTC),
            request_timeout_s=5.0,
            runner_id=record.id,
            runner_endpoint="ollama",
        )
        built = _Stack(api, queue, relay, model, loop, runner_client, provider)
        yield built
        await built.stop_runner()
        await runner_client.aclose()
    await container.close()


async def _turn(stack: _Stack, sink: _Sink, cancel: asyncio.Event):  # type: ignore[no-untyped-def]
    with as_actor(_ANNA):
        return await SdkAgentProvider(relay=stack.relay).run_turn(
            provider=stack.provider,
            model="fake-model",
            messages=[AgentMessage(role="user", content="Привет")],
            tools=[],
            system=None,
            tool_choice_allowed=False,
            max_output_tokens=256,
            temperature=0.0,
            sink=sink,
            cancel=cancel,
        )


async def test__chat_turn__tokens_stream_through_the_runner_before_the_answer_ends(stack: _Stack) -> None:
    stack.start_runner()
    sink = _Sink()

    started = time.monotonic()
    turn = await _turn(stack, sink, asyncio.Event())
    finished = time.monotonic()

    assert turn.text == "Привет, мир"
    assert [text for _, text in sink.deltas] == ["Привет", ", ", "мир"]
    # Первая дельта пришла раньше конца ответа: поток идёт порциями, а не одним куском в конце.
    assert sink.deltas[0][0] - started < finished - started - 0.3
    async with asyncio.timeout(5):
        while not (await stack.queue.list())[0].state.is_terminal:
            await asyncio.sleep(0.02)
    (job,) = await stack.queue.list()
    assert job.state is JobState.succeeded
    assert job.result is not None
    assert job.result["data"]["status_code"] == 200
    request = stack.model.requests[0]
    assert request.url.path == "/v1/chat/completions"
    assert "authorization" not in request.headers


async def test__models__listed_through_the_runner(stack: _Stack) -> None:
    stack.start_runner()

    with as_actor(_ANNA):
        models = await SdkAIModelLister(stack.relay).list_models(stack.provider)

    assert models == ["fake-model"]


async def test__chat_cancel__closes_the_model_connection_within_seconds(stack: _Stack) -> None:
    stack.model.tokens = [f"t{i}" for i in range(40)]
    stack.start_runner()
    sink = _Sink()
    cancel = asyncio.Event()
    turn_task = asyncio.create_task(_turn(stack, sink, cancel))
    async with asyncio.timeout(10):
        while not sink.deltas:
            await asyncio.sleep(0.02)

    cancel.set()
    await asyncio.wait_for(turn_task, 5)
    cancelled_at = time.monotonic()
    async with asyncio.timeout(3):
        while stack.model.closed < 1:
            await asyncio.sleep(0.02)

    assert time.monotonic() - cancelled_at <= 3
    assert stack.model.sent_chunks < 40
    async with asyncio.timeout(5):
        while not (await stack.queue.list())[0].state.is_terminal:
            await asyncio.sleep(0.05)


async def test__runner_stopped__pickup_timeout_gives_relay_unavailable(stack: _Stack) -> None:
    with as_actor(_ANNA), pytest.raises(Exception) as caught:  # noqa: PT011 — SDK оборачивает транспортную ошибку
        await SdkAIModelLister(stack.relay).list_models(stack.provider)

    error = relay_error_of(caught.value)
    assert isinstance(error, AiRelayError)
    assert error.code is RelayErrorCode.relay_unavailable
    (job,) = await stack.queue.list()
    assert job.state is JobState.cancelled
