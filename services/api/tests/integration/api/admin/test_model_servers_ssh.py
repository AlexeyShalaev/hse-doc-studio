"""Сервер ИИ-модели по SSH поверх общего слоя установки: полезная нагрузка вместо раннера, секреты, открытие наружу."""

from __future__ import annotations

import asyncio

import pytest
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.model_servers import (
    Engine,
    Exposure,
    ModelServerError,
    ModelServerErrorCode,
    ServerStatus,
    StepState,
    Target,
)
from hse_doc_studio.core.runner_install import SshAuth, SshAuthKind, SshResult, SshTarget
from hse_doc_studio.use_cases.admin.model_servers import ModelServerService, ModelServerSettings
from hse_doc_studio.use_cases.admin.model_servers_ssh import ModelServerSshInstaller
from hse_doc_studio.use_cases.runner_install.jobs import InstallJobStore
from hse_doc_studio.use_cases.runner_install.ssh_service import SshInstallService, SshSessionStore

from tests.fakes.model_servers import (
    FakeEngineClient,
    FakeProbe,
    FakeRegistry,
    FakeRemote,
    FakeResources,
    FakeRuntime,
    InMemoryModelServerStore,
    hardware,
)
from tests.fakes.ops import NoopUow
from tests.fakes.ssh import FakeConnector, FakeEgress, FakeHost, InMemorySshCredentials

ADMIN = Actor(kind="user", id="boss", is_instance_admin=True)
PASSWORD = "right-password"
HF = "hf_SECRET_TOKEN_VALUE"


class _Audit:
    def __init__(self) -> None:
        self.events: list[tuple[str, object]] = []

    async def record(self, action: str, *, actor_id: str | None, target: str | None = None, details=None) -> None:  # type: ignore[no-untyped-def]
        self.events.append((action, details))


class _Vault:
    async def reveal(self) -> str:
        return HF


def build_remote_stub(conn, sudo, sudo_stdin, public_host, container, port):  # type: ignore[no-untyped-def]
    from hse_doc_studio.infra.model_servers.ssh_runtime import build_remote  # noqa: PLC0415

    return build_remote(conn, sudo, sudo_stdin, public_host, container, port)


class Stack:
    def __init__(self) -> None:
        self.host = FakeHost(fail_on={"chat/completions": SshResult(0, "200", "")})
        self.audit = _Audit()
        self.store = InMemoryModelServerStore()
        self.registry = FakeRegistry()
        self.credentials = InMemorySshCredentials()
        self.ssh = SshInstallService(
            None,  # type: ignore[arg-type]
            FakeConnector(self.host),
            FakeEgress(),
            SshSessionStore(),
            InstallJobStore(),
            self.audit,  # type: ignore[arg-type]
            NoopUow(),  # type: ignore[arg-type]
            self.credentials,
            image="registry.example/hds:1",
            script=lambda image: "# runner\n",
            poll_s=0.01,
            verify_timeout_s=0.1,
        )
        self.installer = ModelServerSshInstaller(
            self.store,
            self.registry,  # type: ignore[arg-type]
            _Vault(),  # type: ignore[arg-type]
            build_remote_stub,
            images={},
            ready_timeout_s=0.5,
        )

    async def install(self, engine: Engine, model: str, **kw):  # type: ignore[no-untyped-def]
        payload = self.installer.payload(
            ADMIN,
            engine=engine,
            model=model,
            name=kw.get("name", ""),
            exposure=kw.get("exposure", Exposure.localhost),
            acknowledge_public=kw.get("acknowledge_public", False),
            force=kw.get("force", False),
        )
        session, key = await self.ssh.probe(
            ADMIN,
            SshTarget("srv.example.org", 22, "root"),
            SshAuth(SshAuthKind.password, Secret(PASSWORD)),
            save_credentials=kw.get("save", False),
            label="gpu-box",
        )
        await self.ssh.confirm(ADMIN, session.id, key.fingerprint)
        job = await self.ssh.install(
            ADMIN,
            session.id,
            studio_url="https://studio.example",
            name=None,
            install_docker=False,
            payload=payload,
            job_name=payload.name,
        )
        await asyncio.gather(*self.ssh._tasks, return_exceptions=True)  # noqa: SLF001
        return job


def _docker_run(stack: Stack) -> object:
    return next(
        c for c in stack.host.calls if "docker run" in c.command or " run " in c.command and "docker" in c.command
    )


async def test_vllm_on_ssh_stays_on_loopback_without_provider() -> None:
    stack = Stack()
    job = await stack.install(Engine.vllm, "Qwen/Qwen3-4B")

    assert job.state.value == "succeeded"
    states = {s.key: s.state.value for s in job.steps}
    assert states["container"] == "done"
    assert states["provider"] == "skipped"
    assert states["verify"] == "done"
    run = _docker_run(stack)
    assert "127.0.0.1:8000:8000" in run.command  # type: ignore[attr-defined]
    assert "0.0.0.0:8000" not in run.command  # type: ignore[attr-defined]
    assert not stack.registry.registered
    [record] = stack.store.items.values()
    assert record.target is Target.ssh  # type: ignore[attr-defined]
    assert record.status is ServerStatus.running  # type: ignore[attr-defined]
    assert record.exposure is Exposure.localhost  # type: ignore[attr-defined]
    assert record.steps["provider"] is StepState.skipped  # type: ignore[attr-defined]


async def test_secrets_travel_only_through_stdin_never_in_commands_or_records() -> None:
    stack = Stack()
    await stack.install(Engine.vllm, "Qwen/Qwen3-4B")

    run = _docker_run(stack)
    assert HF not in run.command  # type: ignore[attr-defined]
    assert HF in (run.stdin or "")  # type: ignore[attr-defined]
    assert "VLLM_API_KEY=" in (run.stdin or "")  # type: ignore[attr-defined]
    assert "--env-file" in run.command  # type: ignore[attr-defined]
    key = (run.stdin or "").split("VLLM_API_KEY=")[1].split("\n")[0]  # type: ignore[attr-defined]
    for call in stack.host.calls:
        assert key not in call.command
        assert HF not in call.command
    for record in stack.store.history:
        assert HF not in repr(record)
        assert key not in repr(record)
    for _action, details in stack.audit.events:
        assert HF not in str(details)
        assert key not in str(details)


async def test_public_exposure_binds_all_interfaces_registers_provider_with_key() -> None:
    stack = Stack()
    job = await stack.install(Engine.vllm, "Qwen/Qwen3-4B", exposure=Exposure.public, acknowledge_public=True)

    assert job.state.value == "succeeded"
    run = _docker_run(stack)
    assert "0.0.0.0:8000:8000" in run.command  # type: ignore[attr-defined]
    [provider] = stack.registry.registered
    assert provider["base_url"] == "http://srv.example.org:8000/v1"
    assert isinstance(provider["api_key"], str)
    assert len(provider["api_key"]) >= 32  # type: ignore[arg-type]
    [record] = stack.store.items.values()
    assert record.provider_id == str(provider["id"])  # type: ignore[attr-defined]


def test_public_ollama_is_refused_and_public_needs_confirmation() -> None:
    stack = Stack()
    with pytest.raises(ModelServerError) as err:
        stack.installer.payload(
            ADMIN,
            engine=Engine.ollama,
            model="qwen3:4b",
            name="",
            exposure=Exposure.public,
            acknowledge_public=True,
            force=False,
        )
    assert err.value.code is ModelServerErrorCode.public_needs_key
    with pytest.raises(ModelServerError) as err2:
        stack.installer.payload(
            ADMIN,
            engine=Engine.vllm,
            model="Qwen/Qwen3-4B",
            name="",
            exposure=Exposure.public,
            acknowledge_public=False,
            force=False,
        )
    assert err2.value.code is ModelServerErrorCode.public_unconfirmed
    with pytest.raises(ModelServerError):
        stack.installer.payload(
            ADMIN,
            engine=Engine.vllm,
            model="bad name;rm",
            name="",
            exposure=Exposure.localhost,
            acknowledge_public=False,
            force=False,
        )


async def test_missing_gpu_fails_the_install_and_marks_the_record() -> None:
    stack = Stack()
    stack.host.fail_on["nvidia-smi"] = SshResult(127, "", "not found")
    job = await stack.install(Engine.vllm, "Qwen/Qwen3-4B")

    assert job.state.value == "failed"
    assert job.error_code == "engine_requires_gpu"
    [record] = stack.store.items.values()
    assert record.status is ServerStatus.failed  # type: ignore[attr-defined]
    assert not any("docker run" in c.command or " run " in c.command for c in stack.host.calls if "docker" in c.command)


async def test_ollama_on_ssh_pulls_model_inside_the_container() -> None:
    stack = Stack()
    job = await stack.install(Engine.ollama, "qwen3:4b")

    assert job.state.value == "succeeded"
    assert any("exec" in c.command and "ollama pull qwen3:4b" in c.command for c in stack.host.calls)


async def test_saved_access_lets_the_server_be_managed_later() -> None:
    stack = Stack()
    await stack.install(Engine.vllm, "Qwen/Qwen3-4B", save=True)
    [record] = stack.store.items.values()
    assert record.credential_id  # type: ignore[attr-defined]

    runtime = FakeRuntime()
    remote = FakeRemote(runtime)
    service = ModelServerService(
        FakeRuntime(),  # type: ignore[arg-type]
        FakeEngineClient(),  # type: ignore[arg-type]
        FakeProbe(hardware()),
        FakeResources(),  # type: ignore[arg-type]
        stack.registry,  # type: ignore[arg-type]
        ModelServerSettings(),
        None,
        stack.store,  # type: ignore[arg-type]
        remote,  # type: ignore[arg-type]
    )
    [view] = await service.list()
    assert view.target is Target.ssh
    assert view.manageable
    await service.stop(record.id, ADMIN)  # type: ignore[attr-defined]
    assert remote.opened == [(record.credential_id, "")]  # type: ignore[attr-defined]
    assert remote.closed == 1
    assert (await service.get(record.id)).status is ServerStatus.stopped  # type: ignore[attr-defined]
    await service.remove("boss", record.id, actor=ADMIN)  # type: ignore[attr-defined]
    assert await stack.store.list() == []


async def test_server_without_saved_access_cannot_be_managed_but_can_be_forgotten() -> None:
    stack = Stack()
    await stack.install(Engine.vllm, "Qwen/Qwen3-4B", save=False)
    [record] = stack.store.items.values()
    service = ModelServerService(
        FakeRuntime(),  # type: ignore[arg-type]
        FakeEngineClient(),  # type: ignore[arg-type]
        FakeProbe(hardware()),
        FakeResources(),  # type: ignore[arg-type]
        stack.registry,  # type: ignore[arg-type]
        ModelServerSettings(),
        None,
        stack.store,  # type: ignore[arg-type]
        FakeRemote(FakeRuntime()),  # type: ignore[arg-type]
    )
    [view] = await service.list()
    assert not view.manageable
    with pytest.raises(ModelServerError) as err:
        await service.stop(record.id, ADMIN)  # type: ignore[attr-defined]
    assert err.value.code is ModelServerErrorCode.not_manageable
    await service.remove("boss", record.id, actor=ADMIN)  # type: ignore[attr-defined]
    assert await stack.store.list() == []


async def test_install_interrupted_by_restart_is_shown_as_failed() -> None:
    from dataclasses import replace  # noqa: PLC0415

    stack = Stack()
    await stack.install(Engine.vllm, "Qwen/Qwen3-4B")
    [record] = stack.store.items.values()
    stack.store.items[record.id] = replace(record, target=Target.local, status=ServerStatus.installing)  # type: ignore[attr-defined,type-var]
    service = ModelServerService(
        FakeRuntime(),  # type: ignore[arg-type]
        FakeEngineClient(),  # type: ignore[arg-type]
        FakeProbe(hardware()),
        FakeResources(),  # type: ignore[arg-type]
        stack.registry,  # type: ignore[arg-type]
        ModelServerSettings(),
        None,
        stack.store,  # type: ignore[arg-type]
    )
    [view] = await service.list()
    assert view.status is ServerStatus.failed
    assert view.error
