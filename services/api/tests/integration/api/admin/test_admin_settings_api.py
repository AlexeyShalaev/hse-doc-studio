"""`/api/admin`: регистрация, способы входа, SMTP с тестовым письмом, провайдеры OIDC; секреты только на запись."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from fastapi import FastAPI
from hse_doc_studio.api.auth_cookie import SESSION_COOKIE
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.guards import install_exception_handlers
from hse_doc_studio.api.routers.admin import make_admin_router
from hse_doc_studio.core.identity.auth_settings import AuthEnvOverrides
from hse_doc_studio.core.identity.entities import RegistrationMode, Session, User, UserStatus
from hse_doc_studio.core.identity.normalize import hash_token, normalize_email
from hse_doc_studio.core.identity.protocols import IActorResolver
from hse_doc_studio.core.identity.smtp_settings import SmtpEnv, SmtpParams
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.infra.identity.resolvers import ChainActorResolver, SessionCookieResolver
from hse_doc_studio.infra.secrets.fernet_cipher import FernetSecretCipher
from hse_doc_studio.infra.secrets.key_store import KeyFileStore
from hse_doc_studio.use_cases.admin.oidc import (
    CreateOidcProviderUC,
    DeleteOidcProviderUC,
    GetOidcProviderUC,
    ListOidcProvidersUC,
    UpdateOidcProviderUC,
)
from hse_doc_studio.use_cases.admin.settings import GetAuthGroupUC, UpdateAuthMethodsUC, UpdateRegistrationUC
from hse_doc_studio.use_cases.identity.auth_settings import AuthSettingsService, UpdateAuthSettingsUC
from hse_doc_studio.use_cases.identity.sessions import SessionService
from hse_doc_studio.use_cases.identity.smtp_settings import (
    GetSmtpSettingsUC,
    SendTestMailUC,
    SmtpSettingsService,
    UpdateSmtpSettingsUC,
)
from httpx import ASGITransport, AsyncClient

from tests.fakes.auth import (
    InMemoryAuditLog,
    InMemoryOidcProviderRepository,
    InMemorySessionRepository,
    empty_bearer_resolver,
)
from tests.fakes.identity import InMemoryIdentityStore, InMemoryInstanceSettingsRepository, InMemoryUserRepository
from tests.unit.use_cases.identity.conftest import FakeSender

NOW = datetime.now(UTC)
PASSWORD = "very-secret-smtp-password"  # noqa: S105 — значение для проверки, что оно не утекает
CLIENT_SECRET = "very-secret-oidc-client"  # noqa: S105
OIDC = {"label": "HSE ID", "issuer": "https://id.example.org", "client_id": "studio", "client_secret": CLIENT_SECRET}


class _Env:
    def __init__(self, tmp_path: Path) -> None:
        self.store = InMemoryIdentityStore()
        self.users = InMemoryUserRepository(self.store)
        self.sessions = InMemorySessionRepository()
        self.audit = InMemoryAuditLog()
        self.settings = InMemoryInstanceSettingsRepository()
        self.oidc = InMemoryOidcProviderRepository()
        self.cipher = FernetSecretCipher(KeyFileStore(tmp_path / "secret.key"))
        self.sender = FakeSender(enabled=True)
        self.auth_env = AuthEnvOverrides()
        self.smtp_env = SmtpEnv()
        self.make: Callable[[], AsyncClient]

    async def add(self, uid: str, *, admin: bool = False) -> dict[str, str]:
        email = f"{uid}@example.org"
        await self.users.add(
            User(
                id=uid,
                email=email,
                email_normalized=normalize_email(email),
                name=uid.title(),
                status=UserStatus.active,
                created_at=NOW,
                email_verified=True,
                is_instance_admin=admin,
            )
        )
        await self.sessions.add(
            Session(hash_token(f"s-{uid}"), uid, "csrf", NOW, NOW, NOW + timedelta(days=7), None, "UA")
        )
        return {"Cookie": f"{SESSION_COOKIE}=s-{uid}"}


class _Provider(Provider):
    scope = Scope.APP

    def __init__(self, env: _Env) -> None:
        super().__init__()
        self.e = env
        self.auth = AuthSettingsService(env.settings, env.auth_env)
        update = UpdateAuthSettingsUC(self.auth, env.settings, env.audit)
        group = GetAuthGroupUC(self.auth, env.oidc)
        smtp = SmtpSettingsService(env.settings, env.cipher, env.smtp_env)
        self.uc: dict[type, object] = {
            GetAuthGroupUC: group,
            UpdateRegistrationUC: UpdateRegistrationUC(update, group),
            UpdateAuthMethodsUC: UpdateAuthMethodsUC(update, self.auth, env.oidc, group),
            GetSmtpSettingsUC: GetSmtpSettingsUC(smtp),
            UpdateSmtpSettingsUC: UpdateSmtpSettingsUC(smtp, env.settings, env.audit),
            SendTestMailUC: SendTestMailUC(env.sender, env.audit),
            ListOidcProvidersUC: ListOidcProvidersUC(env.oidc),
            GetOidcProviderUC: GetOidcProviderUC(env.oidc),
            CreateOidcProviderUC: CreateOidcProviderUC(env.oidc, env.cipher, env.audit),
            UpdateOidcProviderUC: UpdateOidcProviderUC(env.oidc, env.cipher, self.auth, env.audit),
            DeleteOidcProviderUC: DeleteOidcProviderUC(env.oidc, self.auth, env.audit),
        }
        for kind, instance in self.uc.items():
            self._register(kind, instance)

    def _register(self, kind: type, instance: object) -> None:
        self.provide(lambda: instance, provides=kind)

    @provide
    def resolver(self) -> IActorResolver:
        return ChainActorResolver(
            [SessionCookieResolver(SessionService(self.e.sessions, self.e.users)), empty_bearer_resolver()]
        )


@pytest_asyncio.fixture
async def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AsyncIterator[_Env]:
    monkeypatch.setattr(settings, "mode", StudioMode.server)
    e = _Env(tmp_path)
    clients: list[AsyncClient] = []
    containers = []

    def make() -> AsyncClient:
        app = FastAPI()
        app.include_router(make_admin_router())
        install_exception_handlers(app)
        container = make_async_container(_Provider(e), FastapiProvider())
        setup_dishka(container, app)
        containers.append(container)
        client = AsyncClient(transport=ASGITransport(app=app, client=("203.0.113.9", 5000)), base_url="http://test")
        clients.append(client)
        return client

    e.make = make
    yield e
    for client in clients:
        await client.aclose()
    for container in containers:
        await container.close()


async def _boss(env: _Env) -> tuple[AsyncClient, dict[str, str]]:
    return env.make(), await env.add("boss", admin=True)


async def test__access__student_gets_404_and_anonymous_401(env: _Env) -> None:
    student = await env.add("student")
    client = env.make()

    for method, path in (
        ("GET", "/api/admin/settings/registration"),
        ("PUT", "/api/admin/settings/auth"),
        ("GET", "/api/admin/settings/smtp"),
        ("POST", "/api/admin/settings/smtp/test"),
        ("GET", "/api/admin/oidc-providers"),
        ("POST", "/api/admin/oidc-providers"),
    ):
        body = {} if method in {"PUT", "POST"} else None
        assert (await client.request(method, path, headers=student, json=body)).status_code == 404, path
        assert (await client.request(method, path, json=body)).status_code == 401, path


async def test__registration__defaults_then_update_writes_audit(env: _Env) -> None:
    client, boss = await _boss(env)

    before = (await client.get("/api/admin/settings/registration", headers=boss)).json()
    after = await client.put(
        "/api/admin/settings/registration",
        json={"registration_mode": "domains", "registration_domains": ["@HSE.ru", "hse.ru"], "require_approval": True},
        headers=boss,
    )

    assert before["registration_mode"] == "invite"
    assert before["fields"]["auth.registration_mode"] == {"source": "default", "locked": False}
    body = after.json()
    assert (body["registration_mode"], body["registration_domains"], body["require_approval"]) == (
        "domains",
        ["hse.ru"],
        True,
    )
    assert body["fields"]["auth.registration_mode"] == {"source": "admin", "locked": False}
    assert [e.action for e in await env.audit.list()] == ["settings.auth_update"]


async def test__registration__env_wins_and_locks_the_key(env: _Env) -> None:
    env.auth_env = AuthEnvOverrides(registration_mode=RegistrationMode.closed)
    client, boss = await _boss(env)

    shown = (await client.get("/api/admin/settings/registration", headers=boss)).json()
    refused = await client.put("/api/admin/settings/registration", json={"registration_mode": "open"}, headers=boss)
    other = await client.put("/api/admin/settings/registration", json={"require_approval": True}, headers=boss)

    assert shown["registration_mode"] == "closed"
    assert shown["fields"]["auth.registration_mode"] == {"source": "env", "locked": True}
    assert (refused.status_code, refused.json()["code"]) == (409, "setting_locked")
    assert other.status_code == 200
    assert other.json()["registration_mode"] == "closed"


async def test__registration__domains_mode_needs_a_domain(env: _Env) -> None:
    client, boss = await _boss(env)

    refused = await client.put("/api/admin/settings/registration", json={"registration_mode": "domains"}, headers=boss)

    assert refused.status_code == 403
    assert (await env.audit.list()) == []


async def test__auth__cannot_turn_off_password_without_another_way_in(env: _Env) -> None:
    client, boss = await _boss(env)

    refused = await client.put("/api/admin/settings/auth", json={"password_enabled": False}, headers=boss)

    assert (refused.status_code, refused.json()["code"]) == (409, "last_login_method")
    assert (await client.get("/api/admin/settings/auth", headers=boss)).json()["password_enabled"] is True


async def test__auth__password_off_with_sso_then_last_provider_is_protected(env: _Env) -> None:
    client, boss = await _boss(env)
    created = (await client.post("/api/admin/oidc-providers", json=OIDC, headers=boss)).json()
    pid = created["id"]

    off = await client.put("/api/admin/settings/auth", json={"password_enabled": False}, headers=boss)
    disable = await client.patch(f"/api/admin/oidc-providers/{pid}", json={"enabled": False}, headers=boss)
    delete = await client.delete(f"/api/admin/oidc-providers/{pid}", headers=boss)
    back = await client.put("/api/admin/settings/auth", json={"password_enabled": True}, headers=boss)
    deleted = await client.delete(f"/api/admin/oidc-providers/{pid}", headers=boss)

    assert off.status_code == 200
    assert off.json()["oidc_enabled_count"] == 1
    assert (disable.status_code, disable.json()["code"]) == (409, "last_login_method")
    assert (delete.status_code, delete.json()["code"]) == (409, "last_login_method")
    assert back.status_code == 200
    assert deleted.status_code == 204


async def test__auth__env_locked_password_is_not_changeable(env: _Env) -> None:
    env.auth_env = AuthEnvOverrides(password_enabled=True)
    client, boss = await _boss(env)

    refused = await client.put("/api/admin/settings/auth", json={"password_enabled": False}, headers=boss)

    assert (refused.status_code, refused.json()["code"]) == (409, "setting_locked")


async def test__smtp__off_by_default_and_password_never_comes_back(env: _Env) -> None:
    client, boss = await _boss(env)
    off = (await client.get("/api/admin/settings/smtp", headers=boss)).json()

    put = await client.put(
        "/api/admin/settings/smtp",
        json={"host": "smtp.example.org", "port": 465, "security": "tls", "username": "mailer", "password": PASSWORD},
        headers=boss,
    )
    again = await client.get("/api/admin/settings/smtp", headers=boss)

    assert (off["enabled"], off["host"], off["password_set"]) == (False, None, False)
    assert put.status_code == 200
    for response in (put, again):
        body = response.json()
        assert (body["enabled"], body["host"], body["port"], body["security"]) == (True, "smtp.example.org", 465, "tls")
        assert body["password_set"] is True
        assert PASSWORD not in response.text
    stored = await env.settings.get_secret("smtp.password")
    assert stored is not None
    assert PASSWORD not in stored
    assert PASSWORD not in json.dumps([dict(e.details) for e in await env.audit.list()])
    assert [e.action for e in await env.audit.list()] == ["settings.smtp_update"]


async def test__smtp__keeps_password_unless_told_and_clears_it_with_empty(env: _Env) -> None:
    client, boss = await _boss(env)
    await client.put("/api/admin/settings/smtp", json={"host": "smtp.example.org", "password": PASSWORD}, headers=boss)

    kept = await client.put("/api/admin/settings/smtp", json={"port": 25}, headers=boss)
    cleared = await client.put("/api/admin/settings/smtp", json={"password": ""}, headers=boss)

    assert (kept.json()["port"], kept.json()["password_set"]) == (25, True)
    assert cleared.json()["password_set"] is False
    assert await env.settings.get_secret("smtp.password") is None


async def test__smtp__empty_host_turns_mail_off_and_bad_input_is_refused(env: _Env) -> None:
    client, boss = await _boss(env)
    await client.put("/api/admin/settings/smtp", json={"host": "smtp.example.org"}, headers=boss)

    off = await client.put("/api/admin/settings/smtp", json={"host": ""}, headers=boss)
    bad_port = await client.put("/api/admin/settings/smtp", json={"port": 0}, headers=boss)
    bad_host = await client.put("/api/admin/settings/smtp", json={"host": "evil.org/path"}, headers=boss)
    bad_from = await client.put("/api/admin/settings/smtp", json={"from_address": "nope"}, headers=boss)

    assert off.json()["enabled"] is False
    assert bad_port.status_code == 422
    assert (bad_host.status_code, bad_from.status_code) == (403, 403)


async def test__smtp__env_wins_and_locks_the_whole_group(env: _Env) -> None:
    env.smtp_env = SmtpEnv(SmtpParams(host="smtp.env.example", port=2525, password=PASSWORD))
    client, boss = await _boss(env)

    shown = await client.get("/api/admin/settings/smtp", headers=boss)
    refused = await client.put("/api/admin/settings/smtp", json={"host": "other.example"}, headers=boss)

    body = shown.json()
    assert (body["host"], body["port"], body["password_set"]) == ("smtp.env.example", 2525, True)
    assert all(state == {"source": "env", "locked": True} for state in body["fields"].values())
    assert PASSWORD not in shown.text
    assert (refused.status_code, refused.json()["code"]) == (409, "setting_locked")


async def test__smtp_test__sends_to_the_admin_or_to_the_given_address(env: _Env) -> None:
    client, boss = await _boss(env)

    own = await client.post("/api/admin/settings/smtp/test", json={}, headers=boss)
    other = await client.post("/api/admin/settings/smtp/test", json={"to": "dean@example.org"}, headers=boss)

    assert own.json() == {"ok": True, "error": None}
    assert other.json()["ok"] is True
    assert [to for to, _, _ in env.sender.sent] == ["boss@example.org", "dean@example.org"]
    assert [e.action for e in await env.audit.list()] == ["settings.smtp_test", "settings.smtp_test"]


async def test__smtp_test__failure_is_a_result_not_a_server_error(env: _Env) -> None:
    env.sender.fail = True
    client, boss = await _boss(env)

    failed = await client.post("/api/admin/settings/smtp/test", json={}, headers=boss)
    bad = await client.post("/api/admin/settings/smtp/test", json={"to": "nope"}, headers=boss)

    assert failed.status_code == 200
    assert failed.json()["ok"] is False
    assert "smtp down" in failed.json()["error"]
    assert bad.status_code == 403


async def test__smtp_test__without_smtp_is_refused(env: _Env) -> None:
    env.sender = FakeSender(enabled=False)
    client, boss = await _boss(env)

    assert (await client.post("/api/admin/settings/smtp/test", json={}, headers=boss)).status_code == 403


async def test__oidc__create_list_get_never_return_the_secret(env: _Env) -> None:
    client, boss = await _boss(env)

    created = await client.post("/api/admin/oidc-providers", json=OIDC, headers=boss)
    listed = await client.get("/api/admin/oidc-providers", headers=boss)
    one = await client.get(f"/api/admin/oidc-providers/{created.json()['id']}", headers=boss)

    assert created.status_code == 201
    for response in (created, listed, one):
        assert CLIENT_SECRET not in response.text
        assert "client_secret_enc" not in response.text
    assert created.json()["client_secret_set"] is True
    assert [p["label"] for p in listed.json()] == ["HSE ID"]
    stored = (await env.oidc.list())[0]
    assert CLIENT_SECRET not in stored.client_secret_enc
    assert CLIENT_SECRET not in json.dumps([dict(e.details) for e in await env.audit.list()])


async def test__oidc__secret_is_replaced_only_by_a_new_value(env: _Env) -> None:
    client, boss = await _boss(env)
    pid = (await client.post("/api/admin/oidc-providers", json=OIDC, headers=boss)).json()["id"]
    first = (await env.oidc.get(pid)).client_secret_enc  # type: ignore[union-attr]

    await client.patch(f"/api/admin/oidc-providers/{pid}", json={"label": "Renamed", "client_secret": ""}, headers=boss)
    same = (await env.oidc.get(pid)).client_secret_enc  # type: ignore[union-attr]
    await client.patch(f"/api/admin/oidc-providers/{pid}", json={"client_secret": "another-secret"}, headers=boss)
    rotated = (await env.oidc.get(pid)).client_secret_enc  # type: ignore[union-attr]

    assert same == first
    assert rotated != first
    assert [e.action for e in await env.audit.list()][0] == "oidc.update"
    opened = env.cipher.decrypt(rotated, aad=f"oidc_providers/client_secret_enc/{pid}")
    assert opened.reveal() == "another-secret"


async def test__oidc__validation(env: _Env) -> None:
    client, boss = await _boss(env)

    for patch in (
        {"issuer": "http://id.example.org"},
        {"issuer": "ftp://id.example.org"},
        {"issuer": "https://user:pw@id.example.org"},
        {"issuer": "https://id.example.org/?x=1"},
        {"scopes": "email profile"},
        {"label": "  "},
        {"client_secret": " "},
    ):
        response = await client.post("/api/admin/oidc-providers", json={**OIDC, **patch}, headers=boss)
        assert (response.status_code, response.json()["code"]) == (422, "input_invalid"), patch
    local = await client.post(
        "/api/admin/oidc-providers", json={**OIDC, "issuer": "http://localhost:8080"}, headers=boss
    )

    assert local.status_code == 201
    assert (await client.get("/api/admin/oidc-providers/nope", headers=boss)).status_code == 404
    assert (await client.patch("/api/admin/oidc-providers/nope", json={}, headers=boss)).status_code == 404
    assert (await client.delete("/api/admin/oidc-providers/nope", headers=boss)).status_code == 404


async def test__audit__every_settings_mutation_writes_exactly_its_event_and_refusals_write_nothing(env: _Env) -> None:
    client, boss = await _boss(env)
    pid = (await client.post("/api/admin/oidc-providers", json=OIDC, headers=boss)).json()["id"]
    await client.put("/api/admin/settings/auth", json={"password_enabled": False}, headers=boss)
    await client.patch(f"/api/admin/oidc-providers/{pid}", json={"label": "New"}, headers=boss)
    await client.put("/api/admin/settings/registration", json={"require_approval": True}, headers=boss)
    await client.put("/api/admin/settings/smtp", json={"host": "smtp.example.org"}, headers=boss)
    await client.post("/api/admin/settings/smtp/test", json={}, headers=boss)
    written = [e.action for e in reversed(await env.audit.list())]
    refused = [
        await client.patch(f"/api/admin/oidc-providers/{pid}", json={"enabled": False}, headers=boss),
        await client.delete(f"/api/admin/oidc-providers/{pid}", headers=boss),
        await client.put("/api/admin/settings/smtp", json={"port": 0}, headers=boss),
    ]
    await client.put("/api/admin/settings/auth", json={"password_enabled": True}, headers=boss)
    await client.delete(f"/api/admin/oidc-providers/{pid}", headers=boss)

    assert written == [
        "oidc.create",
        "settings.auth_update",
        "oidc.update",
        "settings.auth_update",
        "settings.smtp_update",
        "settings.smtp_test",
    ]
    assert [r.status_code for r in refused] == [409, 409, 422]
    assert [e.action for e in reversed(await env.audit.list())][len(written) :] == [
        "settings.auth_update",
        "oidc.delete",
    ]
    assert all(e.actor_id == "boss" for e in await env.audit.list())
