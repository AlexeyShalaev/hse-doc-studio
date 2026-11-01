"""`/api/admin` квоты по видам ресурсов: умолчания, переопределения, использование, сброс; `/api/v1/usage`."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import pytest_asyncio
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from fastapi import Depends, FastAPI, Request
from hse_doc_studio.api.actor import resolve_actor
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.guards import install_exception_handlers
from hse_doc_studio.api.routers.admin import make_admin_router
from hse_doc_studio.api.routers.v1 import usage as usage_router
from hse_doc_studio.core.access.context import set_current_actor
from hse_doc_studio.core.identity.protocols import IActorResolver
from hse_doc_studio.core.jobs.autoscale import QueueMetrics
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.core.orgs.entities import Org, OrgMember, OrgRole
from hse_doc_studio.core.quotas.kinds import QuotaKind
from hse_doc_studio.infra.identity.resolvers import ChainActorResolver, SessionCookieResolver
from hse_doc_studio.use_cases.admin.ops_quota_policy import (
    AdminOwnerUsageUC,
    AdminUsageSummaryUC,
    DeleteQuotaOverrideUC,
    GetQuotaPolicyUC,
    ListQuotaOverridesUC,
    ResetUsageUC,
    SetQuotaOverrideUC,
    UpdateQuotaPolicyUC,
)
from hse_doc_studio.use_cases.admin.ops_quotas import QuotaService
from hse_doc_studio.use_cases.jobs.autoscale import AutoscaleService, GetAutoscaleUC, UpdateAutoscaleUC
from hse_doc_studio.use_cases.quotas.gate import QuotaGate
from hse_doc_studio.use_cases.quotas.usage import GetMyUsageUC, GetOrgUsageUC
from httpx import ASGITransport, AsyncClient

from tests.fakes.auth import empty_bearer_resolver
from tests.fakes.identity import InMemoryInstanceSettingsRepository
from tests.fakes.job_quotas import InMemoryQuotaOverrides
from tests.fakes.ops import NoopUow
from tests.fakes.orgs import InMemoryOrgRepository, InMemoryOrgStore
from tests.fakes.quotas import InMemoryFootprint, InMemoryUsageCounters
from tests.integration.api.admin.test_admin_users_api import _Env as _UsersEnv

NOW = datetime(2026, 11, 10, 12, tzinfo=UTC)


async def _set_actor(request: Request) -> None:
    """Как в приложении: актор запроса приходит из сессии, а не из соседнего запроса."""
    set_current_actor(await resolve_actor(request))


class _Metrics:
    async def read(self, now: datetime) -> QueueMetrics:
        return QueueMetrics(queued=12, oldest_wait_s=40, running=2, runners_online=1, slots_total=2)


class _NoOrchestrator:
    def create(self, policy: object) -> None:
        return None


class _Stack:
    def __init__(self, users: _UsersEnv) -> None:
        self.users = users
        self.settings = InMemoryInstanceSettingsRepository()
        self.overrides = InMemoryQuotaOverrides()
        self.service = QuotaService(self.settings, self.overrides, ttl_s=0)
        self.counters = InMemoryUsageCounters()
        self.footprint = InMemoryFootprint()
        self.gate = QuotaGate(self.service, self.counters, self.footprint, clock=lambda: NOW)
        self.orgs = InMemoryOrgRepository(InMemoryOrgStore(users.store))
        self.autoscale = AutoscaleService(
            self.settings,
            _Metrics(),
            _NoOrchestrator(),
            users.audit,
            clock=lambda: NOW,  # type: ignore[arg-type]
        )
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
    def quota_service(self) -> QuotaService:
        return self.s.service

    @provide
    def gate(self) -> QuotaGate:
        return self.s.gate

    @provide
    def get_policy(self) -> GetQuotaPolicyUC:
        return GetQuotaPolicyUC(self.s.settings)

    @provide
    def update_policy(self) -> UpdateQuotaPolicyUC:
        return UpdateQuotaPolicyUC(self.s.settings, self.s.users.audit, NoopUow(), self.s.service)

    @provide
    def list_overrides(self) -> ListQuotaOverridesUC:
        return ListQuotaOverridesUC(self.s.overrides, self.s.users.users, self.s.orgs)

    @provide
    def set_override(self) -> SetQuotaOverrideUC:
        return SetQuotaOverrideUC(
            self.s.overrides, self.s.users.users, self.s.orgs, self.s.users.audit, NoopUow(), self.s.service
        )

    @provide
    def delete_override(self) -> DeleteQuotaOverrideUC:
        return DeleteQuotaOverrideUC(self.s.overrides, self.s.users.audit, NoopUow(), self.s.service)

    @provide
    def owner_usage(self) -> AdminOwnerUsageUC:
        return AdminOwnerUsageUC(self.s.gate, self.s.users.users, self.s.orgs)

    @provide
    def summary(self) -> AdminUsageSummaryUC:
        return AdminUsageSummaryUC(self.s.gate, self.s.users.users, self.s.orgs)

    @provide
    def reset(self) -> ResetUsageUC:
        return ResetUsageUC(self.s.gate, self.s.users.users, self.s.orgs, self.s.users.audit, NoopUow())

    @provide
    def get_autoscale(self) -> GetAutoscaleUC:
        return GetAutoscaleUC(self.s.autoscale)

    @provide
    def update_autoscale(self) -> UpdateAutoscaleUC:
        return UpdateAutoscaleUC(self.s.settings, self.s.users.audit, NoopUow(), self.s.autoscale)

    @provide
    def my_usage(self) -> GetMyUsageUC:
        return GetMyUsageUC(self.s.gate, self.s.orgs)

    @provide
    def org_usage(self) -> GetOrgUsageUC:
        return GetOrgUsageUC(self.s.gate, self.s.orgs)


@pytest_asyncio.fixture
async def stack(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[_Stack]:
    monkeypatch.setattr(settings, "mode", StudioMode.server)
    s = _Stack(_UsersEnv())
    app = FastAPI()
    app.include_router(make_admin_router())
    app.include_router(usage_router.router, prefix="/api/v1", dependencies=[Depends(_set_actor)])
    install_exception_handlers(app)
    container = make_async_container(_Provider(s), FastapiProvider())
    setup_dishka(container, app)
    async with AsyncClient(transport=ASGITransport(app=app, client=("203.0.113.9", 5000)), base_url="http://test") as c:
        s.client = c
        yield s
    await container.close()


_POLICY = {
    "defaults": [
        {"kind": "storage", "user": 1000, "org": 5000},
        {"kind": "builds", "user": 30, "org": None},
        {"kind": "ai_tokens_day", "user": None, "org": None},
        {"kind": "ai_tokens_month", "user": 200, "org": None},
        {"kind": "members", "user": 5, "org": None},
    ],
    "warn_percent": 75,
    "on_exceed": "reject",
}

_AUTOSCALE = {
    "mode": "compose",
    "min_runners": 1,
    "max_runners": 6,
    "target_queue_per_slot": 2.0,
    "scale_up_wait_s": 30,
    "cooldown_up_s": 60,
    "cooldown_down_s": 300,
    "idle_before_down_s": 300,
    "step_up": 2,
    "step_down": 1,
    "webhook_url": None,
}

_ROUTES = [
    ("GET", "/api/admin/autoscale", None),
    ("PUT", "/api/admin/autoscale", _AUTOSCALE),
    ("GET", "/api/admin/ai-gateway", None),
    ("GET", "/api/admin/quota-policy", None),
    ("PUT", "/api/admin/quota-policy", _POLICY),
    ("GET", "/api/admin/quota-overrides", None),
    (
        "PUT",
        "/api/admin/quota-overrides",
        {"owner_kind": "user", "owner_id": "x", "resource": "builds.month_user", "hard_limit": 1},
    ),
    ("DELETE", "/api/admin/quota-overrides?owner_kind=user&owner_id=x&resource=builds.month_user", None),
    ("GET", "/api/admin/usage?owner_kind=user&owner_id=x", None),
    ("GET", "/api/admin/usage/summary", None),
    ("POST", "/api/admin/usage/reset", {"owner_kind": "user", "owner_id": "x", "kind": "builds"}),
]


@pytest.mark.parametrize(("method", "path", "body"), _ROUTES, ids=[f"{m} {p[:45]}" for m, p, _ in _ROUTES])
async def test__quota_routes__student_404_anonymous_401(stack: _Stack, method: str, path: str, body: object) -> None:
    student = await stack.users.add(str(uuid4()))

    assert (await stack.client.request(method, path, json=body, headers=student)).status_code == 404
    assert (await stack.client.request(method, path, json=body)).status_code == 401
    assert await stack.users.audit.list() == []


async def test__policy__roundtrip_validates_and_audits(stack: _Stack) -> None:
    boss = await stack.users.add(str(uuid4()), admin=True)
    c = stack.client

    empty = (await c.get("/api/admin/quota-policy", headers=boss)).json()
    saved = await c.put("/api/admin/quota-policy", json=_POLICY, headers=boss)
    bad_percent = await c.put("/api/admin/quota-policy", json={**_POLICY, "warn_percent": 0}, headers=boss)
    bad_mode = await c.put("/api/admin/quota-policy", json={**_POLICY, "on_exceed": "explode"}, headers=boss)
    bad_value = await c.put(
        "/api/admin/quota-policy",
        json={**_POLICY, "defaults": [{"kind": "storage", "user": 0, "org": None}]},
        headers=boss,
    )

    assert empty["on_exceed"] == "deprioritize"
    assert all(d["user"] is None and d["org"] is None for d in empty["defaults"])
    assert saved.status_code == 200
    assert (await c.get("/api/admin/quota-policy", headers=boss)).json() == saved.json()
    assert saved.json()["warn_percent"] == 75
    assert {bad_percent.status_code, bad_mode.status_code, bad_value.status_code} == {422}
    assert [e.action for e in await stack.users.audit.list()] == ["settings.quota_policy_update"]


async def test__overrides__set_list_delete_with_names_and_validation(stack: _Stack) -> None:
    uid = str(uuid4())
    boss = await stack.users.add(str(uuid4()), admin=True)
    await stack.users.add(uid, name="Анна")
    c = stack.client
    body = {"owner_kind": "user", "owner_id": uid, "resource": "storage.bytes_user", "hard_limit": 50 * 1024**3}

    saved = await c.put("/api/admin/quota-overrides", json=body, headers=boss)
    listed = (await c.get("/api/admin/quota-overrides", headers=boss)).json()
    wrong_scope = await c.put(
        "/api/admin/quota-overrides", json={**body, "resource": "storage.bytes_org"}, headers=boss
    )
    unknown_owner = await c.put("/api/admin/quota-overrides", json={**body, "owner_id": "nobody"}, headers=boss)
    deleted = await c.delete(
        f"/api/admin/quota-overrides?owner_kind=user&owner_id={uid}&resource=storage.bytes_user", headers=boss
    )

    assert saved.status_code == 200
    assert saved.json()["owner_name"] == "Анна"
    assert [(o["owner_id"], o["hard_limit"]) for o in listed] == [(uid, 50 * 1024**3)]
    assert wrong_scope.status_code == 422
    assert unknown_owner.status_code == 404
    assert deleted.status_code == 204
    assert (await c.get("/api/admin/quota-overrides", headers=boss)).json() == []
    assert sorted(e.action for e in await stack.users.audit.list()) == ["quota.override_delete", "quota.override_set"]


async def test__usage__my_page_shows_limits_sources_and_org_lines(stack: _Stack) -> None:
    uid = str(uuid4())
    me = await stack.users.add(uid)
    boss = await stack.users.add(str(uuid4()), admin=True)
    c = stack.client
    await c.put("/api/admin/quota-policy", json=_POLICY, headers=boss)
    await c.put(
        "/api/admin/quota-overrides",
        json={"owner_kind": "user", "owner_id": uid, "resource": "builds.month_user", "hard_limit": 4},
        headers=boss,
    )
    org = Org(id="org_1", slug="kafedra", name="Кафедра", created_at=NOW)
    await stack.orgs.add(org)
    await stack.orgs.add_member(OrgMember(org.id, uid, OrgRole.member, NOW))
    await stack.gate.charge(QuotaKind.builds, __import__("uuid").UUID(uid), None, 3)

    page = (await c.get("/api/v1/usage", headers=me)).json()
    by_kind = {line["kind"]: line for line in page["user"]["lines"]}
    org_page = await c.get("/api/v1/orgs/kafedra/usage", headers=me)
    stranger = await c.get("/api/v1/orgs/kafedra/usage", headers=await stack.users.add(str(uuid4())))

    assert page["warn_percent"] == 75
    assert (by_kind["builds"]["used"], by_kind["builds"]["limit"], by_kind["builds"]["source"]) == (3, 4, "user")
    assert by_kind["builds"]["state"] == "warning"
    assert by_kind["builds"]["resets_at"] == "2026-12-01T00:00:00Z"
    assert by_kind["ai_tokens_month"]["limit"] == 200
    assert by_kind["ai_tokens_day"]["state"] == "unlimited"
    assert by_kind["storage"]["resets_at"] is None
    assert [o["owner_name"] for o in page["orgs"]] == ["Кафедра"]
    assert org_page.status_code == 200
    assert stranger.status_code == 404


async def test__usage__admin_owner_summary_and_reset(stack: _Stack) -> None:
    uid = str(uuid4())
    await stack.users.add(uid, name="Борис")
    boss = await stack.users.add(str(uuid4()), admin=True)
    c = stack.client
    await stack.gate.charge(QuotaKind.builds, __import__("uuid").UUID(uid), None, 7)

    owner = (await c.get(f"/api/admin/usage?owner_kind=user&owner_id={uid}", headers=boss)).json()
    summary = (await c.get("/api/admin/usage/summary", headers=boss)).json()
    reset = await c.post(
        "/api/admin/usage/reset", json={"owner_kind": "user", "owner_id": uid, "kind": "builds"}, headers=boss
    )
    after = (await c.get("/api/admin/usage/summary", headers=boss)).json()

    assert owner["owner_name"] == "Борис"
    assert {line["kind"]: line["used"] for line in owner["lines"]}["builds"] == 7
    assert summary["totals"]["builds"] == 7
    assert summary["top_builds"] == [{"user_id": uid, "name": "Борис", "used": 7}]
    assert reset.status_code == 204
    assert after["totals"]["builds"] == 0
    assert [e.action for e in await stack.users.audit.list()] == ["usage.reset"]


async def test__usage__user_stored_as_hex_shares_counters_with_dashed_spelling(stack: _Stack) -> None:

    owner = uuid4()
    await stack.users.add(owner.hex, name="Вера")
    boss = await stack.users.add(str(uuid4()), admin=True)
    c = stack.client
    await stack.gate.charge(QuotaKind.builds, owner, None, 4)

    seen = (await c.get(f"/api/admin/usage?owner_kind=user&owner_id={owner}", headers=boss)).json()
    top = (await c.get("/api/admin/usage/summary", headers=boss)).json()["top_builds"]
    reset = await c.post(
        "/api/admin/usage/reset", json={"owner_kind": "user", "owner_id": owner.hex, "kind": "builds"}, headers=boss
    )

    assert {line["kind"]: line["used"] for line in seen["lines"]}["builds"] == 4
    assert top == [{"user_id": str(owner), "name": "Вера", "used": 4}]
    assert reset.status_code == 204
    assert await stack.counters.total(QuotaKind.builds, NOW.date().replace(day=1)) == 0


async def test__autoscale__put_persists_policy_and_status_shows_metrics_and_decision(stack: _Stack) -> None:
    boss = await stack.users.add(str(uuid4()), admin=True)
    c = stack.client

    initial = (await c.get("/api/admin/autoscale", headers=boss)).json()
    saved = await c.put("/api/admin/autoscale", json=_AUTOSCALE, headers=boss)
    bad_range = await c.put("/api/admin/autoscale", json={**_AUTOSCALE, "min_runners": 9}, headers=boss)
    bad_hook = await c.put(
        "/api/admin/autoscale", json={**_AUTOSCALE, "mode": "webhook", "webhook_url": None}, headers=boss
    )
    bad_url = await c.put("/api/admin/autoscale", json={**_AUTOSCALE, "webhook_url": "ftp://x"}, headers=boss)

    assert initial["policy"]["mode"] == "off"
    assert saved.status_code == 200
    body = saved.json()
    assert body["policy"]["max_runners"] == 6
    assert body["metrics"] == {
        "queued": 12,
        "oldest_wait_s": 40.0,
        "running": 2,
        "runners_online": 1,
        "slots_total": 2,
        "slots_busy": 2,
    }
    assert (body["decision"]["action"], body["decision"]["desired"], body["decision"]["reason"]) == (
        "up",
        3,
        "queue_depth",
    )
    assert body["webhook_secret_set"] is False
    assert {bad_range.status_code, bad_hook.status_code, bad_url.status_code} == {422}
    assert [e.action for e in await stack.users.audit.list()] == ["settings.autoscale_update"]
