"""Стенд ссылок доступа: настоящий `create_app` в server на Postgres, люди с cookie и проект владельца.

Один TestClient (один цикл событий и пул БД); у каждого человека и гостя свой набор cookie и заголовков.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.entrypoint import create_app
from hse_doc_studio.core.access.entities import Role
from hse_doc_studio.core.access.repositories import IProjectMemberRepository, ProjectMemberGrant
from hse_doc_studio.core.identity.entities import RegistrationMode, User, UserStatus
from hse_doc_studio.core.identity.normalize import normalize_email
from hse_doc_studio.core.identity.protocols import ICredentialRepository, IPasswordHasher, IUserRepository
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.core.orgs.entities import Org, OrgMember, OrgRole
from hse_doc_studio.core.orgs.protocols import IOrgRepository
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.infra.di.containers.api import create_container
from pydantic import SecretStr

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

ADMIN_EMAIL = "admin@example.org"
ADMIN_PASSWORD = "stand-admin-password"  # noqa: S105 — тестовое значение
USER_PASSWORD = "user-password-1234"  # noqa: S105 — тестовое значение
ORIGIN = "http://localhost:8100"
PROJECT_NAME = "ВКР: Анализ требований"


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
    monkeypatch.setattr(settings.rate_limit, "enabled", False)
    with TestClient(create_app(), base_url=ORIGIN) as client:
        yield client


async def _in_container[T](work: Any) -> T:
    container = create_container(StudioMode.server)
    try:
        return await work(container)  # type: ignore[no-any-return]
    finally:
        await container.close()


def add_user(email: str, name: str) -> str:
    async def work(container: Any) -> str:
        users = await container.get(IUserRepository)
        credentials = await container.get(ICredentialRepository)
        hasher = await container.get(IPasswordHasher)
        uow = await container.get(IUnitOfWork)
        user = User(
            id=uuid.uuid4().hex,
            email=email,
            email_normalized=normalize_email(email),
            name=name,
            status=UserStatus.active,
            created_at=datetime.now(UTC),
            email_verified=True,
            locale="ru",
        )
        async with uow.begin():
            await users.add(user)
            await credentials.set_hash(user.id, hasher.hash(USER_PASSWORD))
        return user.id

    return asyncio.run(_in_container(work))


def set_member(
    project_id: str, user_id: str, role: Role, *, can_share: bool = False, show_sources: bool = True
) -> None:
    async def work(container: Any) -> None:
        members = await container.get(IProjectMemberRepository)
        uow = await container.get(IUnitOfWork)
        grant = ProjectMemberGrant("user", user_id, role, can_share=can_share, show_sources=show_sources)
        async with uow.begin():
            await members.set_member(uuid.UUID(project_id), grant)

    asyncio.run(_in_container(work))


def add_org(org_id: str, slug: str, members: dict[str, OrgRole], policies: dict[str, object] | None = None) -> None:
    async def work(container: Any) -> None:
        orgs = await container.get(IOrgRepository)
        uow = await container.get(IUnitOfWork)
        now = datetime.now(UTC)
        org = Org(id=org_id, slug=slug, name=slug.upper(), created_at=now)
        if policies is not None:
            org = Org(id=org_id, slug=slug, name=slug.upper(), created_at=now, policies=policies)
        async with uow.begin():
            await orgs.add(org)
            for user_id, role in members.items():
                await orgs.add_member(OrgMember(org_id, user_id, role, now))

    asyncio.run(_in_container(work))


def run_sql(sql: str, **params: object) -> None:
    from sqlalchemy import text  # noqa: PLC0415

    async def work(container: Any) -> None:
        from hse_doc_studio.infra.db.session import SessionProvider  # noqa: PLC0415

        sessions = await container.get(SessionProvider)
        async with sessions.use() as db:
            await db.execute(text(sql), params)

    asyncio.run(_in_container(work))


class Person:
    """Набор cookie и заголовков одного человека или гостя в общем TestClient."""

    def __init__(self, client: TestClient, email: str | None = None, password: str | None = None) -> None:
        self.client = client
        self.headers: dict[str, str] = {"Origin": ORIGIN}
        client.cookies.clear()
        if email is not None and password is not None:
            login = client.post("/api/v1/auth/login", json={"email": email, "password": password}, headers=self.headers)
            assert login.status_code == 200, login.text
            self.headers["X-CSRF-Token"] = login.json()["csrf_token"]
        self.cookies = dict(client.cookies.items())

    def __enter__(self) -> TestClient:
        self.client.cookies.clear()
        for name, value in self.cookies.items():
            self.client.cookies.set(name, value)
        return self.client

    def __exit__(self, *_exc: object) -> None:
        # Гость получает cookie по ходу работы: запоминаем, что выдал сервер.
        self.cookies = dict(self.client.cookies.items())
        self.client.cookies.clear()

    def request(self, method: str, url: str, **kwargs: Any) -> Any:
        with self as client:
            headers = {**self.headers, **kwargs.pop("headers", {})}
            return client.request(method, url, headers=headers, **kwargs)

    def get(self, url: str, **kwargs: Any) -> Any:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> Any:
        return self.request("POST", url, **kwargs)

    def patch(self, url: str, **kwargs: Any) -> Any:
        return self.request("PATCH", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> Any:
        return self.request("PUT", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> Any:
        return self.request("DELETE", url, **kwargs)


class World:
    """Анна владеет проектом; Борис редактор с правом делиться, Вера редактор без права, Глеб читатель,
    Дина чужая."""

    def __init__(self, stand: TestClient) -> None:
        self.stand = stand
        self.ids = {
            key: add_user(f"{key}@example.org", name)
            for key, name in (
                ("anna", "Анна Петрова"),
                ("boris", "Борис"),
                ("vera", "Вера Смирнова"),
                ("gleb", "Глеб"),
                ("dina", "Дина"),
            )
        }
        self.anna = self.login("anna")
        created = self.anna.post(
            "/api/v1/projects",
            json={
                "name": PROJECT_NAME,
                "pack_id": "hse-cs-sse",
                "template_id": "coursework",
                "version": "2026.1",
                "lang": "ru",
                "authors": [{"name": "Анна"}],
            },
        )
        assert created.status_code == 201, created.text
        self.project_id = str(created.json()["id"])
        set_member(self.project_id, self.ids["boris"], Role.editor, can_share=True)
        set_member(self.project_id, self.ids["vera"], Role.editor)
        set_member(self.project_id, self.ids["gleb"], Role.reader, show_sources=False)
        self.boris = self.login("boris")
        self.vera = self.login("vera")
        self.gleb = self.login("gleb")
        self.dina = self.login("dina")

    def login(self, key: str) -> Person:
        return Person(self.stand, f"{key}@example.org", USER_PASSWORD)

    def anonymous(self) -> Person:
        return Person(self.stand)

    @property
    def links_url(self) -> str:
        return f"/api/v1/projects/{self.project_id}/links"

    def create_link(self, person: Person | None = None, **body: Any) -> dict[str, Any]:
        payload = {"label": "Для научрука", "role": "reader", **body}
        response = (person or self.anna).post(self.links_url, json=payload)
        assert response.status_code == 201, response.text
        return dict(response.json())


@pytest.fixture
def world(stand: TestClient) -> World:
    return World(stand)


def token_of(link: dict[str, Any]) -> str:
    return str(link["url"]).rsplit("/s/", 1)[1]
