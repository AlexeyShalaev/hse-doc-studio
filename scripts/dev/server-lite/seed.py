"""Демо-данные стенда server-lite: три пользователя и по проекту у каждого, чтобы проверить изоляцию глазами.

Запускается внутри образа api (`make server-lite-seed`): пользователи заводятся через
контейнер приложения, проекты создаются настоящими запросами от их имени. Повторный запуск ничего не дублирует.
Организаций в этом срезе нет: таблицы организаций появятся в среде позже.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.identity.entities import User, UserStatus
from hse_doc_studio.core.identity.normalize import normalize_email
from hse_doc_studio.core.identity.protocols import ICredentialRepository, IPasswordHasher, IUserRepository
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.infra.di.containers.api import create_container


@dataclass(frozen=True)
class DemoUser:
    email: str
    name: str
    locale: str
    projects: tuple[str, ...]


DEMO_USERS = (
    DemoUser("anna@example.org", "Анна Иванова", "ru", ("Курсовая: анализ CI/CD", "Отчёт по практике")),
    DemoUser("boris@example.org", "Борис Петров", "ru", ("Курсовая: микросервисы",)),
    DemoUser("victor@example.org", "Victor Smith", "en", ("Coursework: static analysis",)),
)
PACK, TEMPLATE, VERSION = "hse-cs-sse", "coursework", "2026.1"


def _log(line: str) -> None:
    sys.stdout.write(f"{line}\n")


async def ensure_users(password: str) -> None:
    container = create_container(StudioMode.server)
    try:
        users = await container.get(IUserRepository)
        credentials = await container.get(ICredentialRepository)
        hasher = await container.get(IPasswordHasher)
        uow = await container.get(IUnitOfWork)
        for demo in DEMO_USERS:
            if await users.get_by_email(demo.email) is not None:
                _log(f"user exists: {demo.email}")
                continue
            user = User(
                id=uuid.uuid4().hex,
                email=demo.email,
                email_normalized=normalize_email(demo.email),
                name=demo.name,
                status=UserStatus.active,
                created_at=datetime.now(UTC),
                email_verified=True,
                locale=demo.locale,
            )
            async with uow.begin():
                await users.add(user)
                await credentials.set_hash(user.id, hasher.hash(password))
            _log(f"user created: {demo.email}")
    finally:
        await container.close()


def ensure_projects(api_url: str, public_url: str, password: str) -> None:
    for demo in DEMO_USERS:
        # Origin нужен проверке CSRF: запрос идёт «из браузера» с адреса Студии.
        with httpx.Client(base_url=api_url, headers={"Origin": public_url}, timeout=60.0) as client:
            login = client.post("/api/v1/auth/login", json={"email": demo.email, "password": password})
            login.raise_for_status()
            headers = {"X-CSRF-Token": login.json()["csrf_token"]}
            existing = {item["name"] for item in client.get("/api/v1/projects").raise_for_status().json()}
            for name in demo.projects:
                if name in existing:
                    _log(f"project exists: {demo.email} / {name}")
                    continue
                body = {
                    "name": name,
                    "pack_id": PACK,
                    "template_id": TEMPLATE,
                    "version": VERSION,
                    "lang": demo.locale,
                    "authors": [{"name": demo.name}],
                }
                client.post("/api/v1/projects", json=body, headers=headers).raise_for_status()
                _log(f"project created: {demo.email} / {name}")
            client.post("/api/v1/auth/logout", headers=headers)


def main() -> int:
    password = os.environ["SERVER_LITE_SEED_PASSWORD"]
    api_url = os.environ.get("SERVER_LITE_API_URL", "http://localhost:8100")
    public_url = settings.auth.public_url or api_url
    asyncio.run(ensure_users(password))
    ensure_projects(api_url, public_url, password)
    _log("seed done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
