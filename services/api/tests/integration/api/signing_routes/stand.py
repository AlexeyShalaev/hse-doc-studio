"""Стенд маршрутов подписания: настоящее серверное приложение на Postgres и проект КП пака hse-cs-sse на томе.

Отдельный модуль, а не conftest: без extra server (CI «Local mode without server extra») серверные модули этой
папки не собираются, а тест локального режима собирается, и импорт sqlalchemy здесь ему не мешает.

Люди работают персональными токенами (как в `personal/conftest.py`), но с id вида `users.id` (32 hex-символа):
маршрут хранит пользователей именно так. Сборку документа заменяет PDF, записанный на место результата сборки.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from hse_doc_studio.api.config import settings
from hse_doc_studio.infra.db.orm.identity import PasswordCredentialRow, UserRow
from hse_doc_studio.infra.db.orm.projects import ProjectMemberRow
from hse_doc_studio.infra.identity.argon2_hasher import Argon2PasswordHasher
from httpx2 import Response
from reportlab.pdfgen import canvas

from tests.integration.api.personal.conftest import ORIGIN, PASSWORD, Person, Stand

__all__ = ["PNG", "TOPIC_PAIRS", "Person", "Project", "Stand", "make_project", "person"]

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
PACK = {"pack_id": "hse-cs-sse", "template_id": "coursework", "version": "2026.1.3"}
TOPIC = "topic-approval"
TOPIC_DOCS = ("project_proposal", "topic_application")
# Пары «документ, слот» точки: без места на странице слот не подписать (помеха отправки `placement_off`).
TOPIC_PAIRS = (("project_proposal", "supervisor"), ("topic_application", "author"), ("topic_application", "supervisor"))


async def person(stand: Stand, name: str) -> Person:
    """Человек с id как у настоящих аккаунтов и персональным токеном."""
    user_id = uuid4().hex
    email = f"{user_id[:8]}@example.org"
    async with stand.sessions.use() as db:
        db.add(
            UserRow(
                id=user_id,
                email=email,
                email_normalized=email,
                name=name,
                status="active",
                email_verified=True,
                created_at=datetime.now(UTC),
            )
        )
        await db.flush()
        db.add(PasswordCredentialRow(user_id=user_id, password_hash=Argon2PasswordHasher().hash(PASSWORD)))
    login = stand.client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}, headers={"Origin": ORIGIN}
    )
    assert login.status_code == 200, login.text
    created = stand.client.post(
        "/api/v1/account/tokens",
        json={"name": "tests", "scopes": ["api"], "expires_in_days": 30},
        headers={"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]},
    )
    assert created.status_code == 201, created.text
    stand.client.cookies.clear()
    return Person(id=user_id, email=email, headers={"Authorization": f"Bearer {created.json()['token']}"})


@dataclass
class Project:
    stand: Stand
    id: str
    owner: Person

    @property
    def base(self) -> str:
        return f"/api/v1/projects/{self.id}"

    @property
    def routes(self) -> str:
        return f"{self.base}/signing-routes"

    @property
    def folder(self) -> Path:
        return settings.data_dir / "projects" / self.id

    def call(self, who: Person, method: str, path: str, **kwargs: Any) -> Response:
        return self.stand.client.request(method, path, headers=who.headers, **kwargs)

    def build(self, doc_id: str, text: str = "v1") -> None:
        """PDF на месте результата сборки документа: маршрут видит документ собранным."""
        doc = self.call(self.owner, "GET", f"{self.base}/documents/{doc_id}")
        assert doc.status_code == 200, doc.text
        path = self.folder / doc.json()["output_file"]
        path.parent.mkdir(parents=True, exist_ok=True)
        c = canvas.Canvas(str(path))
        c.drawString(100, 700, f"{doc_id} {text}")
        c.save()

    def png(self, who: Person, slot_id: str) -> None:
        resp = self.call(
            who, "POST", f"{self.base}/signatures/slots/{slot_id}/png", files={"file": ("s.png", PNG, "image/png")}
        )
        assert resp.status_code == 200, resp.text

    def place(self, who: Person, *pairs: tuple[str, str]) -> None:
        """Включить место слотов на странице (по умолчанию всех пар точки «Заявка на тему КП»)."""
        for doc_id, slot_id in pairs or TOPIC_PAIRS:
            placed = self.call(
                who, "PATCH", f"{self.base}/signatures/placements/{doc_id}/{slot_id}", json={"enabled": True}
            )
            assert placed.status_code == 200, placed.text

    async def member(self, who: Person, role: str, persona: str | None) -> None:
        async with self.stand.sessions.use() as db:
            db.add(
                ProjectMemberRow(
                    project_id=UUID(self.id), principal_kind="user", principal_id=who.id, role=role, persona=persona
                )
            )
            await db.flush()


def make_project(stand: Stand, owner: Person, **extra: Any) -> Project:
    body = {"name": "КП: маршрут", "lang": "ru", "authors": [{"name": "Иванов Иван Иванович"}], **PACK, **extra}
    created = stand.client.post("/api/v1/projects", json=body, headers=owner.headers)
    assert created.status_code == 201, created.text
    return Project(stand, str(created.json()["id"]), owner)
