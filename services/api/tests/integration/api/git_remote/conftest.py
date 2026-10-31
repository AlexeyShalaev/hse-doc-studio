"""Живой сервер Студии на случайном порту (uvicorn в потоке) и настоящий клиент git против него.

git не умеет ходить в TestClient, поэтому приложение `create_app` поднимается настоящим HTTP-сервером. Люди
создаются строками в базе, входят паролем и выпускают токены через API; проекты создаются `POST /projects`.
"""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
import uvicorn
from cryptography.fernet import Fernet
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.entrypoint import create_app
from hse_doc_studio.core.identity.entities import RegistrationMode
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.infra.identity.argon2_hasher import Argon2PasswordHasher
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

PASSWORD = "git-remote-password"  # noqa: S105 — тестовое значение
ADMIN_EMAIL = "git-admin@example.org"


@dataclass
class Person:
    id: str
    email: str
    name: str
    session: dict[str, str] = field(default_factory=dict)
    cookies: dict[str, str] = field(default_factory=dict)
    api: dict[str, str] = field(default_factory=dict)


@dataclass
class Live:
    base: str
    dsn: str
    tmp: Path

    def client(self) -> httpx.Client:
        return httpx.Client(base_url=self.base, timeout=60)

    def sql(self, statement: str, **params: Any) -> list[Any]:
        """Отдельный движок на своём цикле: тест синхронный, у сервера в потоке свой цикл и пул."""

        async def run() -> list[Any]:
            engine = create_async_engine(self.dsn)
            try:
                async with engine.begin() as db:
                    result = await db.execute(text(statement), params)
                    return list(result.all()) if result.returns_rows else []
            finally:
                await engine.dispose()

        return asyncio.run(run())

    def person(self, name: str) -> Person:
        user_id = uuid4().hex
        email = f"{name}-{user_id[:6]}@example.org"
        self.sql(
            "INSERT INTO users (id, email, email_normalized, name, status, email_verified, is_instance_admin, "
            "created_at) VALUES (:id, :e, :e, :n, 'active', true, false, :at)",
            id=user_id,
            e=email,
            n=name,
            at=datetime.now(UTC),
        )
        self.sql(
            "INSERT INTO password_credentials (user_id, password_hash) VALUES (:id, :h)",
            id=user_id,
            h=Argon2PasswordHasher().hash(PASSWORD),
        )
        with self.client() as client:
            login = client.post(
                "/api/v1/auth/login", json={"email": email, "password": PASSWORD}, headers={"Origin": self.base}
            )
            assert login.status_code == 200, login.text
            person = Person(id=user_id, email=email, name=name)
            person.cookies = dict(client.cookies)
            person.session = {"Origin": self.base, "X-CSRF-Token": login.json()["csrf_token"]}
        person.api = {"Authorization": f"Bearer {self.token(person, ['api'])}"}
        return person

    def token(self, person: Person, scopes: list[str], name: str = "tests") -> str:
        with self.client() as client:
            created = client.post(
                "/api/v1/account/tokens",
                json={"name": name, "scopes": scopes, "expires_in_days": 30},
                headers=person.session,
                cookies=person.cookies,
            )
        assert created.status_code == 201, created.text
        return str(created.json()["token"])

    def call(self, method: str, path: str, person: Person | None = None, **kwargs: Any) -> httpx.Response:
        with self.client() as client:
            headers = {**(person.api if person else {}), **kwargs.pop("headers", {})}
            return client.request(method, path, headers=headers, **kwargs)

    def create_project(self, owner: Person, name: str = "Курсовая: git") -> str:
        body = {
            "name": name,
            "pack_id": "hse-cs-sse",
            "template_id": "coursework",
            "version": "2026.1",
            "lang": "ru",
            "authors": [{"name": owner.name}],
        }
        response = self.call("POST", "/api/v1/projects", owner, json=body)
        assert response.status_code in {200, 201}, response.text
        return str(response.json()["id"])

    def add_member(self, project_id: str, person: Person, role: str, **flags: Any) -> None:
        self.sql(
            "INSERT INTO project_members (project_id, principal_kind, principal_id, role, persona, can_share, "
            "show_sources, can_edit_all) VALUES (:p, 'user', :u, :r, :persona, false, :src, :all)",
            p=UUID(project_id),
            u=person.id,
            r=role,
            persona=flags.get("persona"),
            src=flags.get("show_sources", True),
            all=flags.get("can_edit_all", False),
        )

    def repo_url(self, project_id: str, token: str | None = None) -> str:
        host = self.base.removeprefix("http://")
        auth = f"x:{token}@" if token else ""
        return f"http://{auth}{host}/git/{project_id}.git"


def git(*args: str, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(cwd or Path.cwd()),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "LC_ALL": "C",
        "GIT_AUTHOR_NAME": "Tester",
        "GIT_AUTHOR_EMAIL": "tester@example.org",
        "GIT_COMMITTER_NAME": "Tester",
        "GIT_COMMITTER_EMAIL": "tester@example.org",
    }
    result = subprocess.run(  # noqa: S603 — тест запускает git с известными аргументами
        ["git", "-c", "credential.helper=", "-c", "protocol.version=2", *args],  # noqa: S607
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if check:
        assert result.returncode == 0, result.stderr
    return result


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def live(pg_migrated_engine: AsyncEngine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Live]:
    dsn = pg_migrated_engine.url.render_as_string(hide_password=False)
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    monkeypatch.setattr(settings, "mode", StudioMode.server)
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings, "host_data_dir", None)
    monkeypatch.setattr(settings, "docker_binary", str(tmp_path / "no-docker"))
    monkeypatch.setattr(settings.server, "host", "127.0.0.1")
    monkeypatch.setattr(settings.db, "dsn", dsn)
    monkeypatch.setattr(settings.db, "auto_migrate", True)
    monkeypatch.setattr(settings.secrets, "key", SecretStr(Fernet.generate_key().decode()))
    monkeypatch.setattr(settings.auth, "public_url", base)
    monkeypatch.setattr(settings.auth, "registration_mode", RegistrationMode.invite)
    monkeypatch.setattr(settings.cors, "allow_origins", [base])
    monkeypatch.setattr(settings.auth, "admin_email", ADMIN_EMAIL)
    monkeypatch.setattr(settings.auth, "admin_password", SecretStr(PASSWORD))
    server = uvicorn.Server(uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 60
    while not server.started:
        assert thread.is_alive(), "uvicorn не стартовал"
        assert time.monotonic() < deadline, "uvicorn не стартовал за минуту"
        time.sleep(0.05)
    try:
        yield Live(base=base, dsn=dsn, tmp=tmp_path)
    finally:
        server.should_exit = True
        thread.join(timeout=30)
