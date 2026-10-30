"""Швы серверного режима, которые раньше искали проекты в локальном индексе папок (на сервере он пуст).

Реестр удалённых репозиториев и список проектов с доступом читают каталог в БД, перенос проекта на сервере
отвечает явным кодом, копия name/kind/lang в каталоге обновляется после переименования, а схема OpenAPI
строится в обоих режимах.
"""

from __future__ import annotations

import time
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
    monkeypatch.setattr(settings.auth, "experimental", True)
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


def _create(client: TestClient, headers: dict[str, str]) -> str:
    body = {
        "name": "Курсовая: швы",
        "pack_id": "hse-cs-sse",
        "template_id": "coursework",
        "version": "2026.1",
        "lang": "ru",
        "authors": [{"name": "Админ"}],
    }
    response = client.post("/api/v1/projects", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _call(stand: TestClient, coro_fn):  # type: ignore[no-untyped-def]
    """Запускает корутину в цикле приложения: у пула БД он один."""
    return stand.portal.call(coro_fn)  # type: ignore[attr-defined]


def test__move__server__answers_a_clear_code(stand: TestClient) -> None:
    owner = _Session(stand, ADMIN_EMAIL, ADMIN_PASSWORD)
    with owner as client:
        project_id = _create(client, owner.headers)
        moved = client.post(f"/api/v1/projects/{project_id}/move", json={"folder": "/tmp/x"}, headers=owner.headers)

        assert moved.status_code == 409
        assert moved.json()["detail"]["code"] == "not_available_in_server_mode"
        caps = client.get("/api/v1/session/bootstrap").json()["capabilities"]
        assert caps["move_project"] is False


def test__rename__mirrors_name_into_the_catalog_without_errors(
    stand: TestClient, capfd: pytest.CaptureFixture[str]
) -> None:
    from hse_doc_studio.infra.db.orm.projects import ProjectRow
    from hse_doc_studio.infra.db.session import SessionProvider
    from sqlalchemy import select

    owner = _Session(stand, ADMIN_EMAIL, ADMIN_PASSWORD)
    with owner as client:
        project_id = _create(client, owner.headers)
        assert (
            client.patch(
                f"/api/v1/projects/{project_id}", json={"name": "Новое имя"}, headers=owner.headers
            ).status_code
            == 200
        )

        async def _name() -> str:
            container = stand.app.state.dishka_container  # type: ignore[attr-defined]
            sessions = await container.get(SessionProvider)
            async with sessions.use() as session:
                row = (
                    await session.execute(select(ProjectRow.name).where(ProjectRow.id == uuid.UUID(project_id)))
                ).scalar_one()
            return str(row)

        for _ in range(50):
            name = _call(stand, _name)
            if name == "Новое имя":
                break
            time.sleep(0.1)
        assert name == "Новое имя"
    assert "copy failed" not in capfd.readouterr().out


def test__remote_registry_sees_server_projects_and_credential_usage_ignores_the_project_config(
    stand: TestClient, tmp_path: Path
) -> None:
    from hse_doc_studio.core.access.context import set_current_actor
    from hse_doc_studio.core.access.entities import Actor
    from hse_doc_studio.core.git_sync.protocols import IGitCredentialUsage, IGitRemoteRegistry
    from hse_doc_studio.core.projects.locator import IProjectLocator
    from hse_doc_studio.infra.git_sync.remote_registry import store_has_remote

    owner = _Session(stand, ADMIN_EMAIL, ADMIN_PASSWORD)
    credential = uuid.uuid4()
    with owner as client:
        project_id = _create(client, owner.headers)
        owner_id = client.get("/api/v1/session/bootstrap").json()["user"]["id"]

        async def _folder() -> Path:
            container = stand.app.state.dishka_container  # type: ignore[attr-defined]
            locator = await container.get(IProjectLocator)
            folder = await locator.folder_of(uuid.UUID(project_id))
            assert folder is not None
            return folder

        folder = _call(stand, _folder)
        config = folder / ".hse-studio" / "git" / "config"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(
            f'[remote "origin"]\n\turl = file:///srv/x.git\n[hse]\n\tcredential = {credential}\n', encoding="utf-8"
        )
        assert store_has_remote(folder)

        async def _seen() -> tuple[list[Path], dict]:  # type: ignore[type-arg]
            container = stand.app.state.dishka_container  # type: ignore[attr-defined]
            registry = await container.get(IGitRemoteRegistry)
            usage = await container.get(IGitCredentialUsage)
            set_current_actor(Actor.user(owner_id))
            try:
                return await registry.list(), await usage.by_credential()
            finally:
                set_current_actor(None)

        folders, used = _call(stand, _seen)
        assert [f.resolve() for f in folders] == [folder.resolve()]
        # Использование доступа берётся из привязок в базе, а не из конфига, который могла принести синхронизация.
        assert used == {}


def test__openapi__server__schema_builds_and_the_docs_urls_are_off(stand: TestClient) -> None:
    schema = stand.app.openapi()  # type: ignore[attr-defined]

    assert "/api/v1/projects" in schema["paths"]
    assert stand.get("/system/openapi.json").status_code != 200


def test__openapi__local__schema_builds(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(settings, "mode", StudioMode.local)
    monkeypatch.setattr(settings, "data_dir", tmp_path)

    schema = create_app().openapi()

    assert "/api/v1/projects" in schema["paths"]
    assert "/api/v1/auth/register" in schema["paths"]
