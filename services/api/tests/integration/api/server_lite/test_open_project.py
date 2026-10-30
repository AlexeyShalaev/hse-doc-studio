"""Открытие созданного проекта на сервере: владелец видит рабочее место, чужой пользователь и аноним нет.

Регрессия: GET /projects/{id} искал проект перебором локального индекса папок, который на сервере пуст,
и владелец получал 404 на только что созданный проект. Проекты демо-данных стенда (scripts/dev/server-lite/seed.py)
создаются тем же запросом POST /projects от имени пользователя, поэтому отдельного пути создания нет.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.entrypoint import create_app
from hse_doc_studio.core.identity.entities import RegistrationMode, User, UserStatus
from hse_doc_studio.core.identity.normalize import normalize_email
from hse_doc_studio.core.identity.protocols import ICredentialRepository, IPasswordHasher, IUserRepository
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.infra.di.containers.api import create_container
from pydantic import SecretStr

pytestmark = pytest.mark.pg

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

ADMIN_EMAIL = "admin@example.org"
ADMIN_PASSWORD = "stand-admin-password"  # noqa: S105 — тестовое значение
OTHER_EMAIL = "boris@example.org"
OTHER_PASSWORD = "other-user-password"  # noqa: S105 — тестовое значение
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


async def _add_user(email: str, password: str) -> None:
    container = create_container(StudioMode.server)
    try:
        users = await container.get(IUserRepository)
        credentials = await container.get(ICredentialRepository)
        hasher = await container.get(IPasswordHasher)
        uow = await container.get(IUnitOfWork)
        user = User(
            id=uuid.uuid4().hex,
            email=email,
            email_normalized=normalize_email(email),
            name="Борис",
            status=UserStatus.active,
            created_at=datetime.now(UTC),
            email_verified=True,
            locale="ru",
        )
        async with uow.begin():
            await users.add(user)
            await credentials.set_hash(user.id, hasher.hash(password))
    finally:
        await container.close()


class _Session:
    """Один TestClient (у него один цикл событий и один пул БД), у каждого пользователя свои куки."""

    def __init__(self, client: TestClient, email: str | None, password: str | None) -> None:
        self._client = client
        self.headers: dict[str, str] = {"Origin": ORIGIN}
        client.cookies.clear()
        if email is not None and password is not None:
            login = client.post("/api/v1/auth/login", json={"email": email, "password": password}, headers=self.headers)
            assert login.status_code == 200
            self.headers["X-CSRF-Token"] = login.json()["csrf_token"]
        self._cookies = dict(client.cookies.items())

    def __enter__(self) -> TestClient:
        self._client.cookies.clear()
        for name, value in self._cookies.items():
            self._client.cookies.set(name, value)
        return self._client

    def __exit__(self, *_exc: object) -> None:
        self._client.cookies.clear()


def _create_project(client: TestClient, headers: dict[str, str]) -> str:
    body = {
        "name": "Курсовая: открытие",
        "pack_id": "hse-cs-sse",
        "template_id": "coursework",
        "version": "2026.1",
        "lang": "ru",
        "authors": [{"name": "Админ"}],
    }
    response = client.post("/api/v1/projects", json=body, headers=headers)
    assert response.status_code in {200, 201}, response.text
    return str(response.json()["id"])


def test__open_project__owner_works_stranger_gets_404_anonymous_401(stand: TestClient) -> None:
    asyncio.run(_add_user(OTHER_EMAIL, OTHER_PASSWORD))
    owner = _Session(stand, ADMIN_EMAIL, ADMIN_PASSWORD)
    stranger = _Session(stand, OTHER_EMAIL, OTHER_PASSWORD)
    anonymous = _Session(stand, None, None)
    with owner as client:
        base = f"/api/v1/projects/{_create_project(client, owner.headers)}"

        project = client.get(base)
        assert project.status_code == 200, project.text
        assert project.json()["name"] == "Курсовая: открытие"
        tree = client.get(f"{base}/files")
        assert tree.status_code == 200, tree.text
        assert client.put(f"{base}/files/notes/a.txt", content=b"hello", headers=owner.headers).status_code in {
            200,
            204,
        }
        read = client.get(f"{base}/files/notes/a.txt")
        assert read.status_code == 200
        assert read.content == b"hello"
        documents = client.get(f"{base}/documents")
        assert documents.status_code == 200, documents.text
        assert documents.json()
        assert client.get(f"{base}/vcs/status").status_code == 200
        assert client.get(f"{base}/git").status_code == 200
        assert [item["name"] for item in client.get("/api/v1/projects").json()] == ["Курсовая: открытие"]
        assert client.post(f"{base}/vcs/snapshots", json={"message": "m"}, headers=owner.headers).status_code == 200
        assert client.post(f"{base}/chats", json={}, headers=owner.headers).status_code == 201
        assert client.patch(base, json={"name": "Новое имя"}, headers=owner.headers).status_code == 200

    paths = ("", "/files", "/files/notes/a.txt", "/documents", "/vcs/status", "/git")
    with stranger as client:
        for path in paths:
            assert client.get(f"{base}{path}").status_code == 404, path
        assert client.put(f"{base}/files/notes/a.txt", content=b"x", headers=stranger.headers).status_code == 404
        assert client.post(f"{base}/vcs/snapshots", json={"message": "m"}, headers=stranger.headers).status_code == 404
        assert client.post(f"{base}/chats", json={}, headers=stranger.headers).status_code == 404
        assert client.patch(base, json={"name": "Взлом"}, headers=stranger.headers).status_code == 404
        assert client.delete(base, headers=stranger.headers).status_code == 404
        assert client.get("/api/v1/projects").json() == []
    with anonymous as client:
        for path in paths:
            assert client.get(f"{base}{path}").status_code == 401, path


def test__project_detail__server__does_not_leak_the_volume_path(stand: TestClient) -> None:
    owner = _Session(stand, ADMIN_EMAIL, ADMIN_PASSWORD)
    with owner as client:
        body = {
            "name": "Без пути",
            "pack_id": "hse-cs-sse",
            "template_id": "coursework",
            "version": "2026.1",
            "lang": "ru",
            "authors": [{"name": "Админ"}],
        }
        created = client.post("/api/v1/projects", json=body, headers=owner.headers)
        assert created.status_code == 201, created.text
        detail = client.get(f"/api/v1/projects/{created.json()['id']}")

        assert created.json()["folder"] == ""
        assert detail.json()["folder"] == ""
        # Организаций в M1 нет: непустой owner_org_slug не должен молча давать личный проект.
        rejected = client.post("/api/v1/projects", json={**body, "owner_org_slug": "mspin"}, headers=owner.headers)
        assert rejected.status_code == 422
        # Клонирование принимает папку сервера от клиента: на сервере маршрута нет.
        clone = client.post(
            "/api/v1/git/clone", json={"url": "https://example.org/r.git", "folder": "/tmp/x"}, headers=owner.headers
        )
        assert clone.status_code == 404
