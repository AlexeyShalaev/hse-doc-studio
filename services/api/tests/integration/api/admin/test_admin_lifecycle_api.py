"""`/api/admin/data-lifecycle`: обзор источников, сроки хранения, пороги, запуск очистки; права и границы."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import pytest_asyncio
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from fastapi import FastAPI
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.guards import install_exception_handlers
from hse_doc_studio.api.routers.admin import make_admin_router
from hse_doc_studio.core.identity.protocols import IActorResolver
from hse_doc_studio.core.lifecycle.disk import SafeMode
from hse_doc_studio.core.lifecycle.policies import POLICY_BY_KEY
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.infra.identity.resolvers import ChainActorResolver, SessionCookieResolver
from hse_doc_studio.use_cases.identity.sessions import SessionService
from hse_doc_studio.use_cases.lifecycle.admin import (
    GetLifecycleUC,
    RunLifecycleUC,
    TaskRun,
    UpdateRetentionUC,
    UpdateThresholdsUC,
)
from hse_doc_studio.use_cases.lifecycle.engine import LifecycleEngine
from hse_doc_studio.use_cases.lifecycle.guard import StorageGuard
from hse_doc_studio.use_cases.lifecycle.sweep import LifecycleSweepService
from httpx import ASGITransport, AsyncClient

from tests.fakes.auth import empty_bearer_resolver
from tests.fakes.data_lifecycle import (
    FakeAdmins,
    FakeNotifier,
    FakeProbe,
    FakeRuns,
    FakeSource,
    InMemoryLifecycleSweeps,
)
from tests.fakes.identity import InMemoryInstanceSettingsRepository
from tests.fakes.ops import NoopUow
from tests.integration.api.admin.test_admin_users_api import _Env as _UsersEnv

NOW = datetime(2026, 11, 10, 12, tzinfo=UTC)


class _Stack:
    def __init__(self, users: _UsersEnv) -> None:
        self.users = users
        self.settings = InMemoryInstanceSettingsRepository()
        self.runs = FakeRuns()
        self.sources = {key: FakeSource(key) for key in POLICY_BY_KEY}
        self.engine = LifecycleEngine(
            self.sources,
            self.settings,
            self.runs,
            users.audit,
            env_days={"audit_log": 365},
            batch_size=10,
            budget_s=5,
            clock=lambda: NOW,
        )
        self.sweeps = InMemoryLifecycleSweeps()
        self.sweep_service = LifecycleSweepService(
            self.engine, self.sweeps, self.settings, users.audit, clock=lambda: NOW
        )
        self.mode = SafeMode()
        self.guard = StorageGuard(
            FakeProbe(0.85), self.settings, FakeNotifier(), FakeAdmins(), self.mode, safe_mode_enabled=True
        )
        self.client: AsyncClient


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
    def get_uc(self) -> GetLifecycleUC:
        tasks = {"auth_cleanup": TaskRun(runs=3, failures=0, last_run_at=NOW)}
        return GetLifecycleUC(self.s.engine, self.s.settings, self.s.runs, self.s.guard, self.s.mode, lambda: tasks)

    @provide
    def retention_uc(self) -> UpdateRetentionUC:
        return UpdateRetentionUC(self.s.settings, self.s.users.audit, NoopUow())

    @provide
    def thresholds_uc(self) -> UpdateThresholdsUC:
        return UpdateThresholdsUC(self.s.settings, self.s.users.audit, NoopUow())

    @provide
    def run_uc(self) -> RunLifecycleUC:
        return RunLifecycleUC(self.s.engine, self.s.users.audit)

    @provide
    def sweep_service(self) -> LifecycleSweepService:
        return self.s.sweep_service


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
        s.client = c
        yield s
    await container.close()


_ROUTES = [
    ("GET", "/api/admin/data-lifecycle", None),
    ("PUT", "/api/admin/data-lifecycle/retention/notifications", {"days": 60}),
    ("PUT", "/api/admin/data-lifecycle/thresholds", {"warn_percent": 70, "critical_percent": 85}),
    ("POST", "/api/admin/data-lifecycle/notifications/run", None),
    ("GET", "/api/admin/data-lifecycle/sweep/preview", None),
    ("GET", "/api/admin/data-lifecycle/sweep", None),
    ("POST", "/api/admin/data-lifecycle/sweep", {}),
    ("POST", "/api/admin/data-lifecycle/sweep/x/cancel", {}),
]


@pytest.mark.parametrize(("method", "path", "body"), _ROUTES, ids=[f"{m} {p[-30:]}" for m, p, _ in _ROUTES])
async def test__routes__student_404_anonymous_401(stack: _Stack, method: str, path: str, body: object) -> None:
    student = await stack.users.add(str(uuid4()))

    assert (await stack.client.request(method, path, json=body, headers=student)).status_code == 404
    assert (await stack.client.request(method, path, json=body)).status_code == 401
    assert await stack.users.audit.list() == []


async def test__overview__lists_sources_volumes_and_levels(stack: _Stack) -> None:
    boss = await stack.users.add(str(uuid4()), admin=True)
    await stack.engine.run_one("notifications")

    body = (await stack.client.get("/api/admin/data-lifecycle", headers=boss)).json()

    by_key = {s["key"]: s for s in body["sources"]}
    assert set(by_key) == set(POLICY_BY_KEY)
    audit = by_key["audit_log"]
    assert (audit["days"], audit["min_days"], audit["max_days"], audit["editable"], audit["run_now"]) == (
        365,
        90,
        3650,
        True,
        False,
    )
    assert audit["protected"] is True
    assert audit["env"] == "HSE_STUDIO__SERVER__AUDIT_RETENTION_DAYS"
    assert by_key["notifications"]["last_run"]["removed"] == 3
    assert by_key["notifications"]["run_now"] is True
    assert by_key["auth_records"]["last_run"]["runs"] == 3
    assert by_key["container_logs"]["editable"] is False
    assert by_key["container_logs"]["days"] is None
    assert body["thresholds"] == {"warn_percent": 80, "critical_percent": 90}
    assert [v["level"] for v in body["volumes"]] == ["warning", "ok"]
    assert body["level"] == "warning"
    assert body["safe_mode"] is False


async def test__retention__roundtrip_bounds_and_reset(stack: _Stack) -> None:
    boss = await stack.users.add(str(uuid4()), admin=True)
    c = stack.client

    saved = await c.put("/api/admin/data-lifecycle/retention/notifications", json={"days": 120}, headers=boss)
    too_low = await c.put("/api/admin/data-lifecycle/retention/audit_log", json={"days": 30}, headers=boss)
    zero = await c.put("/api/admin/data-lifecycle/retention/audit_log", json={"days": 0}, headers=boss)
    not_editable = await c.put("/api/admin/data-lifecycle/retention/compile_records", json={"days": 30}, headers=boss)
    unknown = await c.put("/api/admin/data-lifecycle/retention/nope", json={"days": 30}, headers=boss)
    reset = await c.put("/api/admin/data-lifecycle/retention/notifications", json={"days": None}, headers=boss)

    notif = {s["key"]: s for s in saved.json()["sources"]}["notifications"]
    assert saved.status_code == 200
    assert (notif["days"], notif["days_source"]) == (120, "admin")
    assert {too_low.status_code, zero.status_code, not_editable.status_code} == {422}
    assert unknown.status_code == 404
    back = {s["key"]: s for s in reset.json()["sources"]}["notifications"]
    assert (back["days"], back["days_source"]) == (90, "default")
    assert [e.action for e in await stack.users.audit.list()] == ["settings.retention_update"] * 2


async def test__thresholds__validated_and_applied(stack: _Stack) -> None:
    boss = await stack.users.add(str(uuid4()), admin=True)
    c = stack.client

    ok = await c.put(
        "/api/admin/data-lifecycle/thresholds", json={"warn_percent": 60, "critical_percent": 70}, headers=boss
    )
    inverted = await c.put(
        "/api/admin/data-lifecycle/thresholds", json={"warn_percent": 90, "critical_percent": 80}, headers=boss
    )
    out = await c.put(
        "/api/admin/data-lifecycle/thresholds", json={"warn_percent": 10, "critical_percent": 80}, headers=boss
    )

    assert ok.json()["thresholds"] == {"warn_percent": 60, "critical_percent": 70}
    assert ok.json()["level"] == "critical"
    assert inverted.status_code == 422
    assert out.status_code == 422


async def test__run_now__audit_refused_others_run_and_are_audited(stack: _Stack) -> None:
    boss = await stack.users.add(str(uuid4()), admin=True)
    c = stack.client

    audit = await c.post("/api/admin/data-lifecycle/audit_log/run", headers=boss)
    infra = await c.post("/api/admin/data-lifecycle/container_logs/run", headers=boss)
    unknown = await c.post("/api/admin/data-lifecycle/nope/run", headers=boss)
    done = await c.post("/api/admin/data-lifecycle/notifications/run", headers=boss)

    assert (audit.status_code, infra.status_code, unknown.status_code) == (403, 403, 404)
    assert done.status_code == 200
    assert done.json() == {"key": "notifications", "removed": 3, "partitions_dropped": 1, "more": False, "error": None}
    assert [e.action for e in await stack.users.audit.list()] == ["lifecycle.run_now"]


_MANUAL = ["ai_usage", "jobs", "notifications", "collab_requests", "share_links", "guest_sessions", "collab_state"]


async def test__sweep_preview__shape_and_no_store(stack: _Stack) -> None:
    boss = await stack.users.add(str(uuid4()), admin=True)
    stack.sources["ai_usage"].expired = 100_001
    stack.sources["jobs"].expired = None

    response = await stack.client.get("/api/admin/data-lifecycle/sweep/preview", headers=boss)

    body = response.json()
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert [s["key"] for s in body["sources"]] == _MANUAL
    ai = body["sources"][0]
    assert ai == {
        "key": "ai_usage",
        "days": 90,
        "cutoff": "2026-08-12T12:00:00Z",
        "count": 100_000,
        "capped": True,
        "bytes": 1024,
    }
    assert (body["sources"][1]["count"], body["sources"][1]["capped"]) == (None, False)
    assert body["sources"][5]["days"] is None
    assert {"key": "audit_log", "reason": "protected"} in body["excluded"]
    assert {"key": "lifecycle_sweeps", "reason": "on_write"} in body["excluded"]
    assert body["nothing"] is False
    assert await stack.users.audit.list() == []


async def test__sweep__start_poll_result_and_busy(stack: _Stack) -> None:
    boss = await stack.users.add(str(uuid4()), admin=True)
    c = stack.client

    empty = await c.get("/api/admin/data-lifecycle/sweep", headers=boss)
    started = await c.post("/api/admin/data-lifecycle/sweep", json={}, headers=boss)
    busy = await c.post("/api/admin/data-lifecycle/sweep", json={}, headers=boss)
    await stack.sweep_service.drain()
    state = await c.get("/api/admin/data-lifecycle/sweep", headers=boss)
    stop_done = await c.post(f"/api/admin/data-lifecycle/sweep/{started.json()['id']}/cancel", json={}, headers=boss)
    stop_unknown = await c.post("/api/admin/data-lifecycle/sweep/nope/cancel", json={}, headers=boss)

    assert empty.json() == {"sweep": None}
    assert started.status_code == 202
    first = started.json()
    assert (first["status"], first["finished_at"], first["removed_total"], first["freed_bytes"]) == (
        "running",
        None,
        0,
        0,
    )
    assert first["steps"][0] == {
        "key": "ai_usage",
        "status": "pending",
        "removed": 0,
        "partitions_dropped": 0,
        "more": False,
        "bytes_before": None,
        "bytes_after": None,
        "error": None,
    }
    assert (busy.status_code, busy.json()["code"]) == (409, "lifecycle_sweep_busy")
    sweep = state.json()["sweep"]
    assert sweep["status"] == "done"
    assert sweep["removed_total"] == 3 * len(_MANUAL)
    assert {s["status"] for s in sweep["steps"]} == {"done"}
    assert sweep["steps"][0]["bytes_before"] == 1024
    assert state.headers["cache-control"] == "no-store"
    assert (stop_done.status_code, stop_done.json()["code"]) == (409, "command_finished")
    assert stop_unknown.status_code == 404
    actions = [e.action for e in await stack.users.audit.list()]
    assert sorted(actions) == ["lifecycle.sweep", "lifecycle.swept"]
