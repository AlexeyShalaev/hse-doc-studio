"""`/api/admin` эксплуатации: очередь, квоты, сервисы, место, политика подписи, общие ИИ-провайдеры, токены раннеров."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from fastapi import FastAPI
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.guards import install_exception_handlers
from hse_doc_studio.api.observability.health import HealthRegistry
from hse_doc_studio.api.routers.admin import make_admin_router
from hse_doc_studio.core.entities import AIProvider
from hse_doc_studio.core.identity.protocols import IActorResolver
from hse_doc_studio.core.jobs.enums import JobKind
from hse_doc_studio.core.jobs.queue import EnqueueRequest
from hse_doc_studio.core.jobs.runners import hash_runner_secret
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.core.runner_install import InstallError, InstallTarget, LocalInstance
from hse_doc_studio.infra.identity.resolvers import ChainActorResolver, SessionCookieResolver
from hse_doc_studio.use_cases.admin.ops_ai_providers import (
    CheckInstanceAiProviderUC,
    CreateInstanceAiProviderUC,
    DeleteInstanceAiProviderUC,
    GetInstanceAiProviderUC,
    InstanceAiProviderStore,
    ListInstanceAiProvidersUC,
    UpdateInstanceAiProviderUC,
)
from hse_doc_studio.use_cases.admin.ops_queue import (
    CancelJobBatchUC,
    CancelJobUC,
    ListQueueUC,
    PickProjectsUC,
    QueueSummaryUC,
)
from hse_doc_studio.use_cases.admin.ops_quotas import GetQuotasUC, QuotaService, UpdateQuotasUC
from hse_doc_studio.use_cases.admin.ops_runners import (
    ListRegistrationTokensUC,
    ListRunnersUC,
    PickRunnersUC,
    RunnerSummaryUC,
)
from hse_doc_studio.use_cases.admin.ops_services import ServicesOverviewUC
from hse_doc_studio.use_cases.admin.ops_signing import GetSigningPolicyUC, UpdateSigningPolicyUC
from hse_doc_studio.use_cases.admin.ops_storage import GetStorageUsageUC, ListStorageOwnersUC
from hse_doc_studio.use_cases.admin.runner_isolation import (
    RunnerDeploymentUC,
    RunnerIsolationSettings,
    RunnerIsolationUC,
)
from hse_doc_studio.use_cases.identity.smtp_settings import SmtpSettingsService
from hse_doc_studio.use_cases.jobs.queue_service import JobQueueService
from hse_doc_studio.use_cases.jobs.runners import RunnerRegistry
from hse_doc_studio.use_cases.runner_install import (
    InstallJobStore,
    RunnerInstallService,
    SshInstallService,
    SshSessionStore,
)
from httpx import ASGITransport, AsyncClient

from tests.factories.runner_isolation import make_declared, make_install_facts, make_report
from tests.fakes.auth import empty_bearer_resolver
from tests.fakes.identity import InMemoryInstanceSettingsRepository
from tests.fakes.job_queue import InMemoryJobQueue
from tests.fakes.ops import (
    CountingStorageReader,
    FixedProjectPicker,
    FixedServerKeyCounter,
    InMemoryAIProviderRepository,
    InMemoryJobAdminReader,
    NoopUow,
    ReversingCipher,
)
from tests.fakes.runner_install import FakeLocalHost
from tests.fakes.runner_isolation import FakeClusterReader
from tests.fakes.runners import (
    InMemoryRegistrationTokenRepository,
    InMemoryRunnerAdminReader,
    InMemoryRunnerRepository,
)
from tests.fakes.ssh import FakeConnector, FakeEgress, FakeHost, InMemorySshCredentials
from tests.integration.api.admin.test_admin_users_api import _Env as _UsersEnv


class _Lister:
    async def list_models(self, provider: AIProvider) -> list[str]:
        return ["m1"] if provider.api_key else []


class _Egress:
    async def authorize(self, host: str, port: int | None = None, *, purpose: object = None):  # type: ignore[no-untyped-def]
        from hse_doc_studio.core.egress import EgressBlockedError, EgressBlockReason, EgressTarget  # noqa: PLC0415

        if host == "169.254.169.254":
            raise EgressBlockedError(host, EgressBlockReason.metadata)
        return EgressTarget(host=host, port=port, addresses=("10.0.0.5",))


class _Stack:
    def __init__(self, users: _UsersEnv) -> None:
        self.users = users
        self.settings = InMemoryInstanceSettingsRepository()
        self.queue = InMemoryJobQueue()
        self.storage = CountingStorageReader()
        self.runners = InMemoryRunnerRepository()
        self.tokens = InMemoryRegistrationTokenRepository()
        self.runner_reader = InMemoryRunnerAdminReader(self.runners, self.tokens)
        self.job_reader = InMemoryJobAdminReader(self.queue)
        self.health = HealthRegistry()
        self.quotas = QuotaService(self.settings, ttl_s=0)
        self.providers = InMemoryAIProviderRepository()
        self.store = InstanceAiProviderStore(self.providers)
        self.registry = RunnerRegistry(self.runners, self.tokens, users.audit, NoopUow())
        self.smtp = SmtpSettingsService(self.settings, ReversingCipher())  # type: ignore[arg-type]
        self.install_host = FakeLocalHost()
        self.install_jobs = InstallJobStore()
        self.install = RunnerInstallService(
            self.registry,
            {InstallTarget.docker: self.install_host},
            self.install_jobs,
            users.audit,
            NoopUow(),
            image="registry.example/hds:1.2.3",
            data_dir="/var/lib/hse-runner",
            register_timeout_s=0.3,
            poll_s=0.01,
        )
        self.ssh_host = FakeHost()
        self.ssh_connector = FakeConnector(self.ssh_host)
        self.ssh_egress = FakeEgress()
        self.ssh_credentials = InMemorySshCredentials()
        self.ssh_sessions = SshSessionStore()
        self.ssh = SshInstallService(
            self.registry,
            self.ssh_connector,
            self.ssh_egress,
            self.ssh_sessions,
            self.install_jobs,
            users.audit,
            NoopUow(),
            self.ssh_credentials,
            image="registry.example/hds:1.2.3",
            script=lambda image: f"# runner install script for {image}\n",
            register_timeout_s=0.3,
            poll_s=0.01,
            verify_timeout_s=0.1,
        )
        self.cluster = FakeClusterReader()
        self.background: set[asyncio.Task[None]] = set()
        self.isolation = RunnerIsolationSettings(
            declared=None, install=make_install_facts(), read_live=False, studio_version="0.14.0"
        )
        self.client: AsyncClient
        self.app: FastAPI


class _Provider(Provider):
    scope = Scope.APP

    def __init__(self, s: _Stack) -> None:
        super().__init__()
        self.s = s

    @provide
    def resolver(self) -> IActorResolver:
        from hse_doc_studio.use_cases.identity.sessions import SessionService  # noqa: PLC0415

        return ChainActorResolver(
            [SessionCookieResolver(SessionService(self.s.users.sessions, self.s.users.users)), empty_bearer_resolver()]
        )

    @provide
    def registry(self) -> RunnerRegistry:
        return self.s.registry

    @provide
    def runner_install(self) -> RunnerInstallService:
        return self.s.install

    @provide
    def ssh_install(self) -> SshInstallService:
        return self.s.ssh

    @provide
    def list_runners(self) -> ListRunnersUC:
        return ListRunnersUC(self.s.runner_reader)

    # Настройки изоляции тест меняет на ходу: сценарии строятся на каждый запрос.
    @provide(scope=Scope.REQUEST)
    def runner_deployment(self) -> RunnerDeploymentUC:
        return RunnerDeploymentUC(self.s.runners, self.s.cluster, self.s.isolation)

    @provide(scope=Scope.REQUEST)
    def runner_isolation(self) -> RunnerIsolationUC:
        return RunnerIsolationUC(self.s.cluster, self.s.isolation)

    @provide
    def runner_summary(self) -> RunnerSummaryUC:
        return RunnerSummaryUC(self.s.runner_reader)

    @provide
    def list_tokens(self) -> ListRegistrationTokensUC:
        return ListRegistrationTokensUC(self.s.runner_reader)

    @provide
    def pick_runners(self) -> PickRunnersUC:
        return PickRunnersUC(self.s.runner_reader)

    @provide
    def pick_projects(self) -> PickProjectsUC:
        return PickProjectsUC(FixedProjectPicker({str(uuid4()): "Диплом"}))

    @provide
    def list_queue(self) -> ListQueueUC:
        return ListQueueUC(self.s.job_reader)

    @provide
    def queue_summary(self) -> QueueSummaryUC:
        return QueueSummaryUC(self.s.job_reader)

    @provide
    def cancel(self) -> CancelJobUC:
        return CancelJobUC(
            self.s.queue, JobQueueService(self.s.queue), self.s.users.audit, NoopUow(), self.s.job_reader
        )

    @provide
    def cancel_batch(self) -> CancelJobBatchUC:
        return CancelJobBatchUC(JobQueueService(self.s.queue), self.s.users.audit, NoopUow(), self.s.job_reader)

    @provide
    def get_quotas(self) -> GetQuotasUC:
        return GetQuotasUC(self.s.settings)

    @provide
    def update_quotas(self) -> UpdateQuotasUC:
        return UpdateQuotasUC(self.s.settings, self.s.users.audit, NoopUow(), self.s.quotas)

    @provide
    def services(self) -> ServicesOverviewUC:
        return ServicesOverviewUC(self.s.runners, self.s.smtp)

    @provide
    def storage(self) -> GetStorageUsageUC:
        return GetStorageUsageUC(self.s.storage)

    @provide
    def storage_owners(self) -> ListStorageOwnersUC:
        return ListStorageOwnersUC(self.s.storage)

    @provide
    def get_signing(self) -> GetSigningPolicyUC:
        return GetSigningPolicyUC(self.s.settings, FixedServerKeyCounter(2))

    @provide
    def update_signing(self) -> UpdateSigningPolicyUC:
        return UpdateSigningPolicyUC(self.s.settings, self.s.users.audit, NoopUow(), FixedServerKeyCounter(2))

    @provide
    def list_providers(self) -> ListInstanceAiProvidersUC:
        return ListInstanceAiProvidersUC(self.s.providers)

    @provide
    def get_provider(self) -> GetInstanceAiProviderUC:
        return GetInstanceAiProviderUC(self.s.store)

    @provide
    def create_provider(self) -> CreateInstanceAiProviderUC:
        return CreateInstanceAiProviderUC(self.s.store, self.s.users.audit, NoopUow(), _Egress())  # type: ignore[arg-type]

    @provide
    def update_provider(self) -> UpdateInstanceAiProviderUC:
        return UpdateInstanceAiProviderUC(self.s.store, self.s.users.audit, NoopUow(), _Egress())  # type: ignore[arg-type]

    @provide
    def delete_provider(self) -> DeleteInstanceAiProviderUC:
        return DeleteInstanceAiProviderUC(self.s.store, self.s.users.audit, NoopUow())

    @provide
    def check_provider(self) -> CheckInstanceAiProviderUC:
        return CheckInstanceAiProviderUC(self.s.store, _Lister())


@pytest_asyncio.fixture
async def stack(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[_Stack]:
    monkeypatch.setattr(settings, "mode", StudioMode.server)
    s = _Stack(_UsersEnv())
    app = FastAPI()
    app.include_router(make_admin_router())
    install_exception_handlers(app)
    app.state.health_registry = s.health
    container = make_async_container(_Provider(s), FastapiProvider())
    setup_dishka(container, app)
    async with AsyncClient(transport=ASGITransport(app=app, client=("203.0.113.9", 5000)), base_url="http://test") as c:
        s.client = c
        s.app = app
        yield s
    await container.close()


def _enqueue(user: object = None, *, batch_id: UUID | None = None, project_id: UUID | None = None) -> EnqueueRequest:
    return EnqueueRequest(
        job_id=uuid4(),
        kind=JobKind.compile,
        project_id=project_id or uuid4(),
        user_id=user or uuid4(),  # type: ignore[arg-type]
        tags=frozenset({"tex"}),
        payload={},
        batch_id=batch_id,
    )


_ROUTES: list[tuple[str, str, Any]] = [
    ("GET", "/api/admin/queue", None),
    ("GET", "/api/admin/queue/summary", None),
    ("POST", f"/api/admin/queue/{uuid4()}/cancel", None),
    ("POST", f"/api/admin/queue/batches/{uuid4()}/cancel", None),
    ("GET", "/api/admin/quotas", None),
    ("PUT", "/api/admin/quotas", {"user_concurrent": 1, "org_concurrent": None, "max_duration_s": None}),
    ("GET", "/api/admin/services", None),
    ("GET", "/api/admin/storage", None),
    ("GET", "/api/admin/storage/owners", None),
    ("GET", "/api/admin/runners", None),
    ("GET", "/api/admin/runners/summary", None),
    ("GET", "/api/admin/runners/isolation", None),
    ("GET", f"/api/admin/runners/{uuid4().hex}/deployment", None),
    ("GET", "/api/admin/runner-tokens", None),
    ("GET", "/api/admin/pickers/runners", None),
    ("GET", "/api/admin/pickers/projects", None),
    ("GET", "/api/admin/settings/signing", None),
    ("PUT", "/api/admin/settings/signing", {"server_keys": "allowed"}),
    ("GET", "/api/admin/ai-providers", None),
    (
        "POST",
        "/api/admin/ai-providers",
        {
            "name": "p",
            "type": "openai",
            "api_key": "k",
            "base_url": "",
            "models": [],
            "ssl_verify": True,
            "connect_timeout_s": 10,
            "request_timeout_s": 60,
        },
    ),
    ("GET", f"/api/admin/ai-providers/{uuid4()}", None),
    ("DELETE", f"/api/admin/ai-providers/{uuid4()}", None),
    ("POST", f"/api/admin/ai-providers/{uuid4()}/check", None),
    ("POST", "/api/admin/runner-tokens", {"label": "t"}),
    ("GET", "/api/admin/runner-install/local", None),
    ("GET", "/api/admin/runner-install/local/instances", None),
    ("POST", "/api/admin/runner-install/local/docker", {}),
    ("DELETE", "/api/admin/runner-install/local/docker/hse-runner-1", None),
    ("POST", "/api/admin/runner-install/local/docker/hse-runner-1/upgrade", None),
    ("GET", f"/api/admin/runner-install/jobs/{uuid4()}", None),
    ("GET", "/api/admin/runner-install/ssh", None),
    (
        "POST",
        "/api/admin/runner-install/ssh/probe",
        {"host": "srv.example.org", "username": "root", "auth_kind": "password", "password": "x"},
    ),
    ("POST", "/api/admin/runner-install/ssh/abc/confirm", {"fingerprint": "SHA256:0123456789"}),
    ("POST", "/api/admin/runner-install/ssh/abc/install", {}),
    ("DELETE", "/api/admin/runner-install/ssh/abc", None),
    ("GET", "/api/admin/runner-install/ssh/credentials", None),
    ("DELETE", "/api/admin/runner-install/ssh/credentials/abc", None),
    ("POST", "/api/admin/runner-install/ssh/credentials/abc/run", {"action": "update"}),
]


@pytest.mark.parametrize(("method", "path", "body"), _ROUTES, ids=[f"{m} {p[:40]}" for m, p, _ in _ROUTES])
async def test__ops_routes__student_404_anonymous_401(stack: _Stack, method: str, path: str, body: Any) -> None:
    student = await stack.users.add("student")

    assert (await stack.client.request(method, path, json=body, headers=student)).status_code == 404
    assert (await stack.client.request(method, path, json=body)).status_code == 401
    assert await stack.users.audit.list() == []


async def test__queue__list_summary_cancel_flow(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)
    anna = uuid4()
    first = (await stack.queue.enqueue(_enqueue(anna))).job
    await stack.queue.enqueue(_enqueue())
    c = stack.client

    page = (await c.get("/api/admin/queue?limit=1", headers=boss)).json()
    only = (await c.get(f"/api/admin/queue?user_id={anna}&state=queued", headers=boss)).json()
    summary = (await c.get("/api/admin/queue/summary", headers=boss)).json()
    cancelled = await c.post(f"/api/admin/queue/{first.id}/cancel", headers=boss)
    missing = await c.post(f"/api/admin/queue/{uuid4()}/cancel", headers=boss)

    assert len(page["items"]) == 1
    assert page["next_cursor"] is not None
    assert [j["id"] for j in only["items"]] == [str(first.id)]
    assert "payload" not in only["items"][0]
    assert summary["by_state"]["queued"] == 2
    assert cancelled.json()["state"] == "cancelled"
    assert missing.status_code == 404
    assert [e.action for e in await stack.users.audit.list()] == ["queue.job_cancel"]
    assert (await c.get("/api/admin/queue?state=bogus", headers=boss)).status_code == 422
    assert (await c.get("/api/admin/queue?limit=0", headers=boss)).status_code == 422


async def test__queue__build_all_batch__whole_batch_summary_on_each_row_and_filter(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)
    anna, project, batch = uuid4(), uuid4(), uuid4()
    jobs = [(await stack.queue.enqueue(_enqueue(anna, batch_id=batch, project_id=project))).job for _ in range(3)]
    single = (await stack.queue.enqueue(_enqueue())).job
    await stack.queue.request_cancel(jobs[0].id)
    c = stack.client

    # Первая страница видит только две задачи пакета, но сводка пакета считает все три.
    page = (await c.get("/api/admin/queue?limit=2", headers=boss)).json()
    only = (await c.get(f"/api/admin/queue?batch_id={batch}", headers=boss)).json()

    assert [j["id"] for j in page["items"]] == [str(single.id), str(jobs[2].id)]
    assert (page["items"][0]["batch_id"], page["items"][0]["batch"]) == (None, None)
    row = page["items"][1]
    assert row["batch_id"] == str(batch)
    assert row["batch"]["total"] == 3
    assert row["batch"]["by_state"] == {"cancelled": 1, "queued": 2}
    assert sorted(j["id"] for j in only["items"]) == sorted(str(j.id) for j in jobs)


async def test__queue__cancel_batch__cancels_active_jobs_and_audits_each(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)
    batch = uuid4()
    jobs = [(await stack.queue.enqueue(_enqueue(batch_id=batch))).job for _ in range(3)]
    other = (await stack.queue.enqueue(_enqueue())).job
    await stack.queue.request_cancel(jobs[0].id)

    response = await stack.client.post(f"/api/admin/queue/batches/{batch}/cancel", headers=boss)

    assert response.json() == {"cancelled": 2}
    states = {j.id: (await stack.queue.get(j.id)).state.value for j in [*jobs, other]}  # type: ignore[union-attr]
    assert states == {jobs[0].id: "cancelled", jobs[1].id: "cancelled", jobs[2].id: "cancelled", other.id: "queued"}
    events = await stack.users.audit.list()
    assert [e.action for e in events] == ["queue.job_cancel", "queue.job_cancel"]
    assert {e.details["batch_id"] for e in events} == {str(batch)}


async def test__quotas__put_validates_persists_and_audits(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)
    c = stack.client
    assert (await c.get("/api/admin/quotas", headers=boss)).json() == {
        "user_concurrent": None,
        "org_concurrent": None,
        "max_duration_s": None,
        "on_exhausted": "wait",
    }

    for bad in ({"user_concurrent": 0}, {"max_duration_s": 5}, {"max_duration_s": 10**6}):
        body = {"user_concurrent": None, "org_concurrent": None, "max_duration_s": None, **bad}
        assert (await c.put("/api/admin/quotas", json=body, headers=boss)).status_code == 422
    missing_field = await c.put("/api/admin/quotas", json={"user_concurrent": 1}, headers=boss)
    saved = await c.put(
        "/api/admin/quotas",
        json={"user_concurrent": 2, "org_concurrent": 6, "max_duration_s": 300},
        headers=boss,
    )

    assert missing_field.status_code == 422
    assert saved.json()["user_concurrent"] == 2
    assert (await c.get("/api/admin/quotas", headers=boss)).json()["max_duration_s"] == 300
    quota = await stack.quotas.current()
    assert quota is not None
    assert quota.max_running_per_org == 6
    assert [e.action for e in await stack.users.audit.list()] == ["settings.quotas_update"]


async def test__signing_policy__default_forbidden_then_allowed(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)
    c = stack.client

    assert (await c.get("/api/admin/settings/signing", headers=boss)).json() == {
        "server_keys": "forbidden",
        "stored_keys": 2,
    }
    assert (await c.put("/api/admin/settings/signing", json={"server_keys": "yes"}, headers=boss)).status_code == 422
    await c.put("/api/admin/settings/signing", json={"server_keys": "allowed"}, headers=boss)

    assert (await c.get("/api/admin/settings/signing", headers=boss)).json() == {
        "server_keys": "allowed",
        "stored_keys": 2,
    }
    assert [e.action for e in await stack.users.audit.list()] == ["settings.signing_policy_update"]


async def test__services__failed_probe_is_down_not_500(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)

    async def boom() -> str | None:
        raise ConnectionError

    async def fine() -> str | None:
        return None

    stack.health.register("s3", boom)
    stack.health.register("database", fine)

    response = await stack.client.get("/api/admin/services", headers=boss)

    assert response.status_code == 200
    states = {s["id"]: (s["state"], s["reason"]) for s in response.json()}
    assert states["s3"] == ("down", "ConnectionError")
    assert states["database"] == ("ok", None)
    assert states["onlyoffice"] == ("not_configured", None)


async def test__storage__cached_and_refreshable(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)
    c = stack.client

    one = (await c.get("/api/admin/storage", headers=boss)).json()
    two = (await c.get("/api/admin/storage", headers=boss)).json()
    fresh = (await c.get("/api/admin/storage?refresh=true", headers=boss)).json()

    assert one == two
    assert fresh["blob_count"] == 2
    assert stack.storage.reads == 2


async def test__ai_providers__crud_never_returns_key(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)
    c = stack.client
    body = {
        "name": "LAN",
        "type": "openai_compat",
        "api_key": "sk-top-secret",
        "base_url": "http://10.0.0.5:8000/v1",
        "models": ["m1"],
        "ssl_verify": False,
        "connect_timeout_s": 5,
        "request_timeout_s": 30,
    }

    created = await c.post("/api/admin/ai-providers", json=body, headers=boss)
    provider_id = created.json()["id"]
    listed = await c.get("/api/admin/ai-providers", headers=boss)
    patched = await c.patch(
        f"/api/admin/ai-providers/{provider_id}",
        json={
            "name": "LAN2",
            "type": None,
            "api_key": "",
            "clear_key": False,
            "base_url": None,
            "models": None,
            "ssl_verify": None,
            "connect_timeout_s": None,
            "request_timeout_s": None,
        },
        headers=boss,
    )
    checked = await c.post(f"/api/admin/ai-providers/{provider_id}/check", headers=boss)
    blocked = await c.post(
        "/api/admin/ai-providers", json={**body, "base_url": "http://169.254.169.254/latest"}, headers=boss
    )
    deleted = await c.delete(f"/api/admin/ai-providers/{provider_id}", headers=boss)

    assert created.status_code == 201
    everything = created.text + listed.text + patched.text
    assert "sk-top-secret" not in everything
    assert listed.json()["items"][0]["key_set"] is True
    assert listed.json()["total"] == 1
    assert patched.json()["name"] == "LAN2"
    assert patched.json()["key_set"] is True
    assert checked.json() == {"ok": True, "models": ["m1"], "error": None}
    assert blocked.status_code == 422
    assert deleted.status_code == 204
    assert (await c.get(f"/api/admin/ai-providers/{provider_id}", headers=boss)).status_code == 404
    assert [e.action for e in reversed(await stack.users.audit.list())] == [
        "settings.ai_provider_create",
        "settings.ai_provider_update",
        "settings.ai_provider_delete",
    ]
    assert "sk-top-secret" not in str([e.details for e in await stack.users.audit.list()])


async def test__runner_token__secret_and_command_shown_once(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)
    c = stack.client

    created = (await c.post("/api/admin/runner-tokens", json={"label": "vm"}, headers=boss)).json()
    listed = (await c.get("/api/admin/runner-tokens", headers=boss)).text

    assert created["secret"].startswith("hsrt_")
    assert created["secret"] in created["command"]
    assert "hse-doc-studio runner" in created["command"]
    assert created["secret"] not in listed
    assert "hse-doc-studio runner" not in listed


async def test__runner_token__install_commands_carry_secret_once_and_never_cache(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)
    c = stack.client

    response = await c.post("/api/admin/runner-tokens", json={"label": "vm"}, headers=boss)
    created = response.json()
    secret = created["secret"]

    assert response.headers["cache-control"] == "no-store"
    assert secret in created["docker_command"]
    assert created["docker_command"].startswith("docker run ")
    assert "HSE_RUNNER__TOKEN=" + secret in created["docker_command"]
    assert created["script_command"].startswith("curl -fsSL ")
    assert "/api/runner/v1/install.sh" in created["script_command"]
    assert " | sudo env " in created["script_command"]
    assert " | env " in created["script_command_macos"]
    assert "sudo" not in created["script_command_macos"]
    assert secret in created["script_command"]
    listed = (await c.get("/api/admin/runner-tokens", headers=boss)).text
    assert secret not in listed
    assert "install.sh" not in listed


async def test__runner_token__install_commands_require_admin(stack: _Stack) -> None:
    plain = await stack.users.add("plain")

    response = await stack.client.post("/api/admin/runner-tokens", json={"label": "vm"}, headers=plain)

    assert response.status_code == 404
    assert "install.sh" not in response.text


async def test__runners__list_has_status(stack: _Stack) -> None:
    from hse_doc_studio.core.jobs.wire import RUNNER_PROTOCOL_VERSION, RunnerRegisterRequest  # noqa: PLC0415

    boss = await stack.users.add("boss", admin=True)
    created = await stack.registry.create_registration_token(_admin_actor(), label="t")
    await stack.registry.register(
        created.secret,
        RunnerRegisterRequest(
            name="r1",
            protocol=RUNNER_PROTOCOL_VERSION,
            version="1",
            tags=frozenset({"office"}),
            concurrency=1,
            resource_class="standard",
        ),
    )

    runners = (await stack.client.get("/api/admin/runners", headers=boss)).json()

    assert [(r["name"], r["status"]) for r in runners["items"]] == [("r1", "online")]
    assert runners["total"] == 1


def _admin_actor():  # type: ignore[no-untyped-def]
    from hse_doc_studio.core.access.entities import Actor, ActorKind  # noqa: PLC0415

    return Actor(kind=ActorKind.user, id="boss", is_instance_admin=True)


async def _finished(stack: _Stack, job_id: str, headers: Any) -> dict[str, Any]:
    for _ in range(200):
        job = (await stack.client.get(f"/api/admin/runner-install/jobs/{job_id}", headers=headers)).json()
        if job["state"] != "running":
            return job
        await asyncio.sleep(0.01)
    raise AssertionError("install job did not finish")


async def _register_like_runner(stack: _Stack) -> None:
    """Раннер на той стороне: берёт переданный ему токен и тратит его, как при регистрации."""
    for _ in range(200):
        if stack.install_host.specs:
            digest = hash_runner_secret(stack.install_host.specs[0].token)
            await stack.tokens.consume(digest, datetime.now(UTC))
            return
        await asyncio.sleep(0.01)


async def test__runner_install__capabilities_report_each_host_with_reason(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)

    response = await stack.client.get("/api/admin/runner-install/local", headers=boss)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "docker": {"available": True, "reason": None},
        "kubernetes": {"available": False, "reason": "disabled"},
    }


async def test__runner_install__unavailable_host_is_refused_with_reason(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)

    response = await stack.client.post("/api/admin/runner-install/local/kubernetes", json={}, headers=boss)

    assert response.status_code == 409
    assert response.json()["detail"] == {"code": "install_unavailable", "reason": "disabled"}
    assert await stack.tokens.list() == []


async def test__runner_install__resource_limits_from_the_form_reach_the_host_and_audit(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)
    body = {"resources": {"build_memory": "6Gi", "build_cpu": "3"}}

    started = await stack.client.post("/api/admin/runner-install/local/docker", json=body, headers=boss)
    await _register_like_runner(stack)
    await _finished(stack, started.json()["id"], boss)

    assert started.status_code == 202
    resources = stack.install_host.specs[0].resources
    assert resources is not None
    assert (resources.build_memory, resources.build_cpu, resources.runner_memory) == ("6Gi", "3", None)
    audit = [e for e in await stack.users.audit.list() if e.action == "runner_install.local.start"]
    assert audit[0].details["resources"] == {"build_cpu": "3", "build_memory": "6Gi"}


async def test__runner_install__resource_limits_out_of_bounds_are_422_before_any_token(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)
    stack.install_host.reject_field = "build_memory"

    response = await stack.client.post(
        "/api/admin/runner-install/local/docker", json={"resources": {"build_memory": "999Gi"}}, headers=boss
    )

    assert response.status_code == 422
    assert response.json()["detail"] == {"code": "invalid_resources", "field": "build_memory", "reason": "max"}
    assert await stack.tokens.list() == []


async def test__runner_install__garbage_quantity_is_rejected_by_the_schema(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)

    response = await stack.client.post(
        "/api/admin/runner-install/local/docker", json={"resources": {"build_cpu": "lots; rm -rf"}}, headers=boss
    )

    assert response.status_code == 422
    assert await stack.tokens.list() == []


async def test__runner_install__success_flow_never_leaks_the_token(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)

    started = await stack.client.post(
        "/api/admin/runner-install/local/docker", json={"name": "Lab Box", "concurrency": 2}, headers=boss
    )
    await _register_like_runner(stack)
    job = await _finished(stack, started.json()["id"], boss)

    assert started.status_code == 202
    assert job["state"] == "succeeded"
    assert [s["key"] for s in job["steps"]] == ["token", "pull", "start", "register"]
    assert all(s["state"] == "done" for s in job["steps"])
    spec = stack.install_host.specs[0]
    assert spec.name.startswith("lab-box-")
    assert spec.concurrency == 2
    assert spec.image == "registry.example/hds:1.2.3"
    assert spec.data_dir == f"/var/lib/hse-runner/{spec.name}"
    assert spec.token.startswith("hsrt_")
    everything = started.text + str(job) + str([(e.action, e.details) for e in await stack.users.audit.list()])
    assert spec.token not in everything
    actions = [e.action for e in await stack.users.audit.list()]
    assert "runner_install.local.start" in actions
    assert "runner_install.local.succeeded" in actions


async def test__runner_install__failure_revokes_the_token_and_explains(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)
    stack.install_host.fail_with = InstallError("image_pull_failed", "pull access denied")

    started = await stack.client.post("/api/admin/runner-install/local/docker", json={}, headers=boss)
    job = await _finished(stack, started.json()["id"], boss)

    assert job["state"] == "failed"
    assert job["error_code"] == "image_pull_failed"
    assert job["error_detail"] == "pull access denied"
    assert [s["state"] for s in job["steps"]][:2] == ["done", "failed"]
    assert all(t.revoked_at is not None for t in await stack.tokens.list())
    assert "runner_install.local.failed" in [e.action for e in await stack.users.audit.list()]


async def test__runner_install__register_timeout_is_reported(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)

    started = await stack.client.post("/api/admin/runner-install/local/docker", json={}, headers=boss)
    job = await _finished(stack, started.json()["id"], boss)

    assert job["state"] == "failed"
    assert job["error_code"] == "register_timeout"


async def test__runner_install__second_install_while_running_is_busy(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)

    first = await stack.client.post("/api/admin/runner-install/local/docker", json={}, headers=boss)
    second = await stack.client.post("/api/admin/runner-install/local/docker", json={}, headers=boss)

    assert first.status_code == 202
    assert second.status_code == 409
    assert second.json()["detail"] == {"code": "install_busy"}
    await _finished(stack, first.json()["id"], boss)


async def test__runner_install__invalid_input_is_rejected(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)
    c = stack.client

    assert (
        await c.post("/api/admin/runner-install/local/docker", json={"concurrency": 99}, headers=boss)
    ).status_code == 422
    assert (await c.post("/api/admin/runner-install/local/ssh", json={}, headers=boss)).status_code == 422
    assert (await c.post("/api/admin/runner-install/local/docker", json={"x": 1}, headers=boss)).status_code == 422
    assert (await c.get(f"/api/admin/runner-install/jobs/{uuid4()}", headers=boss)).status_code == 404


async def test__runner_install__instances_list_and_remove_are_audited(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)
    stack.install_host.instances = [LocalInstance(InstallTarget.docker, "hse-runner-abc123", "img:1", "running", None)]

    listed = (await stack.client.get("/api/admin/runner-install/local/instances", headers=boss)).json()
    missing = await stack.client.delete("/api/admin/runner-install/local/docker/nope", headers=boss)
    removed = await stack.client.delete("/api/admin/runner-install/local/docker/hse-runner-abc123", headers=boss)

    assert listed[0]["name"] == "hse-runner-abc123"
    assert missing.status_code == 404
    assert removed.status_code == 204
    assert stack.install_host.removed == ["hse-runner-abc123"]
    assert "runner_install.local.remove" in [e.action for e in await stack.users.audit.list()]


# ---- Обновление раннера из админки на месте ----


async def _installed_runner(stack: _Stack, *, version: str = "1.0.0", name: str = "hse-runner-abc123") -> str:
    """Установка из админки и её раннер в Студии (имя раннера задаёт установка)."""
    stack.install_host.instances = [
        LocalInstance(InstallTarget.docker, name, f"registry.example/hds:{version}", "running", None)
    ]
    return await _registered(stack, version=version, name=name)


def _comes_back(stack: _Stack, runner_id: str, version: str = "1.2.3") -> None:
    """Новый процесс раннера после перезапуска: тот же id (личность на томе), новая версия."""

    async def announce() -> None:
        await asyncio.sleep(0.02)
        await stack.runners.touch(runner_id, datetime.now(UTC), version=version)

    async def started() -> None:
        # Новый процесс объявляется сам, уже после того как хост закончил свои шаги.
        task = asyncio.create_task(announce())
        stack.background.add(task)

    stack.install_host.on_upgraded = started


async def test__runner_upgrade__keeps_the_runner_and_records_versions(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)
    runner_id = await _installed_runner(stack)
    tokens_before = len(await stack.tokens.list())
    _comes_back(stack, runner_id)

    listed = (await stack.client.get("/api/admin/runner-install/local/instances", headers=boss)).json()
    started = await stack.client.post("/api/admin/runner-install/local/docker/hse-runner-abc123/upgrade", headers=boss)
    job = await _finished(stack, started.json()["id"], boss)

    assert listed[0]["runner_id"] == runner_id
    assert (listed[0]["runner_version"], listed[0]["studio_version"], listed[0]["outdated"]) == ("1.0.0", "1.2.3", True)
    assert started.status_code == 202
    assert started.headers["cache-control"] == "no-store"
    assert job["state"] == "succeeded", job
    assert [(s["key"], s["state"]) for s in job["steps"]] == [
        ("pull", "done"),
        ("recreate", "done"),
        ("reconnect", "done"),
    ]
    assert stack.install_host.upgraded == [("hse-runner-abc123", "registry.example/hds:1.2.3")]
    # Ни нового токена регистрации, ни новой записи раннера.
    assert len(await stack.tokens.list()) == tokens_before
    assert [r.id for r in await stack.runners.list()] == [runner_id]
    events = {e.action: e for e in await stack.users.audit.list()}
    start = events["runner_install.local.upgrade"]
    assert start.target == "hse-runner-abc123"
    assert (start.details["from_version"], start.details["to_version"]) == ("1.0.0", "1.2.3")
    done = events["runner_install.local.upgrade_succeeded"]
    assert (done.details["from_version"], done.details["to_version"]) == ("1.0.0", "1.2.3")
    assert done.details["from_image"] == "registry.example/hds:1.0.0"
    assert done.details["to_image"] == "registry.example/hds:1.2.3"


async def test__runner_upgrade__same_version_is_allowed_and_not_outdated(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)
    runner_id = await _installed_runner(stack, version="1.2.3")
    _comes_back(stack, runner_id)

    listed = (await stack.client.get("/api/admin/runner-install/local/instances", headers=boss)).json()
    started = await stack.client.post("/api/admin/runner-install/local/docker/hse-runner-abc123/upgrade", headers=boss)
    job = await _finished(stack, started.json()["id"], boss)

    assert listed[0]["outdated"] is False
    assert job["state"] == "succeeded"


async def test__runner_upgrade__runner_that_does_not_come_back_is_a_timeout(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)
    await _installed_runner(stack)

    started = await stack.client.post("/api/admin/runner-install/local/docker/hse-runner-abc123/upgrade", headers=boss)
    job = await _finished(stack, started.json()["id"], boss)

    assert job["state"] == "failed"
    assert job["error_code"] == "reconnect_timeout"
    assert job["steps"][-1] == {"key": "reconnect", "state": "failed", "detail": ""}
    failed = [e for e in await stack.users.audit.list() if e.action == "runner_install.local.upgrade_failed"]
    assert failed[0].details["code"] == "reconnect_timeout"
    assert failed[0].details["from_version"] == "1.0.0"


async def test__runner_upgrade__host_failure_is_reported(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)
    await _installed_runner(stack)
    stack.install_host.upgrade_fail_with = InstallError("image_pull_failed", "pull access denied")

    started = await stack.client.post("/api/admin/runner-install/local/docker/hse-runner-abc123/upgrade", headers=boss)
    job = await _finished(stack, started.json()["id"], boss)

    assert (job["state"], job["error_code"], job["error_detail"]) == (
        "failed",
        "image_pull_failed",
        "pull access denied",
    )
    assert [s["state"] for s in job["steps"]] == ["failed", "pending", "pending"]


async def test__runner_upgrade__install_without_runner_skips_the_reconnect_step(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)
    stack.install_host.instances = [LocalInstance(InstallTarget.docker, "hse-runner-orphan", "img:1", "restarting")]

    listed = (await stack.client.get("/api/admin/runner-install/local/instances", headers=boss)).json()
    started = await stack.client.post("/api/admin/runner-install/local/docker/hse-runner-orphan/upgrade", headers=boss)
    job = await _finished(stack, started.json()["id"], boss)

    assert (listed[0]["runner_id"], listed[0]["outdated"]) == (None, False)
    assert job["state"] == "succeeded"
    assert job["steps"][-1]["state"] == "skipped"


async def test__runner_upgrade__shares_the_lock_with_install_and_needs_an_install(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)
    await _installed_runner(stack)
    stack.install_host.upgrade_gate = asyncio.Event()
    path = "/api/admin/runner-install/local/docker/hse-runner-abc123/upgrade"

    first = await stack.client.post(path, headers=boss)
    again = await stack.client.post(path, headers=boss)
    install = await stack.client.post("/api/admin/runner-install/local/docker", json={}, headers=boss)
    missing = await stack.client.post("/api/admin/runner-install/local/docker/nope/upgrade", headers=boss)
    disabled = await stack.client.post(
        "/api/admin/runner-install/local/kubernetes/hse-runner-abc123/upgrade", headers=boss
    )
    stack.install_host.upgrade_gate.set()
    await _finished(stack, first.json()["id"], boss)

    assert first.status_code == 202
    assert (again.status_code, again.json()["detail"]) == (409, {"code": "install_busy"})
    assert (install.status_code, install.json()["detail"]) == (409, {"code": "install_busy"})
    assert missing.status_code == 404
    assert (disabled.status_code, disabled.json()["detail"]["code"]) == (409, "install_unavailable")


# ---- Как развёрнут раннер и изоляция раннеров в кластере ----


async def _registered(stack: _Stack, *, version: str = "0.14.0", name: str = "r1") -> str:
    from hse_doc_studio.core.jobs.wire import RUNNER_PROTOCOL_VERSION, RunnerRegisterRequest  # noqa: PLC0415

    created = await stack.registry.create_registration_token(_admin_actor(), label="t")
    registered = await stack.registry.register(
        created.secret,
        RunnerRegisterRequest(
            name=name,
            protocol=RUNNER_PROTOCOL_VERSION,
            version=version,
            tags=frozenset({"tex"}),
            concurrency=1,
            resource_class="standard",
        ),
    )
    return registered.runner.id


async def test__runner_deployment__old_runner_has_no_data_and_a_reinstall_hint(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)
    runner_id = await _registered(stack, version="0.13.2")

    response = await stack.client.get(f"/api/admin/runners/{runner_id}/deployment", headers=boss)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["report"] is None
    assert body["live"] is None
    assert body["live_status"] == "not_applicable"
    assert body["outdated"] is True
    assert body["limits_supported"] is False
    assert body["reinstall"] == ["before_limits"]
    assert body["origin"] is None
    listed = (await stack.client.get("/api/admin/runners", headers=boss)).json()["items"][0]
    assert listed["reinstall"] == ["before_limits"]
    assert listed["deployment_reported"] is False


async def test__runner_deployment__report_is_shown_with_its_source_and_origin(stack: _Stack) -> None:
    from dataclasses import replace  # noqa: PLC0415

    boss = await stack.users.add("boss", admin=True)
    runner_id = await _registered(stack)
    runner = await stack.runners.get(runner_id)
    assert runner is not None
    await stack.registry.report_deployment(runner, make_report())
    stack.isolation = replace(stack.isolation, declared=make_declared())

    body = (await stack.client.get(f"/api/admin/runners/{runner_id}/deployment", headers=boss)).json()

    assert body["origin"] == "chart"
    assert body["reinstall"] == []
    report = body["report"]
    assert report["reported_at"] is not None
    assert report["executor"] == "kubernetes"
    assert report["resources"]["source"] == "pod"
    assert report["resources"]["memory_limit"] == "2048Mi"
    assert report["build"]["namespace"] == "studio-builds"
    assert report["build"]["security"]["automount_token"] is False
    listed = (await stack.client.get("/api/admin/runners", headers=boss)).json()["items"][0]
    assert listed["deployment_reported"] is True


async def test__runner_deployment__live_deployment_of_an_admin_installed_runner(stack: _Stack) -> None:
    from dataclasses import replace  # noqa: PLC0415

    from hse_doc_studio.core.jobs.deployment import SecurityFacts  # noqa: PLC0415
    from hse_doc_studio.core.runner_isolation import DeploymentListing, LiveDeployment, LookupStatus  # noqa: PLC0415

    boss = await stack.users.add("boss", admin=True)
    runner_id = await _registered(stack, name="builds-a")
    stack.isolation = replace(stack.isolation, install=make_install_facts(enabled=True, service_account="rel-ui"))
    stack.cluster.listing = DeploymentListing(
        LookupStatus.ok,
        (
            LiveDeployment(
                name="builds-a", namespace="studio", image="img:0.13.0", ready=True, security=SecurityFacts()
            ),
        ),
    )

    body = (await stack.client.get(f"/api/admin/runners/{runner_id}/deployment", headers=boss)).json()

    assert body["live_status"] == "ok"
    assert body["origin"] == "ui"
    assert body["live"]["image"] == "img:0.13.0"
    assert body["live"]["resources"] is None
    assert body["reinstall"] == ["no_pod_limits"]
    stack.cluster.listing = DeploymentListing(LookupStatus.forbidden)
    stack.cluster.listed = 0
    body = (await stack.client.get(f"/api/admin/runners/{runner_id}/deployment", headers=boss)).json()
    assert body["live_status"] == "forbidden"
    assert body["live"] is None


async def test__runner_deployment__unknown_and_personal_runners_are_404(stack: _Stack) -> None:
    from dataclasses import replace  # noqa: PLC0415

    from hse_doc_studio.core.jobs.runners import RunnerOwnerKind  # noqa: PLC0415

    boss = await stack.users.add("boss", admin=True)
    runner_id = await _registered(stack)
    runner = await stack.runners.get(runner_id)
    assert runner is not None
    await stack.runners.add(replace(runner, owner_kind=RunnerOwnerKind.user, owner_id="anna"))

    assert (await stack.client.get("/api/admin/runners/nope/deployment", headers=boss)).status_code == 404
    assert (await stack.client.get(f"/api/admin/runners/{runner_id}/deployment", headers=boss)).status_code == 404


async def test__runners_isolation__without_helm_shows_only_install_settings(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)

    response = await stack.client.get("/api/admin/runners/isolation", headers=boss)

    assert response.status_code == 200
    body = response.json()
    assert body["config"] == "none"
    assert body["live_read"] == "off"
    assert body["chart_runner"] is None
    assert body["network"] is None
    assert body["install_from_ui"]["bounds"]["max_memory"] == "16Gi"
    assert body["install_from_ui"]["runner"]["ephemeral_limit"] == "2Gi"
    assert stack.cluster.asked == []


async def test__runners_isolation__config_is_not_presented_as_checked(stack: _Stack) -> None:
    from dataclasses import replace  # noqa: PLC0415

    boss = await stack.users.add("boss", admin=True)
    stack.isolation = replace(stack.isolation, declared=make_declared())

    body = (await stack.client.get("/api/admin/runners/isolation", headers=boss)).json()

    assert body["config"] == "helm"
    assert body["live_read"] == "off"
    assert body["checked_at"] is None
    assert body["build"]["namespace"] == "builds"
    assert body["chart_runner"]["security"]["read_only_root"] is True
    assert body["chart_runner"]["docker_socket"] is False
    assert body["network"]["build_deny_all"] == {"declared": True, "live": None}
    assert body["network"]["runner_egress"]["extra_rules"] == 2
    assert body["quota"]["declared"] == {"pods": "20", "limits.memory": "80Gi"}
    assert body["quota"]["live_found"] is None
    assert body["limit_range"]["declared"] is None
    assert body["pod_security"] is None
    assert stack.cluster.asked == []


async def test__runners_isolation__live_state_is_read_when_allowed(stack: _Stack) -> None:
    from dataclasses import replace  # noqa: PLC0415

    from hse_doc_studio.core.runner_isolation import (  # noqa: PLC0415
        ClusterTargets,
        LiveClusterState,
        LiveQuota,
        LiveStatus,
        NamespaceSecurity,
    )

    boss = await stack.users.add("boss", admin=True)
    stack.isolation = replace(stack.isolation, declared=make_declared(), read_live=True)
    stack.cluster.state = LiveClusterState(
        status=LiveStatus.partial,
        checked_at=datetime.now(UTC),
        build_deny_all=False,
        quota_checked=True,
        quota=LiveQuota(name="rel-builds", hard={"pods": "20"}, used={"pods": "3"}),
        limit_range_checked=True,
        namespaces=(NamespaceSecurity(namespace="studio", enforce="restricted"),),
    )

    body = (await stack.client.get("/api/admin/runners/isolation", headers=boss)).json()

    assert stack.cluster.asked == [
        ClusterTargets(release_namespace="studio", build_namespace="builds", ui_build_namespace="studio")
    ]
    assert body["live_read"] == "partial"
    assert body["checked_at"] is not None
    assert body["network"]["build_deny_all"] == {"declared": True, "live": False}
    assert body["quota"]["live_used"] == {"pods": "3"}
    assert body["limit_range"]["live_found"] is False
    assert body["pod_security"][0]["enforce"] == "restricted"


async def test__runners_isolation__ui_builds_in_their_own_namespace(stack: _Stack) -> None:
    from dataclasses import replace  # noqa: PLC0415

    from hse_doc_studio.core.runner_isolation import (  # noqa: PLC0415
        ClusterTargets,
        LiveClusterState,
        LiveLimitRange,
        LiveQuota,
        LiveStatus,
    )

    boss = await stack.users.add("boss", admin=True)
    declared = make_declared(
        uiBuild={"enabled": True, "namespace": "ui-builds", "networkPolicy": True, "quota": True, "limitRange": True}
    )
    stack.isolation = replace(
        stack.isolation,
        declared=declared,
        install=make_install_facts(enabled=True, service_account="rel-ui", build_namespace="ui-builds"),
        read_live=True,
    )
    stack.cluster.state = LiveClusterState(
        status=LiveStatus.ok,
        checked_at=datetime.now(UTC),
        ui_build_deny_all=True,
        quota_checked=True,
        ui_quota_checked=True,
        ui_quota=LiveQuota(name="rel-builds", hard={"pods": "20"}, used={"pods": "1"}),
        ui_limit_range_checked=True,
        ui_limit_range=LiveLimitRange(name="rel-builds", max={"cpu": "8"}),
    )

    body = (await stack.client.get("/api/admin/runners/isolation", headers=boss)).json()

    assert stack.cluster.asked == [
        ClusterTargets(release_namespace="studio", build_namespace="builds", ui_build_namespace="ui-builds")
    ]
    assert body["install_from_ui"]["namespace"] == "studio"
    assert body["install_from_ui"]["build_namespace"] == "ui-builds"
    assert body["network"]["ui_build_deny_all"] == {"declared": True, "live": True}
    assert body["quota"]["namespace"] == "builds"
    assert body["ui_quota"]["namespace"] == "ui-builds"
    assert body["ui_quota"]["declared"] == {"pods": "20", "limits.memory": "80Gi"}
    assert body["ui_quota"]["live_used"] == {"pods": "1"}
    assert body["ui_limit_range"]["namespace"] == "ui-builds"
    assert body["ui_limit_range"]["declared"] == {"default": {}, "default_request": {}, "max": {}}
    assert body["ui_limit_range"]["live"]["max"] == {"cpu": "8"}


async def test__runners_isolation__shared_build_namespace_shows_one_quota(stack: _Stack) -> None:
    from dataclasses import replace  # noqa: PLC0415

    boss = await stack.users.add("boss", admin=True)
    # Раннер чарта docker: его квоты нет, но namespace подов сборки раннеров из админки тот же, и квота там одна.
    declared = make_declared(
        uiBuild={"enabled": True, "namespace": "builds", "networkPolicy": False, "quota": True, "limitRange": False}
    )
    declared = declared.model_copy(
        update={
            "runner": declared.runner.model_copy(update={"executor": "docker"}),
            "build": declared.build.model_copy(
                update={"quota": declared.build.quota.model_copy(update={"enabled": False})}
            ),
        }
    )
    stack.isolation = replace(
        stack.isolation,
        declared=declared,
        install=make_install_facts(enabled=True, service_account="rel-ui", build_namespace="builds"),
    )

    body = (await stack.client.get("/api/admin/runners/isolation", headers=boss)).json()

    assert body["quota"]["namespace"] == "builds"
    assert body["quota"]["declared"] == {"pods": "20", "limits.memory": "80Gi"}
    assert body["ui_quota"] is None
    assert body["ui_limit_range"] is None
    assert body["network"]["ui_build_deny_all"] == {"declared": False, "live": None}


async def test__runners_isolation__old_chart_without_ui_build_keeps_builds_in_the_release(stack: _Stack) -> None:
    from dataclasses import replace  # noqa: PLC0415

    boss = await stack.users.add("boss", admin=True)
    stack.isolation = replace(
        stack.isolation,
        declared=make_declared(),
        install=make_install_facts(enabled=True, service_account="rel-ui"),
    )

    body = (await stack.client.get("/api/admin/runners/isolation", headers=boss)).json()

    assert body["install_from_ui"]["build_namespace"] == "studio"
    assert body["network"]["ui_build_deny_all"] == {"declared": True, "live": None}
    assert body["ui_quota"]["namespace"] == "studio"
    assert body["ui_quota"]["declared"] is None


async def test__runner_isolation__answers_carry_no_secrets(stack: _Stack) -> None:
    from dataclasses import replace  # noqa: PLC0415

    boss = await stack.users.add("boss", admin=True)
    created = await stack.registry.create_registration_token(_admin_actor(), label="t")
    runner_id = await _registered(stack)
    runner = await stack.runners.get(runner_id)
    assert runner is not None
    await stack.registry.report_deployment(runner, make_report())
    stack.isolation = replace(stack.isolation, declared=make_declared())

    texts = [
        (await stack.client.get(f"/api/admin/runners/{runner_id}/deployment", headers=boss)).text,
        (await stack.client.get("/api/admin/runners/isolation", headers=boss)).text,
    ]

    for text in texts:
        assert created.secret not in text
        assert "hsrn_" not in text
        assert "hsrt_" not in text
        assert "token_hash" not in text
