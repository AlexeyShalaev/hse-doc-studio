"""Живое серверное приложение на Postgres для трека invites: стенд личных раннеров плюс сессии и организации.

Люди работают персональными токенами (как в `personal/conftest.py`); сценарии, которые принимают только сессию
(запрос доступа), получают куки входа на время вызова.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient
from hse_doc_studio.infra.db.orm.orgs import OrgMemberRow, OrgRow
from httpx2 import Response

from tests.integration.api.personal.conftest import ORIGIN, PASSWORD, Person, Stand, seed_shared_project, stand

__all__ = ["Person", "Session", "Stand", "add_member", "login", "make_org", "seed_shared_project", "stand"]


@dataclass
class Session:
    """Вошедший по паролю: куки подставляются на время вызова, как у браузера."""

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

    def post(self, path: str, **kwargs: Any) -> Response:
        return self.request("POST", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Response:
        return self.request("DELETE", path, **kwargs)


def login(stand: Stand, email: str, password: str = PASSWORD) -> Session:
    response = stand.client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}, headers={"Origin": ORIGIN}
    )
    assert response.status_code == 200, response.text
    cookies = dict(stand.client.cookies)
    stand.client.cookies.clear()
    return Session(stand.client, cookies, {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf_token"]})


async def make_org(stand: Stand, slug: str, *members: tuple[Person, str]) -> str:
    """Организация с участниками (роль owner, admin или member); возвращает её id."""
    org_id = f"org_{uuid4().hex[:12]}"
    async with stand.sessions.use() as db:
        db.add(OrgRow(id=org_id, slug=slug, name=slug.capitalize()))
        await db.flush()
        for person, role in members:
            db.add(OrgMemberRow(org_id=org_id, user_id=person.id, role=role))
        await db.flush()
    return org_id


async def add_member(stand: Stand, project_id: str, person: Person, role: str, **flags: bool) -> None:
    from uuid import UUID  # noqa: PLC0415

    from hse_doc_studio.infra.db.orm.projects import ProjectMemberRow  # noqa: PLC0415

    async with stand.sessions.use() as db:
        db.add(
            ProjectMemberRow(
                project_id=UUID(project_id), principal_kind="user", principal_id=person.id, role=role, **flags
            )
        )
        await db.flush()
