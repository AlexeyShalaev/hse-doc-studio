"""Живое приложение серверного режима на Postgres для личных раннеров: люди с токенами доступа и раннеры.

Настоящий `create_app` (как стенд server-lite), люди создаются строками в базе и работают персональными
токенами доступа (`Authorization: Bearer`), чтобы тесты не возились с cookie и CSRF.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.entrypoint import create_app
from hse_doc_studio.core.identity.entities import RegistrationMode
from hse_doc_studio.core.jobs.wire import RUNNER_PROTOCOL_VERSION
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.orm.identity import PasswordCredentialRow, UserRow
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.identity.argon2_hasher import Argon2PasswordHasher
from httpx2 import Response
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine

ORIGIN = "http://localhost:8100"
PASSWORD = "personal-runner-password"  # noqa: S105 — тестовое значение


@dataclass
class Person:
    id: str
    email: str
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class AdminCalls:
    client: TestClient
    cookies: dict[str, str]
    headers: dict[str, str]

    def request(self, method: str, path: str, **kwargs: Any) -> Response:
        for name, value in self.cookies.items():
            self.client.cookies.set(name, value)
        try:
            return self.client.request(method, path, headers=self.headers, **kwargs)
        finally:
            self.client.cookies.clear()

    def get(self, path: str, **kwargs: Any) -> Response:
        return self.request("GET", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> Response:
        return self.request("PUT", path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> Response:
        return self.request("PATCH", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Response:
        return self.request("POST", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Response:
        return self.request("DELETE", path, **kwargs)


@dataclass
class Stand:
    client: TestClient
    sessions: SessionProvider
    engine: AsyncEngine

    async def person(self, name: str, *, admin: bool = False) -> Person:
        user_id = str(uuid4())
        email = f"{name}-{user_id[:6]}@example.org"
        async with self.sessions.use() as db:
            db.add(
                UserRow(
                    id=user_id,
                    email=email,
                    email_normalized=email,
                    name=name,
                    status="active",
                    email_verified=True,
                    is_instance_admin=admin,
                    created_at=datetime.now(UTC),
                )
            )
            await db.flush()
            db.add(PasswordCredentialRow(user_id=user_id, password_hash=Argon2PasswordHasher().hash(PASSWORD)))
        login = self.client.post(
            "/api/v1/auth/login", json={"email": email, "password": PASSWORD}, headers={"Origin": ORIGIN}
        )
        assert login.status_code == 200, login.text
        csrf = login.json()["csrf_token"]
        created = self.client.post(
            "/api/v1/account/tokens",
            json={"name": "tests", "scopes": ["api"], "expires_in_days": 30},
            headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
        )
        assert created.status_code == 201, created.text
        self.client.cookies.clear()
        return Person(id=user_id, email=email, headers={"Authorization": f"Bearer {created.json()['token']}"})

    def admin(self) -> AdminCalls:
        """Админка принимает только сессию: вход админа из окружения, cookie подставляется на время вызова."""
        login = self.client.post(
            "/api/v1/auth/login",
            json={"email": "stand-admin@example.org", "password": PASSWORD},
            headers={"Origin": ORIGIN},
        )
        assert login.status_code == 200, login.text
        cookies = dict(self.client.cookies)
        self.client.cookies.clear()
        return AdminCalls(self.client, cookies, {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]})

    def register(self, secret: str, name: str = "MacBook", tags: tuple[str, ...] = ("tex", "pack")) -> dict[str, str]:
        """Регистрация раннера токеном; возвращает заголовки с его постоянным токеном."""
        response = self.client.post(
            "/api/runner/v1/register",
            json={
                "name": name,
                "protocol": RUNNER_PROTOCOL_VERSION,
                "version": "0.3.0",
                "tags": list(tags),
                "concurrency": 1,
                "resource_class": "standard",
            },
            headers={"Authorization": f"Bearer {secret}"},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        return {"Authorization": f"Bearer {body['runner_token']}", "X-Runner-Id": body["runner_id"]}

    def personal_runner(self, owner: Person, name: str = "MacBook") -> dict[str, str]:
        token = self.client.post("/api/v1/account/runner-tokens", json={"label": name}, headers=owner.headers)
        assert token.status_code == 201, token.text
        return self.register(token.json()["secret"], name)


@pytest_asyncio.fixture
async def stand(
    pg_migrated_engine: AsyncEngine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Stand]:
    dsn = pg_migrated_engine.url.render_as_string(hide_password=False)
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
    monkeypatch.setattr(settings.cors, "allow_origins", [ORIGIN])
    # Админ из окружения закрывает мастер первого запуска, как на стенде.
    monkeypatch.setattr(settings.auth, "admin_email", "stand-admin@example.org")
    monkeypatch.setattr(settings.auth, "admin_password", SecretStr(PASSWORD))
    with TestClient(create_app(), base_url=ORIGIN) as client:
        yield Stand(client, SessionProvider(create_sessionmaker(pg_migrated_engine)), pg_migrated_engine)


async def seed_shared_project(stand: Stand, owner: Person, *coauthors: tuple[Person, str]) -> str:
    """Личный проект владельца с участниками; папку на томе маршрутам настроек сборок не нужно."""
    from hse_doc_studio.infra.db.orm.projects import ProjectMemberRow, ProjectRow  # noqa: PLC0415

    project_id = uuid4()
    async with stand.sessions.use() as db:
        db.add(
            ProjectRow(
                id=project_id,
                name="Диплом",
                owner_user_id=owner.id,
                workspace_path=str(project_id),
                kind="thesis",
                lang="ru",
            )
        )
        await db.flush()
        db.add(ProjectMemberRow(project_id=project_id, principal_kind="user", principal_id=owner.id, role="owner"))
        for person, role in coauthors:
            db.add(ProjectMemberRow(project_id=project_id, principal_kind="user", principal_id=person.id, role=role))
        await db.flush()
    return str(project_id)
