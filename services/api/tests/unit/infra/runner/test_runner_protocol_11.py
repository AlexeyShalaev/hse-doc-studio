"""Протокол раннера 1.1: согласование /announce, откат на старый сервер, слоты ИИ, шлюз, /offline, наблюдатель."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from hse_doc_studio.core.jobs.relay import AiEndpointFlavor
from hse_doc_studio.core.jobs.runners import DeclaredAiEndpoint, RunnerHostKind
from hse_doc_studio.core.jobs.wire import RunnerPairPollRequest, RunnerPairStartRequest
from hse_doc_studio.infra.di.containers.runner import RunnerConfigError, create_runner_container
from hse_doc_studio.infra.runner.backoff import Backoff
from hse_doc_studio.infra.runner.client import RunnerClient
from hse_doc_studio.infra.runner.config import RunnerConfig
from hse_doc_studio.infra.runner.identity import RunnerIdentityStore
from hse_doc_studio.infra.runner.loop import RunnerLoop, RunnerLoopConfig, RunnerLoopState
from pydantic import ValidationError

from tests.unit.infra.runner.fake_runner_api import (
    RUNNER_TOKEN,
    TOKEN,
    FakeRunnerState,
    SwitchTransport,
    create_fake_app,
    envelope_body,
)
from tests.unit.infra.runner.test_runner_loop import JOB_A, JOB_B, FakeExecutor, until

_OLLAMA = (DeclaredAiEndpoint("ollama", AiEndpointFlavor.ollama),)


class _Observer:
    def __init__(self) -> None:
        self.states: list[RunnerLoopState] = []
        self.jobs: list[tuple[str, str, str]] = []

    def on_state(self, state: RunnerLoopState, code: str | None = None) -> None:
        self.states.append(state)

    def on_job_started(self, job_id: str, kind: str) -> None:
        self.jobs.append(("started", job_id, kind))

    def on_job_finished(self, job_id: str, kind: str, status: str) -> None:
        self.jobs.append((status, job_id, kind))


class Rig:
    def __init__(self, *, ai: bool = True, gate: bool = True) -> None:
        self.state = FakeRunnerState()
        self.transport = SwitchTransport(create_fake_app(self.state))
        self.executor = FakeExecutor()
        self.observer = _Observer()
        self.gate_open = gate
        self.client = RunnerClient(
            "http://api",
            TOKEN,
            version="0.3",
            transport=self.transport,
            retries=1,
            backoff_factory=lambda: Backoff(base_s=0.001, cap_s=0.005),
        )
        self.loop = RunnerLoop(
            self.client,
            self.executor,
            RunnerLoopConfig(
                name="MacBook",
                version="0.3",
                tags=frozenset({"pack"}),
                concurrency=1,
                poll_wait_s=0,
                log_flush_s=0.02,
                heartbeat_s=0.02,
                drain_timeout_s=2.0,
                backoff_factory=lambda: Backoff(base_s=0.01, cap_s=0.05, jitter=0.0),
                ai_concurrency=2 if ai else 0,
                host_kind=RunnerHostKind.desktop,
                ai_endpoints=_OLLAMA if ai else (),
                gate=lambda: self.gate_open,
                gate_recheck_s=0.02,
            ),
            observer=self.observer,
        )
        self.task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self.task = asyncio.create_task(self.loop.run())

    async def stop(self) -> None:
        self.loop.request_stop()
        assert self.task is not None
        await asyncio.wait_for(self.task, 10)
        await self.client.aclose()


async def test__announce__negotiates_features_and_declares_ai_endpoints() -> None:
    rig = Rig()
    rig.start()
    await until(lambda: rig.state.polls > 0)
    await rig.stop()

    (announce,) = rig.state.announces
    assert announce["host_kind"] == "desktop"
    assert announce["ai_endpoints"] == [{"name": "ollama", "flavor": "ollama"}]
    assert set(announce["features"]) == {"announce", "offline", "ai_slots", "ai_relay"}
    assert "ai" in announce["tags"]
    assert rig.client.features == {"announce", "offline", "ai_slots", "ai_relay"}
    assert rig.state.poll_bodies[0]["free_ai_slots"] == 2
    assert rig.state.offline_calls == 1


async def test__announce__without_endpoints__no_relay_and_no_ai_tag() -> None:
    rig = Rig(ai=False)
    rig.start()
    await until(lambda: rig.state.polls > 0)
    await rig.stop()

    (announce,) = rig.state.announces
    assert set(announce["features"]) == {"announce", "offline"}
    assert announce["ai_concurrency"] == 0
    assert "ai" not in announce["tags"]
    assert "free_ai_slots" not in rig.state.poll_bodies[0]


async def test__old_server__404_on_announce__falls_back_to_protocol_one() -> None:
    rig = Rig()
    rig.state.supports_announce = False
    job = rig.state.enqueue(envelope_body("compile", job_id=JOB_A))
    rig.start()
    await until(lambda: job.completed)
    await rig.stop()

    assert rig.client.features == frozenset()
    assert all("free_ai_slots" not in body for body in rig.state.poll_bodies)
    assert all(body["free_slots"] >= 1 for body in rig.state.poll_bodies)
    assert rig.state.offline_calls == 0


async def test__ai_pool__relay_is_taken_while_a_build_holds_the_only_slot() -> None:
    rig = Rig()
    rig.executor.block = True
    build = rig.state.enqueue(envelope_body("compile", job_id=JOB_A))
    relay = rig.state.enqueue(envelope_body("relay", job_id=JOB_B))
    rig.start()
    await until(lambda: set(rig.executor.started) == {JOB_A, JOB_B})

    assert any(body["free_slots"] == 0 and body["free_ai_slots"] >= 1 for body in rig.state.poll_bodies)
    rig.executor.gate.set()
    await until(lambda: build.completed and relay.completed)
    await rig.stop()


async def test__gate_closed__builds_wait_but_relay_runs() -> None:
    rig = Rig(gate=False)
    build = rig.state.enqueue(envelope_body("compile", job_id=JOB_A))
    relay = rig.state.enqueue(envelope_body("relay", job_id=JOB_B))
    rig.start()
    await until(lambda: relay.completed)
    await asyncio.sleep(0.05)

    assert not build.completed
    assert all(body["free_slots"] == 0 for body in rig.state.poll_bodies)
    rig.gate_open = True
    await until(lambda: build.completed)
    await rig.stop()


async def test__gate_closed_without_ai__does_not_poll() -> None:
    rig = Rig(ai=False, gate=False)
    rig.start()
    await asyncio.sleep(0.1)
    await rig.stop()

    assert rig.state.polls == 0


async def test__relay_job__heartbeats_at_the_keepalive_rate() -> None:
    rig = Rig()
    rig.executor.block = True
    relay = rig.state.enqueue(envelope_body("relay", job_id=JOB_B))
    rig.start()
    await until(lambda: relay.heartbeats >= 2)
    relay.cancel = True
    await until(lambda: relay.completed)
    await rig.stop()

    assert relay.completed[-1]["result"]["status"] == "cancelled"


async def test__observer__sees_registering_online_jobs_and_stopped() -> None:
    rig = Rig()
    job = rig.state.enqueue(envelope_body("compile", job_id=JOB_A))
    rig.start()
    await until(lambda: job.completed)
    await rig.stop()

    assert rig.observer.states[0] is RunnerLoopState.registering
    assert RunnerLoopState.online in rig.observer.states
    assert rig.observer.states[-1] is RunnerLoopState.stopped
    assert ("started", JOB_A, "compile") in rig.observer.jobs
    assert ("succeeded", JOB_A, "compile") in rig.observer.jobs


async def test__announce_paused__observer_sees_paused() -> None:
    rig = Rig()
    rig.state.announce_paused = True
    rig.start()
    await until(lambda: RunnerLoopState.paused in rig.observer.states)
    await rig.stop()


async def test__reannounce__sends_the_new_endpoints() -> None:
    rig = Rig()
    rig.start()
    await until(lambda: rig.state.polls > 0)

    await rig.loop.reannounce(ai_endpoints=(DeclaredAiEndpoint("vllm", AiEndpointFlavor.openai),))
    await rig.stop()

    assert rig.state.announces[-1]["ai_endpoints"] == [{"name": "vllm", "flavor": "openai"}]


async def test__client__pairing_calls_go_without_a_bearer_token() -> None:
    state = FakeRunnerState()
    state.pair_status = "approved"
    client = RunnerClient("http://api", "", version="0.3", transport=SwitchTransport(create_fake_app(state)))

    started = await client.pair_start(RunnerPairStartRequest(name="MacBook", host_kind=RunnerHostKind.desktop))
    polled = await client.pair_poll(RunnerPairPollRequest(device_code=started.device_code))
    await client.aclose()

    assert started.user_code == "BCDF-2345"
    assert polled.registration_token == TOKEN


def test__config__ai_endpoints_from_env_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HSE_RUNNER__API_URL", "https://studio.example.org")
    monkeypatch.setenv(
        "HSE_RUNNER__AI_ENDPOINTS",
        json.dumps(
            [
                {"name": "ollama", "url": "http://localhost:11434/v1", "flavor": "ollama"},
                {"name": "vllm", "url": "http://gpu.lan:8000/v1", "key_env": "VLLM_API_KEY"},
            ]
        ),
    )

    config = RunnerConfig()

    assert [(e.name, e.flavor, e.key_env) for e in config.ai_endpoints] == [
        ("ollama", AiEndpointFlavor.ollama, None),
        ("vllm", AiEndpointFlavor.openai, "VLLM_API_KEY"),
    ]
    assert config.token is None


@pytest.mark.parametrize(
    "endpoints",
    [
        [{"name": "Ollama", "url": "http://x"}],
        [{"name": "x", "url": "file:///etc/passwd"}],
        [{"name": "x", "url": "http://h/v1?key=1"}],
        [{"name": "x", "url": "http://a"}, {"name": "x", "url": "http://b"}],
    ],
    ids=["bad_name", "not_http", "query", "duplicate"],
)
def test__config__bad_ai_endpoints__rejected(endpoints: list[dict[str, str]]) -> None:
    with pytest.raises(ValidationError):
        RunnerConfig(api_url="http://api", ai_endpoints=endpoints)  # type: ignore[arg-type]


async def test__container__runner_token_overrides_the_stored_identity(tmp_path: Path) -> None:
    state = FakeRunnerState()
    store = RunnerIdentityStore(tmp_path)
    from hse_doc_studio.core.jobs.wire import RunnerRegisterResponse  # noqa: PLC0415

    store.save("http://api", RunnerRegisterResponse("runner-1", "hsrn_old", 45, 10, 25))
    config = RunnerConfig(api_url="http://api", data_dir=tmp_path, runner_token=RUNNER_TOKEN)  # type: ignore[arg-type]
    container = create_runner_container(config, transport=SwitchTransport(create_fake_app(state)))
    client = await container.get(RunnerClient)

    await client.offline()
    await container.close()

    assert state.offline_calls == 1
    assert state.headers_seen[-1]["authorization"] == f"Bearer {RUNNER_TOKEN}"


async def test__container__no_token_and_no_identity__config_error(tmp_path: Path) -> None:
    container = create_runner_container(RunnerConfig(api_url="http://api", data_dir=tmp_path))

    with pytest.raises(RunnerConfigError):
        await container.get(RunnerClient)
    await container.close()
