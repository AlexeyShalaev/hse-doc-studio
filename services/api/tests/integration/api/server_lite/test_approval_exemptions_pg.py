"""Исключения из одобрения на настоящем приложении и Postgres: регистрация, письмо, подтверждение, вход и аудит.

Почту принимает поддельный SMTP из e2e (`e2e/fake_smtp/server.py`, только стандартная библиотека) в потоке теста.
"""

from __future__ import annotations

import importlib.util
import re
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.entrypoint import create_app
from hse_doc_studio.core.identity.entities import RegistrationMode
from hse_doc_studio.core.mode import StudioMode
from pydantic import SecretStr

pytestmark = pytest.mark.pg

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

ADMIN_EMAIL = "admin@example.org"
ADMIN_PASSWORD = "stand-admin-password"  # noqa: S105 — тестовое значение
PASSWORD = "correct horse battery"  # noqa: S105 — тестовое значение
ORIGIN = "http://localhost:8100"
HEADERS = {"Origin": ORIGIN}
FAKE_SMTP = Path(__file__).resolve().parents[6] / "e2e" / "fake_smtp" / "server.py"


def _load_fake_smtp() -> ModuleType:
    spec = importlib.util.spec_from_file_location("hds_fake_smtp", FAKE_SMTP)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def mailbox() -> Iterator[tuple[int, list[dict[str, Any]]]]:
    fake = _load_fake_smtp()
    server = fake.SmtpServer(("127.0.0.1", 0), fake.SmtpHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1], fake._MESSAGES  # noqa: SLF001 — письма заглушки в памяти
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def stand(pg_engine: AsyncEngine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    dsn = pg_engine.url.render_as_string(hide_password=False)
    monkeypatch.setattr(settings, "mode", StudioMode.server)
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "host_data_dir", None)
    monkeypatch.setattr(settings, "docker_binary", str(tmp_path / "no-docker"))
    monkeypatch.setattr(settings.server, "host", "127.0.0.1")
    monkeypatch.setattr(settings.db, "dsn", dsn)
    monkeypatch.setattr(settings.db, "auto_migrate", True)
    monkeypatch.setattr(settings.secrets, "key", SecretStr(Fernet.generate_key().decode()))
    monkeypatch.setattr(settings.auth, "public_url", ORIGIN)
    monkeypatch.setattr(settings.auth, "registration_mode", RegistrationMode.open)
    monkeypatch.setattr(settings.auth, "admin_email", ADMIN_EMAIL)
    monkeypatch.setattr(settings.auth, "admin_password", SecretStr(ADMIN_PASSWORD))
    monkeypatch.setattr(settings.cors, "allow_origins", [ORIGIN])
    with TestClient(create_app(), base_url=ORIGIN) as client:
        yield client


def _admin(client: TestClient) -> dict[str, str]:
    login = client.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, headers=HEADERS)
    assert login.status_code == 200, login.text
    return {**HEADERS, "X-CSRF-Token": login.json()["csrf_token"]}


def _token_for(messages: list[dict[str, Any]], to: str) -> str:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        for message in messages:
            if to in message["rcpt_to"] and (found := re.search(r"/verify/([A-Za-z0-9_-]+)", message["text"] or "")):
                return found.group(1)
        time.sleep(0.05)
    raise AssertionError(f"письмо для {to} не пришло")


def _register(client: TestClient, email: str) -> str:
    client.cookies.clear()
    answer = client.post(
        "/api/v1/auth/register",
        json={"email": email, "name": "Анна", "password": PASSWORD, "invitation_token": None},
        headers=HEADERS,
    )
    assert answer.status_code == 200, answer.text
    return str(answer.json()["status"])


def _login_code(client: TestClient, email: str) -> int | str:
    client.cookies.clear()
    answer = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}, headers=HEADERS)
    return 200 if answer.status_code == 200 else answer.json()["code"]


def test__exempt_address__verified_by_mail__is_active_without_approval(
    stand: TestClient, mailbox: tuple[int, list[dict[str, Any]]]
) -> None:
    port, messages = mailbox
    admin = _admin(stand)
    smtp = {"host": "127.0.0.1", "port": port, "security": "none", "from_address": "studio@example.org"}
    assert stand.put("/api/admin/settings/smtp", json=smtp, headers=admin).status_code == 200
    rules = {"require_approval": True, "approval_exemptions": ["*.hse.ru", "rector@example.org"]}
    saved = stand.put("/api/admin/settings/registration", json=rules, headers=admin)
    assert saved.json()["approval_exemptions"] == ["*.hse.ru", "rector@example.org"]

    exempt = _register(stand, "ann@edu.hse.ru")
    queued = _register(stand, "bob@gmail.com")
    before = _login_code(stand, "ann@edu.hse.ru")
    for email in ("ann@edu.hse.ru", "bob@gmail.com"):
        verified = stand.post("/api/v1/auth/verify", json={"token": _token_for(messages, email)}, headers=HEADERS)
        assert verified.status_code == 204

    assert (exempt, queued) == ("check_email", "pending_approval")
    assert before == "email_not_verified"
    assert _login_code(stand, "ann@edu.hse.ru") == 200
    assert _login_code(stand, "bob@gmail.com") == "pending_approval"
    admin = _admin(stand)
    pending = stand.get("/api/admin/users", params={"status": "pending_approval"}, headers=admin).json()
    assert [u["email"] for u in pending["items"]] == ["bob@gmail.com"]
    audit = stand.get("/api/admin/audit", params={"action": "auth.approval_exempt"}, headers=admin).json()
    assert [(e["details"], e["actor"]["email"]) for e in audit["items"]] == [
        ({"rule": "*.hse.ru", "via": "email"}, "ann@edu.hse.ru")
    ]
