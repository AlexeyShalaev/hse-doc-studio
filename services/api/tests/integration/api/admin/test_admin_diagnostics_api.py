"""`/api/admin/diagnostics`: обзор, ручной прогон, пороги; права и границы."""

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
from hse_doc_studio.core.diagnostics.entities import CHECKS, CheckId, DiagStatus, Verdict
from hse_doc_studio.core.diagnostics.thresholds import BOUNDS, DEFAULTS
from hse_doc_studio.core.identity.protocols import IActorResolver
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.infra.identity.resolvers import ChainActorResolver, SessionCookieResolver
from hse_doc_studio.use_cases.diagnostics.admin import (
    AcceptDiagnosticsWarningUC,
    GetDiagnosticsUC,
    RevokeDiagnosticsAcceptanceUC,
    RunDiagnosticsUC,
    UpdateDiagnosticsThresholdsUC,
)
from hse_doc_studio.use_cases.diagnostics.service import DiagnosticsService
from hse_doc_studio.use_cases.identity.sessions import SessionService
from httpx import ASGITransport, AsyncClient

from tests.fakes.auth import empty_bearer_resolver
from tests.fakes.data_lifecycle import FakeAdmins, FakeNotifier
from tests.fakes.identity import InMemoryInstanceSettingsRepository
from tests.fakes.ops import NoopUow
from tests.integration.api.admin.test_admin_users_api import _Env as _UsersEnv
from tests.unit.use_cases.diagnostics.test_service_and_admin import MemStore, ScriptedCheck

NOW = datetime(2026, 11, 10, 12, tzinfo=UTC)


class _Stack:
    def __init__(self, users: _UsersEnv) -> None:
        self.users = users
        self.settings = InMemoryInstanceSettingsRepository()
        checks = [
            ScriptedCheck(CheckId.database, Verdict(DiagStatus.ok, "ok", {"latency_ms": 3, "version": "16"})),
            ScriptedCheck(CheckId.disk, Verdict(DiagStatus.warn, "disk_warning", {"volume": "data", "percent": 85})),
            ScriptedCheck(CheckId.backups, Verdict(DiagStatus.warn, "backups_disabled")),
        ]
        self.service = DiagnosticsService(
            checks,  # type: ignore[arg-type]
            MemStore(),  # type: ignore[arg-type]
            self.settings,
            FakeNotifier(),  # type: ignore[arg-type]
            FakeAdmins(),
            timeout_s=5,
            clock=lambda: NOW,
        )
        self.get = GetDiagnosticsUC(self.service, self.settings, interval_s=300, enabled=True, clock=lambda: NOW)
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
    def get_uc(self) -> GetDiagnosticsUC:
        return self.s.get

    @provide
    def run_uc(self) -> RunDiagnosticsUC:
        return RunDiagnosticsUC(self.s.service, self.s.get, self.s.users.audit)

    @provide
    def accept_uc(self) -> AcceptDiagnosticsWarningUC:
        s = self.s
        return AcceptDiagnosticsWarningUC(s.settings, s.users.audit, NoopUow(), s.service, s.get, clock=lambda: NOW)

    @provide
    def revoke_uc(self) -> RevokeDiagnosticsAcceptanceUC:
        return RevokeDiagnosticsAcceptanceUC(self.s.settings, self.s.users.audit, NoopUow(), self.s.get)

    @provide
    def update_uc(self) -> UpdateDiagnosticsThresholdsUC:
        return UpdateDiagnosticsThresholdsUC(self.s.settings, self.s.users.audit, NoopUow(), self.s.get)


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


def _full() -> dict[str, int]:
    return {name: int(getattr(DEFAULTS, name)) for name in BOUNDS}


_ROUTES = [
    ("GET", "/api/admin/diagnostics", None),
    ("POST", "/api/admin/diagnostics/run", {"check": None}),
    ("PUT", "/api/admin/diagnostics/thresholds", {"values": _full(), "notify": True}),
    ("PUT", "/api/admin/diagnostics/accepted/backups", {"reason": "так надо"}),
    ("DELETE", "/api/admin/diagnostics/accepted/backups", None),
]


@pytest.mark.parametrize(("method", "path", "body"), _ROUTES, ids=[f"{m} {p[-12:]}" for m, p, _ in _ROUTES])
async def test__routes__student_404_anonymous_401(stack: _Stack, method: str, path: str, body: object) -> None:
    student = await stack.users.add(str(uuid4()))

    assert (await stack.client.request(method, path, json=body, headers=student)).status_code == 404
    assert (await stack.client.request(method, path, json=body)).status_code == 401
    assert await stack.users.audit.list() == []


async def test__overview__before_first_run__every_check_listed_with_null_status(stack: _Stack) -> None:
    boss = await stack.users.add(str(uuid4()), admin=True)

    body = (await stack.client.get("/api/admin/diagnostics", headers=boss)).json()

    assert [c["id"] for c in body["checks"]] == [spec.id.value for spec in CHECKS]
    assert {c["status"] for c in body["checks"]} == {None}
    assert body["overall"] == "ok"
    assert len(body["thresholds"]) == len(BOUNDS)


async def test__run__fills_status_reason_hint_and_overall(stack: _Stack) -> None:
    boss = await stack.users.add(str(uuid4()), admin=True)

    res = await stack.client.post("/api/admin/diagnostics/run", json={"check": None}, headers=boss)

    by_id = {c["id"]: c for c in res.json()["checks"]}
    assert res.status_code == 200
    assert (by_id["database"]["status"], by_id["database"]["hint"]) == ("ok", None)
    disk = by_id["disk"]
    assert (disk["status"], disk["reason"], disk["hint"]) == ("warn", "disk_warning", "disk_warning")
    assert disk["values"] == {"volume": "data", "percent": 85}
    assert disk["checked_at"] is not None
    assert res.json()["overall"] == "warn"
    assert (disk["acceptable"], disk["accepted"]) == (False, None)  # место на диске принять нельзя
    assert by_id["backups"]["acceptable"] is True
    assert [e.action for e in await stack.users.audit.list()] == ["diagnostics.run"]


async def test__run__unknown_check__404(stack: _Stack) -> None:
    boss = await stack.users.add(str(uuid4()), admin=True)

    res = await stack.client.post("/api/admin/diagnostics/run", json={"check": "nope"}, headers=boss)

    assert res.status_code == 404


async def test__thresholds__saved_validated_and_returned(stack: _Stack) -> None:
    boss = await stack.users.add(str(uuid4()), admin=True)
    c = stack.client

    ok = await c.put(
        "/api/admin/diagnostics/thresholds",
        json={"values": {**_full(), "backup_warn_hours": 48}, "notify": False},
        headers=boss,
    )
    inverted = await c.put(
        "/api/admin/diagnostics/thresholds",
        json={"values": {**_full(), "backup_warn_hours": 200}, "notify": True},
        headers=boss,
    )
    partial = await c.put(
        "/api/admin/diagnostics/thresholds", json={"values": {"tls_warn_days": 30}, "notify": True}, headers=boss
    )

    row = {t["name"]: t for t in ok.json()["thresholds"]}["backup_warn_hours"]
    assert (row["value"], row["default"]) == (48, 36)
    assert ok.json()["notify"] is False
    assert inverted.status_code == 422
    assert partial.status_code == 422


async def test__accept__over_http_greys_the_warning_and_revoke_brings_it_back(stack: _Stack) -> None:
    boss = await stack.users.add(str(uuid4()), admin=True)
    c = stack.client
    await c.post("/api/admin/diagnostics/run", json={"check": None}, headers=boss)

    res = await c.put(
        "/api/admin/diagnostics/accepted/backups",
        json={"reason": "Бэкапы делает хостер", "until": "2026-12-01T00:00:00Z"},
        headers=boss,
    )

    body = res.json()
    by_id = {x["id"]: x for x in body["checks"]}
    assert res.status_code == 200
    assert by_id["backups"]["status"] == "warn"  # статус честный, гасится только итог
    assert by_id["backups"]["accepted"]["reason"] == "Бэкапы делает хостер"
    assert by_id["backups"]["accepted"]["until"].startswith("2026-12-01")
    assert by_id["backups"]["acceptable"] is False
    assert body["overall"] == "warn"  # диск всё ещё предупреждает
    assert [(a["check"], a["active"]) for a in body["accepted"]] == [("backups", True)]
    assert (await stack.settings.get_all())["diagnostics.accepted"]["backups"]["reason"] == "Бэкапы делает хостер"
    (event, *_) = await stack.users.audit.list()
    assert (event.action, event.target, event.details["reason"]) == (
        "diagnostics.accept",
        "backups",
        "Бэкапы делает хостер",
    )

    back = await c.delete("/api/admin/diagnostics/accepted/backups", headers=boss)

    assert back.status_code == 200
    assert {x["id"]: x for x in back.json()["checks"]}["backups"]["accepted"] is None
    assert back.json()["accepted"] == []
    assert (await stack.users.audit.list())[0].action == "diagnostics.accept_revoke"
    assert (await c.delete("/api/admin/diagnostics/accepted/backups", headers=boss)).status_code == 404


async def test__accept__critical_check_and_bad_input_are_422_and_nothing_is_stored(stack: _Stack) -> None:
    boss = await stack.users.add(str(uuid4()), admin=True)
    c = stack.client
    await c.post("/api/admin/diagnostics/run", json={"check": None}, headers=boss)
    audit_before = len(await stack.users.audit.list())

    disk = await c.put("/api/admin/diagnostics/accepted/disk", json={"reason": "пусть"}, headers=boss)
    healthy = await c.put("/api/admin/diagnostics/accepted/database", json={"reason": "пусть"}, headers=boss)
    empty = await c.put("/api/admin/diagnostics/accepted/backups", json={"reason": ""}, headers=boss)
    long = await c.put("/api/admin/diagnostics/accepted/backups", json={"reason": "я" * 201}, headers=boss)
    past = await c.put(
        "/api/admin/diagnostics/accepted/backups",
        json={"reason": "ок", "until": "2020-01-01T00:00:00Z"},
        headers=boss,
    )
    naive = await c.put(
        "/api/admin/diagnostics/accepted/backups", json={"reason": "ок", "until": "2030-01-01T00:00:00"}, headers=boss
    )
    unknown = await c.put("/api/admin/diagnostics/accepted/nope", json={"reason": "ок"}, headers=boss)

    assert [r.status_code for r in (disk, healthy, empty, long, past, naive)] == [422] * 6
    assert unknown.status_code == 404
    assert "diagnostics.accepted" not in await stack.settings.get_all()
    assert len(await stack.users.audit.list()) == audit_before
