"""`/api/admin/backups`: права, формы, секреты не возвращаются и не попадают в ошибки валидации."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

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
from hse_doc_studio.infra.backup.parts import PartUploader
from hse_doc_studio.infra.identity.resolvers import ChainActorResolver, SessionCookieResolver
from hse_doc_studio.use_cases.backup.destinations import (
    CreateDestinationUC,
    DeleteDestinationUC,
    ListDestinationsUC,
    TestDestinationUC,
    UpdateDestinationUC,
)
from hse_doc_studio.use_cases.backup.runs import (
    DeleteStoredBackupUC,
    GetRunUC,
    ListRunsUC,
    ListStoredBackupsUC,
    StartBackupUC,
)
from hse_doc_studio.use_cases.backup.service import BackupService
from hse_doc_studio.use_cases.backup.settings import GetBackupSettingsUC, UpdateBackupSettingsUC
from httpx import ASGITransport, AsyncClient

from tests.fakes.auth import empty_bearer_resolver
from tests.fakes.backup import (
    Admins,
    BytesProducer,
    DirStores,
    FixedEnv,
    FixedKeys,
    FixedPlan,
    InMemoryDestinations,
    InMemoryRuns,
    RecordingNotifier,
)
from tests.fakes.identity import InMemoryInstanceSettingsRepository
from tests.fakes.ops import NoopUow, ReversingCipher
from tests.integration.api.admin.test_admin_users_api import _Env as _UsersEnv

SECRET = "TOP-SECRET-KEY-VALUE"


class _Stack:
    def __init__(self, users: _UsersEnv, root: Path) -> None:
        self.users = users
        self.destinations = InMemoryDestinations()
        self.runs = InMemoryRuns()
        self.settings = InMemoryInstanceSettingsRepository()
        self.stores = DirStores(root / "dest")
        self.cipher = ReversingCipher()
        self.service = BackupService(
            self.destinations,
            self.runs,
            self.settings,
            self.stores,  # type: ignore[arg-type]
            PartUploader(root / "tmp"),
            FixedPlan(BytesProducer("db.pgdump.enc", b"DUMP" * 100)),
            FixedEnv(),
            FixedKeys(),
            self.cipher,  # type: ignore[arg-type]
            users.audit,
            RecordingNotifier(),  # type: ignore[arg-type]
            Admins("boss"),
        )
        self.client: AsyncClient

    def args(self) -> tuple[Any, ...]:
        return (self.destinations, self.runs, self.cipher, self.stores, self.service, self.users.audit, NoopUow())


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
    def list_destinations(self) -> ListDestinationsUC:
        return ListDestinationsUC(self.s.destinations)

    @provide
    def create(self) -> CreateDestinationUC:
        return CreateDestinationUC(*self.s.args())

    @provide
    def update(self) -> UpdateDestinationUC:
        return UpdateDestinationUC(*self.s.args())

    @provide
    def delete(self) -> DeleteDestinationUC:
        return DeleteDestinationUC(*self.s.args())

    @provide
    def test(self) -> TestDestinationUC:
        return TestDestinationUC(*self.s.args())

    @provide
    def get_settings(self) -> GetBackupSettingsUC:
        return GetBackupSettingsUC(self.s.settings, self.s.runs)

    @provide
    def put_settings(self) -> UpdateBackupSettingsUC:
        return UpdateBackupSettingsUC(
            self.s.settings,
            self.s.runs,
            self.s.cipher,
            self.s.users.audit,
            NoopUow(),  # type: ignore[arg-type]
        )

    @provide
    def start(self) -> StartBackupUC:
        return StartBackupUC(self.s.service)

    @provide
    def runs(self) -> ListRunsUC:
        return ListRunsUC(self.s.runs)

    @provide
    def run(self) -> GetRunUC:
        return GetRunUC(self.s.runs)

    @provide
    def stored(self) -> ListStoredBackupsUC:
        return ListStoredBackupsUC(self.s.destinations, self.s.service)

    @provide
    def delete_stored(self) -> DeleteStoredBackupUC:
        return DeleteStoredBackupUC(self.s.destinations, self.s.runs, self.s.service, self.s.users.audit)


@pytest_asyncio.fixture
async def stack(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AsyncIterator[_Stack]:
    monkeypatch.setattr(settings, "mode", StudioMode.server)
    s = _Stack(_UsersEnv(), tmp_path)
    app = FastAPI()
    app.include_router(make_admin_router())
    install_exception_handlers(app)
    container = make_async_container(_Provider(s), FastapiProvider())
    setup_dishka(container, app)
    async with AsyncClient(transport=ASGITransport(app=app, client=("203.0.113.9", 5000)), base_url="http://test") as c:
        s.client = c
        yield s
    await s.service.drain()
    await container.close()


_LOCAL = {"name": "Диск", "kind": "local", "local_path": "disk1"}
_S3 = {
    "name": "Свой S3",
    "kind": "s3",
    "endpoint": "http://backup-minio:9000",
    "bucket": "hse-backups",
    "prefix": "studio",
    "access_key": "AKIA-EXAMPLE-1234",
    "secret_key": SECRET,
}
_ID = "00000000-0000-0000-0000-000000000001"
_ROUTES: list[tuple[str, str, Any]] = [
    ("GET", "/api/admin/backups/status", None),
    (
        "PUT",
        "/api/admin/backups/settings",
        {
            "enabled": False,
            "schedule_kind": "interval",
            "interval_hours": 24,
            "cron": "0 3 * * *",
            "keep_last": 7,
            "keep_days": 30,
            "encryption_mode": "installation",
            "notify_admins": True,
        },
    ),
    ("GET", "/api/admin/backups/destinations", None),
    ("POST", "/api/admin/backups/destinations", _LOCAL),
    ("POST", "/api/admin/backups/destinations/test", {"destination": _LOCAL}),
    ("PUT", f"/api/admin/backups/destinations/{_ID}", _LOCAL),
    ("DELETE", f"/api/admin/backups/destinations/{_ID}", None),
    ("POST", f"/api/admin/backups/destinations/{_ID}/test", None),
    ("GET", f"/api/admin/backups/destinations/{_ID}/backups", None),
    ("DELETE", f"/api/admin/backups/destinations/{_ID}/backups/20261101T120000Z-aaaaaa", None),
    ("POST", "/api/admin/backups/runs", {}),
    ("GET", "/api/admin/backups/runs", None),
    ("GET", f"/api/admin/backups/runs/{_ID}", None),
]


@pytest.mark.parametrize(("method", "path", "body"), _ROUTES, ids=[f"{m} {p[18:60]}" for m, p, _ in _ROUTES])
async def test__routes__student_404_anonymous_401(stack: _Stack, method: str, path: str, body: Any) -> None:
    student = await stack.users.add("student")
    assert (await stack.client.request(method, path, json=body, headers=student)).status_code == 404
    assert (await stack.client.request(method, path, json=body)).status_code == 401
    assert stack.destinations.items == {}


async def test__destination__create_never_returns_or_leaks_secrets(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)
    c = stack.client
    created = await c.post("/api/admin/backups/destinations", json=_S3, headers=boss)
    assert created.status_code == 201
    body = created.json()
    assert body["secret_key_set"] is True
    assert body["access_key_hint"] == "…1234"
    assert body["is_default"] is True
    listed = await c.get("/api/admin/backups/destinations", headers=boss)
    for response in (created, listed):
        assert SECRET not in response.text
        assert "AKIA-EXAMPLE" not in response.text
    stored = next(iter(stack.destinations.items.values()))
    assert stored.secret_key_enc is not None
    assert SECRET not in stored.secret_key_enc
    audit = str([e.details for e in stack.users.audit._entries])  # noqa: SLF001
    assert SECRET not in audit


async def test__destination__validation_error_does_not_echo_secret(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)
    response = await stack.client.post(
        "/api/admin/backups/destinations", json={**_S3, "kind": "nope", "secret_key": SECRET}, headers=boss
    )
    assert response.status_code == 422
    assert SECRET not in response.text


async def test__destination__domain_errors_have_code_field_and_status(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)
    c = stack.client
    bad = await c.post("/api/admin/backups/destinations", json={**_LOCAL, "local_path": "../etc"}, headers=boss)
    assert bad.status_code == 422
    assert bad.json()["code"] == "backup_invalid_input"
    assert bad.json()["field"] == "local_path"
    await c.post("/api/admin/backups/destinations", json=_LOCAL, headers=boss)
    dup = await c.post("/api/admin/backups/destinations", json={**_LOCAL, "name": "диск"}, headers=boss)
    assert dup.status_code == 409
    assert dup.json()["code"] == "backup_conflict"
    assert (await c.delete(f"/api/admin/backups/destinations/{_ID}", headers=boss)).status_code == 404


async def test__destination__test_endpoint_reports_result_and_warnings(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)
    ok = await stack.client.post("/api/admin/backups/destinations/test", json={"destination": _LOCAL}, headers=boss)
    assert ok.status_code == 200
    assert ok.json()["ok"] is True
    stack.stores.primary.add("hse-backups")
    warn = await stack.client.post("/api/admin/backups/destinations/test", json={"destination": _S3}, headers=boss)
    assert warn.json()["warnings"] == ["same_as_primary"]
    assert SECRET not in ok.text + warn.text


async def test__run__start_list_stored_and_restore_hint(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)
    c = stack.client
    dest = (await c.post("/api/admin/backups/destinations", json=_LOCAL, headers=boss)).json()
    started = await c.post("/api/admin/backups/runs", json={}, headers=boss)
    assert started.status_code == 202
    assert started.json()["status"] == "running"
    again = await c.post("/api/admin/backups/runs", json={}, headers=boss)
    assert again.status_code == 409
    assert again.json()["code"] == "backup_already_running"
    await stack.service.drain()
    runs = (await c.get("/api/admin/backups/runs", headers=boss)).json()
    assert runs["total"] == 1
    assert runs["items"][0]["status"] == "ok"
    assert runs["items"][0]["size_bytes"] > 0
    stored = (await c.get(f"/api/admin/backups/destinations/{dest['id']}/backups", headers=boss)).json()
    assert len(stored) == 1
    assert stored[0]["restore_command"].startswith("hse-doc-studio backup restore --from-dir")
    assert stored[0]["backup_id"] in stored[0]["restore_command"]
    deleted = await c.delete(
        f"/api/admin/backups/destinations/{dest['id']}/backups/{stored[0]['backup_id']}", headers=boss
    )
    assert deleted.status_code == 204
    assert (await c.get(f"/api/admin/backups/destinations/{dest['id']}/backups", headers=boss)).json() == []


async def test__settings__roundtrip_status_and_validation(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)
    c = stack.client
    body = {
        "enabled": True,
        "schedule_kind": "cron",
        "interval_hours": 24,
        "cron": "30 2 * * 1",
        "keep_last": 5,
        "keep_days": 14,
        "encryption_mode": "passphrase",
        "notify_admins": True,
        "passphrase": "a long enough passphrase",
    }
    saved = await c.put("/api/admin/backups/settings", json=body, headers=boss)
    assert saved.status_code == 200
    data = saved.json()
    assert data["settings"]["passphrase_set"] is True
    assert data["settings"]["cron"] == "30 2 * * 1"
    assert data["next_run_at"] is not None
    assert "a long enough passphrase" not in saved.text
    bad = await c.put("/api/admin/backups/settings", json={**body, "cron": "bad cron"}, headers=boss)
    assert bad.status_code == 422
    assert bad.json()["field"] == "cron"
    short = await c.put("/api/admin/backups/settings", json={**body, "passphrase": "short"}, headers=boss)
    assert short.status_code == 422
    assert "short" not in short.text.replace("too short", "")
