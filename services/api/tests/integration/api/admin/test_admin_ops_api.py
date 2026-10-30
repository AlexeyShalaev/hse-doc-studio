"""`/api/admin` эксплуатации: очередь, квоты, сервисы, место, политика подписи, общие ИИ-провайдеры, токены раннеров."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

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
from hse_doc_studio.core.mode import StudioMode
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
from hse_doc_studio.use_cases.admin.ops_queue import CancelJobUC, ListQueueUC, QueueSummaryUC
from hse_doc_studio.use_cases.admin.ops_quotas import GetQuotasUC, QuotaService, UpdateQuotasUC
from hse_doc_studio.use_cases.admin.ops_services import ServicesOverviewUC
from hse_doc_studio.use_cases.admin.ops_signing import GetSigningPolicyUC, UpdateSigningPolicyUC
from hse_doc_studio.use_cases.admin.ops_storage import GetStorageUsageUC
from hse_doc_studio.use_cases.identity.smtp_settings import SmtpSettingsService
from hse_doc_studio.use_cases.jobs.queue_service import JobQueueService
from hse_doc_studio.use_cases.jobs.runners import RunnerRegistry
from httpx import ASGITransport, AsyncClient

from tests.fakes.auth import empty_bearer_resolver
from tests.fakes.identity import InMemoryInstanceSettingsRepository
from tests.fakes.job_queue import InMemoryJobQueue
from tests.fakes.ops import CountingStorageReader, InMemoryJobAdminReader, NoopUow, ReversingCipher
from tests.fakes.runners import InMemoryRegistrationTokenRepository, InMemoryRunnerRepository
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
        self.health = HealthRegistry()
        self.quotas = QuotaService(self.settings, ttl_s=0)
        self.store = InstanceAiProviderStore(self.settings, ReversingCipher())
        self.registry = RunnerRegistry(self.runners, InMemoryRegistrationTokenRepository(), users.audit, NoopUow())
        self.smtp = SmtpSettingsService(self.settings, ReversingCipher())  # type: ignore[arg-type]
        self.client: AsyncClient


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
    def list_queue(self) -> ListQueueUC:
        return ListQueueUC(InMemoryJobAdminReader(self.s.queue))

    @provide
    def queue_summary(self) -> QueueSummaryUC:
        return QueueSummaryUC(InMemoryJobAdminReader(self.s.queue))

    @provide
    def cancel(self) -> CancelJobUC:
        return CancelJobUC(self.s.queue, JobQueueService(self.s.queue), self.s.users.audit, NoopUow())

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
    def get_signing(self) -> GetSigningPolicyUC:
        return GetSigningPolicyUC(self.s.settings)

    @provide
    def update_signing(self) -> UpdateSigningPolicyUC:
        return UpdateSigningPolicyUC(self.s.settings, self.s.users.audit, NoopUow())

    @provide
    def list_providers(self) -> ListInstanceAiProvidersUC:
        return ListInstanceAiProvidersUC(self.s.store)

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
        yield s
    await container.close()


def _enqueue(user: object = None) -> EnqueueRequest:
    return EnqueueRequest(
        job_id=uuid4(),
        kind=JobKind.compile,
        project_id=uuid4(),
        user_id=user or uuid4(),  # type: ignore[arg-type]
        tags=frozenset({"tex"}),
        payload={},
    )


_ROUTES: list[tuple[str, str, Any]] = [
    ("GET", "/api/admin/queue", None),
    ("GET", "/api/admin/queue/summary", None),
    ("POST", f"/api/admin/queue/{uuid4()}/cancel", None),
    ("GET", "/api/admin/quotas", None),
    ("PUT", "/api/admin/quotas", {"user_concurrent": 1, "org_concurrent": None, "max_duration_s": None}),
    ("GET", "/api/admin/services", None),
    ("GET", "/api/admin/storage", None),
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

    assert (await c.get("/api/admin/settings/signing", headers=boss)).json() == {"server_keys": "forbidden"}
    assert (await c.put("/api/admin/settings/signing", json={"server_keys": "yes"}, headers=boss)).status_code == 422
    await c.put("/api/admin/settings/signing", json={"server_keys": "allowed"}, headers=boss)

    assert (await c.get("/api/admin/settings/signing", headers=boss)).json() == {"server_keys": "allowed"}
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
    assert listed.json()[0]["key_set"] is True
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

    assert [(r["name"], r["status"]) for r in runners] == [("r1", "online")]


def _admin_actor():  # type: ignore[no-untyped-def]
    from hse_doc_studio.core.access.entities import Actor, ActorKind  # noqa: PLC0415

    return Actor(kind=ActorKind.user, id="boss", is_instance_admin=True)
