"""Архивный PDF сборки на сервере: владельцу 307 на короткую ссылку бакета, чужому 404, анониму 401.

С каталожным хранилищем ссылок нет, и тот же маршрут отдаёт байты.
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
from hse_doc_studio.infra.jobs.s3_artifact_store import archived_pdf_key
from pydantic import SecretStr

from tests.fixtures.s3 import S3Target

pytestmark = pytest.mark.pg

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

ADMIN_EMAIL = "admin@example.org"
ADMIN_PASSWORD = "stand-admin-password"  # noqa: S105 — тестовое значение
OTHER_EMAIL = "boris@example.org"
OTHER_PASSWORD = "other-user-password"  # noqa: S105 — тестовое значение
ORIGIN = "http://localhost:8100"


def _configure(pg_engine: AsyncEngine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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


@pytest.fixture
def stand(
    pg_engine: AsyncEngine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, s3_target: S3Target
) -> Iterator[TestClient]:
    _configure(pg_engine, tmp_path, monkeypatch)
    monkeypatch.setattr(settings.s3, "bucket", s3_target.bucket)
    monkeypatch.setattr(settings.s3, "endpoint", s3_target.endpoint_url)
    monkeypatch.setattr(settings.s3, "cors_origins", [ORIGIN])
    with TestClient(create_app(), base_url=ORIGIN) as client:
        yield client


@pytest.fixture
def disk_stand(pg_engine: AsyncEngine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    _configure(pg_engine, tmp_path, monkeypatch)
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


DOC = "main"
COMPILE_ID = uuid.uuid4()
PDF = b"%PDF-1.7 archived"


def _pdf_url(project_id: str) -> str:
    return f"/api/v1/projects/{project_id}/documents/{DOC}/compiles/{COMPILE_ID}/pdf"


def test__archived_pdf__s3__owner_gets_307_stranger_404_anonymous_401(stand: TestClient, s3_target: S3Target) -> None:
    asyncio.run(_add_user(OTHER_EMAIL, OTHER_PASSWORD))
    owner = _Session(stand, ADMIN_EMAIL, ADMIN_PASSWORD)
    stranger = _Session(stand, OTHER_EMAIL, OTHER_PASSWORD)
    anonymous = _Session(stand, None, None)
    with owner as client:
        project_id = _create_project(client, owner.headers)
        url = _pdf_url(project_id)
        assert client.get(url, follow_redirects=False).status_code == 404
        key = archived_pdf_key(uuid.UUID(project_id), DOC, COMPILE_ID)
        s3_target.client.put_object(Bucket=s3_target.bucket, Key=key, Body=PDF, ContentType="application/pdf")

        response = client.get(url, follow_redirects=False)

        assert response.status_code == 307, response.text
        assert key in response.headers["location"]
        assert response.headers["cache-control"] == "no-store"
        assert s3_target.client.get_bucket_cors(Bucket=s3_target.bucket)["CORSRules"][0]["AllowedOrigins"] == [ORIGIN]
    with stranger as client:
        assert client.get(url, follow_redirects=False).status_code == 404
    with anonymous as client:
        assert client.get(url, follow_redirects=False).status_code == 401


def test__archived_pdf__disk_store__owner_gets_bytes(disk_stand: TestClient, tmp_path: Path) -> None:
    owner = _Session(disk_stand, ADMIN_EMAIL, ADMIN_PASSWORD)
    with owner as client:
        project_id = _create_project(client, owner.headers)
        key = archived_pdf_key(uuid.UUID(project_id), DOC, COMPILE_ID)
        target = tmp_path / "objects" / key
        target.parent.mkdir(parents=True)
        target.write_bytes(PDF)

        response = client.get(_pdf_url(project_id), follow_redirects=False)

        assert response.status_code == 200, response.text
        assert response.content == PDF
        assert response.headers["content-type"] == "application/pdf"
