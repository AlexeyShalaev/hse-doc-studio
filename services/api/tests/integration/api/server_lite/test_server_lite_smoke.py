"""Смоук стенда server-lite без docker: настоящий create_app в server+experimental на пустой базе.

То же, что делает compose: автомиграция, админ из окружения, bootstrap отвечает, вход и «мои проекты» работают.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

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
ORIGIN = "http://localhost:8100"


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
    monkeypatch.setattr(settings.auth, "registration_mode", RegistrationMode.invite)
    monkeypatch.setattr(settings.auth, "admin_email", ADMIN_EMAIL)
    monkeypatch.setattr(settings.auth, "admin_password", SecretStr(ADMIN_PASSWORD))
    monkeypatch.setattr(settings.cors, "allow_origins", [ORIGIN])
    with TestClient(create_app(), base_url=ORIGIN) as client:
        yield client


def test__bootstrap__fresh_database__is_migrated_and_ready(stand: TestClient) -> None:
    body = stand.get("/api/v1/session/bootstrap").json()

    assert body["mode"] == "server"
    assert body["setup_state"] == "ready"
    assert body["user"] is None
    assert body["auth"]["registration_mode"] == "invite"


def test__health__ready_and_live__are_ok(stand: TestClient) -> None:
    assert stand.get("/health/ready").json()["status"] == "ok"
    assert stand.get("/health").json() == {"status": "ok"}


def test__login__env_admin__sees_empty_project_list(stand: TestClient) -> None:
    login = stand.post(
        "/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, headers={"Origin": ORIGIN}
    )

    assert login.status_code == 200
    assert login.json()["user"]["is_instance_admin"] is True
    # Серверный режим отдаёт каталог страницей.
    assert stand.get("/api/v1/projects").json()["items"] == []


def test__projects__anonymous__is_unauthorized(stand: TestClient) -> None:
    assert stand.get("/api/v1/projects").status_code == 401


def test__docs__server_mode__not_mounted(stand: TestClient) -> None:
    # Swagger, ReDoc и схема лежат вне /api/v1 и гардом не закрыты: на сервере их нет вовсе.
    for path in ("/system/docs", "/system/redoc", "/system/openapi.json"):
        body = stand.get(path).text.lower()
        assert "swagger-ui" not in body
        assert "redoc" not in body
        assert '"openapi"' not in body
