"""`/api/admin/model-servers`: права, установка Ollama на подменённом докере, регистрация провайдера, секреты."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from fastapi import FastAPI
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.guards import install_exception_handlers
from hse_doc_studio.api.routers.admin import make_admin_router
from hse_doc_studio.core.identity.protocols import IActorResolver
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.infra.identity.resolvers import ChainActorResolver, SessionCookieResolver
from hse_doc_studio.use_cases.admin.model_servers import ModelServerService, ModelServerSettings, ModelServersUC
from hse_doc_studio.use_cases.identity.sessions import SessionService
from httpx import ASGITransport, AsyncClient

from tests.fakes.auth import empty_bearer_resolver
from tests.fakes.model_servers import FakeEngineClient, FakeProbe, FakeRegistry, FakeResources, FakeRuntime, hardware
from tests.integration.api.admin.test_admin_users_api import _Env as _UsersEnv


class _Stack:
    def __init__(self, users: _UsersEnv) -> None:
        self.users = users
        self.runtime = FakeRuntime()
        self.engine = FakeEngineClient()
        self.registry = FakeRegistry()
        self.probe = FakeProbe(hardware())
        self.settings = ModelServerSettings(startup_timeout_s=2.0)
        self.service = self.build()

    def build(self) -> ModelServerService:
        return ModelServerService(
            self.runtime,  # type: ignore[arg-type]
            self.engine,  # type: ignore[arg-type]
            self.probe,
            FakeResources(),  # type: ignore[arg-type]
            self.registry,  # type: ignore[arg-type]
            self.settings,
        )


class _Provider(Provider):
    scope = Scope.APP

    def __init__(self, s: _Stack) -> None:
        super().__init__()
        self.s = s

    @provide
    def resolver(self) -> IActorResolver:
        return ChainActorResolver(
            [SessionCookieResolver(SessionService(self.s.users.sessions, self.s.users.users)), empty_bearer_resolver()]
        )

    @provide
    def uc(self) -> ModelServersUC:
        return ModelServersUC(self.s.service, self.s.users.audit)


@pytest_asyncio.fixture
async def stack(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[_Stack]:
    monkeypatch.setattr(settings, "mode", StudioMode.server)
    s = _Stack(_UsersEnv())
    app = FastAPI()
    app.include_router(make_admin_router())
    install_exception_handlers(app)
    container = make_async_container(_Provider(s), FastapiProvider())
    setup_dishka(container, app)
    async with AsyncClient(transport=ASGITransport(app=app, client=("203.0.113.9", 5000)), base_url="http://test") as c:
        s.client = c  # type: ignore[attr-defined]
        yield s
    await s.service.wait_idle()
    await container.close()


async def _admin(s: _Stack) -> dict[str, str]:
    return await s.users.add("boss", admin=True)


async def _wait_done(s: _Stack, headers: dict[str, str], server_id: str) -> dict[str, object]:
    for _ in range(100):
        body = (await s.client.get(f"/api/admin/model-servers/{server_id}", headers=headers)).json()  # type: ignore[attr-defined]
        if body["status"] != "installing":
            return body
        await asyncio.sleep(0.02)
    raise AssertionError("install did not finish")


async def test_student_gets_404(stack: _Stack) -> None:
    headers = await stack.users.add("stud")
    for method, path in (("get", "/capabilities"), ("get", ""), ("post", "/estimate")):
        r = await getattr(stack.client, method)(f"/api/admin/model-servers{path}", headers=headers)  # type: ignore[attr-defined]
        assert r.status_code == 404


async def test_capabilities_shows_hardware_and_engine_hints(stack: _Stack) -> None:
    headers = await _admin(stack)
    body = (await stack.client.get("/api/admin/model-servers/capabilities", headers=headers)).json()  # type: ignore[attr-defined]
    assert body["local_enabled"]
    assert body["docker_available"]
    assert body["hardware"]["arch"] == "x86_64"
    engines = {e["engine"]: e for e in body["engines"]}
    assert engines["ollama"]["available"]
    assert engines["vllm"]["reasons"] == ["engine_requires_gpu"]


async def test_estimate_and_catalog(stack: _Stack) -> None:
    headers = await _admin(stack)
    est = await stack.client.post(  # type: ignore[attr-defined]
        "/api/admin/model-servers/estimate", headers=headers, json={"engine": "ollama", "model": "qwen3:8b"}
    )
    assert est.json()["fit"] == "fits"
    cat = await stack.client.get("/api/admin/model-servers/catalog?engine=ollama&q=llama", headers=headers)  # type: ignore[attr-defined]
    assert {m["ref"] for m in cat.json()["items"]} == {"llama3.2:3b", "llama3.1:8b"}
    bad = await stack.client.post(  # type: ignore[attr-defined]
        "/api/admin/model-servers/estimate", headers=headers, json={"engine": "ollama", "model": "a b;c"}
    )
    assert bad.status_code == 422


async def test_install_ollama_registers_provider_and_checks_model(stack: _Stack) -> None:
    headers = await _admin(stack)
    r = await stack.client.post(  # type: ignore[attr-defined]
        "/api/admin/model-servers", headers=headers, json={"engine": "ollama", "model": "qwen3:4b", "name": "Локальная"}
    )
    assert r.status_code == 202
    done = await _wait_done(stack, headers, r.json()["id"])
    assert done["status"] == "running"
    assert done["steps"] == dict.fromkeys(("container", "engine", "model", "provider", "verify"), "done")
    assert done["provider_id"] is not None
    [provider] = stack.registry.registered
    assert provider["base_url"].endswith(":11434/v1")  # type: ignore[union-attr]
    assert provider["type"].value == "ollama"  # type: ignore[union-attr]
    assert provider["models"] == ("qwen3:4b",)
    assert stack.engine.pinged[0][1] == "qwen3:4b"
    audit = await stack.users.audit.list(action="model_server.install")
    assert audit
    assert audit[0].details["model"] == "qwen3:4b"


async def test_failed_pull_marks_install_failed_and_keeps_logs(stack: _Stack) -> None:
    headers = await _admin(stack)
    stack.engine.pull_error = "file does not exist"
    r = await stack.client.post(  # type: ignore[attr-defined]
        "/api/admin/model-servers", headers=headers, json={"engine": "ollama", "model": "nope:1b"}
    )
    done = await _wait_done(stack, headers, r.json()["id"])
    assert done["status"] == "failed"
    assert "file does not exist" in str(done["error"])
    assert done["steps"]["model"] == "failed"  # type: ignore[index]
    assert not stack.registry.registered


async def test_not_responding_model_is_a_warning_not_a_failure(stack: _Stack) -> None:
    headers = await _admin(stack)
    stack.engine.ping_ok = False
    r = await stack.client.post(  # type: ignore[attr-defined]
        "/api/admin/model-servers", headers=headers, json={"engine": "ollama", "model": "qwen3:4b"}
    )
    done = await _wait_done(stack, headers, r.json()["id"])
    assert done["status"] == "running"
    assert done["steps"]["verify"] == "failed"  # type: ignore[index]


async def test_vllm_without_gpu_is_refused_unless_forced(stack: _Stack) -> None:
    headers = await _admin(stack)
    r = await stack.client.post(  # type: ignore[attr-defined]
        "/api/admin/model-servers", headers=headers, json={"engine": "vllm", "model": "Qwen/Qwen3-4B"}
    )
    assert r.status_code == 409
    assert r.json()["code"] == "model_server_engine_requires_gpu"


async def test_vllm_gets_generated_key_that_never_leaves(stack: _Stack) -> None:
    headers = await _admin(stack)
    stack.probe.info = hardware(nvidia=True, vram_mb=24576)
    r = await stack.client.post(  # type: ignore[attr-defined]
        "/api/admin/model-servers", headers=headers, json={"engine": "vllm", "model": "Qwen/Qwen3-4B"}
    )
    assert r.status_code == 202
    done = await _wait_done(stack, headers, r.json()["id"])
    assert done["status"] == "running"
    [provider] = stack.registry.registered
    key = provider["api_key"]
    assert isinstance(key, str)
    assert len(key) >= 32
    assert provider["type"].value == "openai_compat"  # type: ignore[union-attr]
    spec = stack.runtime.specs[0]
    assert spec.secret_env["VLLM_API_KEY"] == key
    assert key not in " ".join(spec.command)
    logs = await stack.client.get(f"/api/admin/model-servers/{done['id']}/logs", headers=headers)  # type: ignore[attr-defined]
    for text in (r.text, str(done), logs.text):
        assert key not in text
    for entry in await stack.users.audit.list(limit=50):
        assert key not in str(entry.details)


async def test_too_large_model_is_refused_unless_forced(stack: _Stack) -> None:
    headers = await _admin(stack)
    r = await stack.client.post(  # type: ignore[attr-defined]
        "/api/admin/model-servers", headers=headers, json={"engine": "ollama", "model": "huge-model-405b"}
    )
    assert r.status_code == 409
    assert r.json()["code"] == "model_server_too_large"


async def test_local_install_disabled_by_cluster_setting(stack: _Stack) -> None:
    headers = await _admin(stack)
    stack.settings = ModelServerSettings(local_enabled=False)
    stack.service = stack.build()
    caps = (await stack.client.get("/api/admin/model-servers/capabilities", headers=headers)).json()  # type: ignore[attr-defined]
    assert caps["local_enabled"] is False
    assert caps["docker_available"] is False
    r = await stack.client.post(  # type: ignore[attr-defined]
        "/api/admin/model-servers", headers=headers, json={"engine": "ollama", "model": "qwen3:4b"}
    )
    assert r.status_code == 409
    assert r.json()["code"] == "model_server_local_install_disabled"
    assert not stack.runtime.specs


async def test_docker_unavailable_is_reported(stack: _Stack) -> None:
    headers = await _admin(stack)
    stack.runtime.docker = False
    r = await stack.client.post(  # type: ignore[attr-defined]
        "/api/admin/model-servers", headers=headers, json={"engine": "ollama", "model": "qwen3:4b"}
    )
    assert r.json()["code"] == "model_server_docker_unavailable"


async def test_only_one_install_at_a_time(stack: _Stack) -> None:
    headers = await _admin(stack)
    gate = asyncio.Event()

    async def slow(*_: object) -> str:
        await gate.wait()
        return "cid"

    stack.runtime.run = slow  # type: ignore[method-assign,assignment]
    first = await stack.client.post(  # type: ignore[attr-defined]
        "/api/admin/model-servers", headers=headers, json={"engine": "ollama", "model": "qwen3:4b"}
    )
    assert first.status_code == 202
    second = await stack.client.post(  # type: ignore[attr-defined]
        "/api/admin/model-servers", headers=headers, json={"engine": "ollama", "model": "qwen3:8b"}
    )
    assert second.status_code == 409
    assert second.json()["code"] == "model_server_busy"
    gate.set()
    stack.service._jobs[first.json()["id"]].task.cancel()  # type: ignore[union-attr]


async def test_stop_start_logs_and_remove(stack: _Stack) -> None:
    headers = await _admin(stack)
    r = await stack.client.post(  # type: ignore[attr-defined]
        "/api/admin/model-servers", headers=headers, json={"engine": "ollama", "model": "qwen3:4b"}
    )
    sid = r.json()["id"]
    done = await _wait_done(stack, headers, sid)
    base = f"/api/admin/model-servers/{sid}"
    assert (await stack.client.post(f"{base}/stop", headers=headers)).json()["status"] == "stopped"  # type: ignore[attr-defined]
    assert (await stack.client.post(f"{base}/start", headers=headers)).json()["status"] == "running"  # type: ignore[attr-defined]
    assert "line two" in (await stack.client.get(f"{base}/logs", headers=headers)).json()["text"]  # type: ignore[attr-defined]
    assert (await stack.client.delete(f"{base}?purge_models=true", headers=headers)).status_code == 204  # type: ignore[attr-defined]
    assert stack.runtime.removed == [(f"hse-ms-{sid}", "hse-ms-ollama-models")]
    assert [str(p) for p in stack.registry.unregistered] == [done["provider_id"]]
    assert (await stack.client.get(base, headers=headers)).status_code == 404  # type: ignore[attr-defined]
    actions = {e.action for e in await stack.users.audit.list(limit=50)}
    assert {"model_server.install", "model_server.stop", "model_server.start", "model_server.remove"} <= actions
