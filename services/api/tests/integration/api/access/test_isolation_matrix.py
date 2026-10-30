"""Матрица изоляции: два пользователя на одном настоящем стенде не видят чужое ни по одному маршруту.

Стенд тот же, что у compose: настоящий `create_app` в server+experimental на Postgres, вход по cookie.
Три чужака владельца проекта (обычный пользователь, админ установки без неявного доступа к содержимому,
аноним) обходят каждую запись `ROUTE_ACTIONS` и получают 404 (аноним 401), а читатель по членству
получает ровно то, что решает `core.access.policy`. Отдельно проверены списки, поиск и данные пользователя
(настройки, провайдеры, подпись, чаты, git). Мутационные тесты ломают правило и убеждаются, что матрица падает.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from hse_doc_studio.api import guards
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.entrypoint import create_app
from hse_doc_studio.api.route_actions import ROUTE_ACTIONS, RouteKey, RouteRule, scope_for_rule
from hse_doc_studio.api.route_scopes import ADMIN_PREFIX, ROUTE_SCOPES, RouteScope
from hse_doc_studio.core.access.actions import RouteExemption
from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.access.entities import Actor, Grant, ProjectAcl, Role
from hse_doc_studio.core.access.policy import Decision, decide
from hse_doc_studio.core.identity.entities import RegistrationMode, User, UserStatus
from hse_doc_studio.core.identity.normalize import normalize_email
from hse_doc_studio.core.identity.protocols import ICredentialRepository, IPasswordHasher, IUserRepository
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.core.orgs.entities import Org, OrgMember, OrgRole
from hse_doc_studio.core.orgs.protocols import IOrgRepository
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.infra.di.containers.api import create_container
from pydantic import SecretStr

pytestmark = pytest.mark.pg

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

ADMIN_EMAIL = "admin@example.org"
ADMIN_PASSWORD = "stand-admin-password"  # noqa: S105 — тестовое значение
ALICE_EMAIL = "alice@example.org"
BOB_EMAIL = "bob@example.org"
USER_PASSWORD = "user-password-1234"  # noqa: S105 — тестовое значение
ORIGIN = "http://localhost:8100"
PROJECT_NAME = "Секретная курсовая Алисы"
_PARAM = re.compile(r"\{(\w+)(?::path)?\}")
_FILLERS = {"path": "notes/a.txt", "slot_id": "main--alice", "doc_id": "thesis", "principal": "user:nobody"}
# Тело, без которого схема отвечает 422 раньше проверки проекта.
_BODY_FILLERS: dict[RouteKey, dict[str, Any]] = {("POST", "/git/remote/probe"): {"url": "https://example.org/r.git"}}
_UNKNOWN_ID = "00000000-0000-4000-8000-000000000001"


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
    # Сотни запросов подряд с одного адреса: лимитер проверяется своими тестами, здесь он только мешает.
    monkeypatch.setattr(settings.rate_limit, "enabled", False)
    with TestClient(create_app(), base_url=ORIGIN) as client:
        yield client


async def _add_user(email: str, name: str) -> str:
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
    finally:
        await container.close()


async def _put_in_one_org(*user_ids: str) -> None:
    """Проект можно открыть только тому, кого владелец вправе видеть: например, по общей организации."""
    container = create_container(StudioMode.server)
    try:
        orgs = await container.get(IOrgRepository)
        uow = await container.get(IUnitOfWork)
        now = datetime.now(UTC)
        async with uow.begin():
            await orgs.add(Org(id="org_matrix", slug="matrix", name="Matrix", created_at=now))
            for user_id in user_ids:
                await orgs.add_member(OrgMember("org_matrix", user_id, OrgRole.member, now))
    finally:
        await container.close()


class _Session:
    """Один TestClient (один цикл событий и пул БД), у каждого человека свои куки."""

    def __init__(self, client: TestClient, email: str | None, password: str | None) -> None:
        self._client = client
        self.headers: dict[str, str] = {"Origin": ORIGIN}
        client.cookies.clear()
        if email is not None and password is not None:
            login = client.post("/api/v1/auth/login", json={"email": email, "password": password}, headers=self.headers)
            assert login.status_code == 200, login.text
            self.headers["X-CSRF-Token"] = login.json()["csrf_token"]
        self._cookies = dict(client.cookies.items())

    def __enter__(self) -> TestClient:
        self._client.cookies.clear()
        for name, value in self._cookies.items():
            self._client.cookies.set(name, value)
        return self._client

    def __exit__(self, *_exc: object) -> None:
        self._client.cookies.clear()


class _World:
    def __init__(self, stand: TestClient) -> None:
        alice_id = asyncio.run(_add_user(ALICE_EMAIL, "Алиса"))
        self.bob_id = asyncio.run(_add_user(BOB_EMAIL, "Боб"))
        self.alice = _Session(stand, ALICE_EMAIL, USER_PASSWORD)
        self.bob = _Session(stand, BOB_EMAIL, USER_PASSWORD)
        self.admin = _Session(stand, ADMIN_EMAIL, ADMIN_PASSWORD)
        self.anonymous = _Session(stand, None, None)
        self.alice_id = alice_id
        with self.alice as client:
            created = client.post(
                "/api/v1/projects",
                json={
                    "name": PROJECT_NAME,
                    "pack_id": "hse-cs-sse",
                    "template_id": "coursework",
                    "version": "2026.1",
                    "lang": "ru",
                    "authors": [{"name": "Алиса"}],
                },
                headers=self.alice.headers,
            )
            assert created.status_code == 201, created.text
            self.project_id = str(created.json()["id"])


@pytest.fixture
def world(stand: TestClient) -> _World:
    return _World(stand)


def _url(template: str, project_id: str) -> str:
    return _PARAM.sub(lambda m: project_id if m[1] == "project_id" else _FILLERS.get(m[1], _UNKNOWN_ID), template)


def _send(client: TestClient, key: RouteKey, rule: RouteRule, project_id: str, headers: dict[str, str]) -> int:
    method, template = key
    url = f"/api/v1{_url(template, project_id)}"
    params: dict[str, str] = {}
    body: dict[str, Any] = {}
    if rule.project_source == "query":
        params["project_id"] = project_id
    elif rule.project_source == "body":
        body["project_id"] = project_id
        body.update(_BODY_FILLERS.get(key, {}))
    # Тело одно на все методы: гард отвечает раньше разбора тела, содержимое важно только для проекта в теле.
    response = client.request(method, url, params=params, json=body, headers=headers)
    return response.status_code


def _checked_rules() -> dict[RouteKey, RouteRule]:
    """Снимок таблицы без системного колбэка: мутационные тесты правят таблицу, а обходят снимок."""
    return {
        k: ROUTE_ACTIONS[k] for k in sorted(ROUTE_ACTIONS) if not isinstance(ROUTE_ACTIONS[k].action, RouteExemption)
    }


def stranger_leaks(world: _World, routes: Mapping[RouteKey, RouteRule]) -> list[str]:
    """Маршруты, где чужак получил не то, что положено: пользователь и админ 404, аноним 401."""
    leaks: list[str] = []
    expected = ((world.bob, 404), (world.admin, 404), (world.anonymous, 401))
    for session, status in expected:
        with session as client:
            for key, rule in routes.items():
                got = _send(client, key, rule, world.project_id, session.headers)
                if got != status:
                    leaks.append(f"{key[0]} {key[1]} -> {got}, ждали {status}")
    return leaks


def reader_deviations(world: _World, routes: Mapping[RouteKey, RouteRule]) -> list[str]:
    """Читатель по членству: запрещённое политикой даёт 403, разрешённое не даёт ни 401, ни 403."""
    reader = Actor.user(world.bob_id)
    acl = ProjectAcl(
        project_id=world.project_id, owner_id=world.alice_id, grants={world.bob_id: Grant(role=Role.reader)}
    )
    deviations: list[str] = []
    with world.bob as client:
        for key, rule in routes.items():
            params = {name: _FILLERS.get(name, _UNKNOWN_ID) for name in _PARAM.findall(key[1])}
            decision = decide(reader, rule.action, acl, scope_for_rule(rule, params))  # type: ignore[arg-type]
            got = _send(client, key, rule, world.project_id, world.bob.headers)
            if decision is Decision.forbidden and got != 403:
                deviations.append(f"{key[0]} {key[1]} -> {got}, ждали 403")
            if decision is Decision.allow and got in {401, 403}:
                deviations.append(f"{key[0]} {key[1]} -> {got}, политика разрешает")
    return deviations


def _share_with_bob_as_reader(world: _World) -> None:
    asyncio.run(_put_in_one_org(world.alice_id, world.bob_id))
    with world.alice as client:
        response = client.put(
            f"/api/v1/projects/{world.project_id}/members/user:{world.bob_id}",
            json={"role": "reader", "persona": None, "can_share": False, "show_sources": False, "can_edit_all": False},
            headers=world.alice.headers,
        )
    assert response.status_code == 200, response.text


def test__route_actions__every_project_route__is_covered_by_the_matrix() -> None:
    assert set(ROUTE_ACTIONS) - set(_checked_rules()) == {("POST", "/office-editor/callback")}


def test__matrix__stranger_admin_and_anonymous__see_no_project_route(world: _World) -> None:
    assert stranger_leaks(world, _checked_rules()) == []


def test__matrix__reader_member__gets_exactly_what_the_policy_decides(world: _World) -> None:
    _share_with_bob_as_reader(world)

    assert reader_deviations(world, _checked_rules()) == []


def test__members__user_outside_the_owners_circle__is_not_found_like_a_missing_one(world: _World) -> None:
    base = f"/api/v1/projects/{world.project_id}/members"
    body = {"role": "reader", "persona": None, "can_share": False, "show_sources": False, "can_edit_all": False}
    with world.alice as client:
        known = client.put(f"{base}/user:{world.bob_id}", json=body, headers=world.alice.headers)
        missing = client.put(f"{base}/user:{uuid.uuid4().hex}", json=body, headers=world.alice.headers)

    assert (known.status_code, known.json()["code"]) == (missing.status_code, missing.json()["code"])
    assert known.status_code == 404
    with world.bob as client:
        assert client.get(f"/api/v1/projects/{world.project_id}").status_code == 404


def test__matrix__stranger_responses__never_name_the_project(world: _World) -> None:
    base = f"/api/v1/projects/{world.project_id}"
    with world.bob as client:
        for path in ("", "/files", "/documents", "/chats", "/git", "/vcs/status"):
            text = client.get(f"{base}{path}").text
            assert PROJECT_NAME not in text
            assert world.project_id not in text.replace(base, "")


def test__matrix__lists_and_search__do_not_reveal_foreign_projects(world: _World) -> None:
    with world.alice as client:
        assert [p["name"] for p in client.get("/api/v1/projects").json()] == [PROJECT_NAME]
    for session in (world.bob, world.admin):
        with session as client:
            assert client.get("/api/v1/projects").json() == []
            for query in ("Секретная", "курсовая", "alice", world.project_id):
                suggestions = client.get("/api/v1/projects/suggestions", params={"q": query})
                assert PROJECT_NAME not in suggestions.text
                assert world.project_id not in suggestions.text
            assert PROJECT_NAME not in client.get("/api/v1/agent/chats").text


def test__matrix__sharing_then_revoking__opens_and_closes_the_project(world: _World) -> None:
    base = f"/api/v1/projects/{world.project_id}"
    _share_with_bob_as_reader(world)
    with world.bob as client:
        assert client.get(base).status_code == 200
        assert [p["name"] for p in client.get("/api/v1/projects").json()] == [PROJECT_NAME]
    with world.alice as client:
        revoked = client.delete(f"{base}/members/user:{world.bob_id}", headers=world.alice.headers)
        assert revoked.status_code in {200, 204}, revoked.text
    with world.bob as client:
        assert client.get(base).status_code == 404
        assert client.get("/api/v1/projects").json() == []


def test__access_panel__reader_sees_the_list_but_only_the_owner_searches_people(world: _World) -> None:
    base = f"/api/v1/projects/{world.project_id}/members"
    _share_with_bob_as_reader(world)
    with world.alice as client:
        owner_list = client.get(base, headers=world.alice.headers)
        found = client.get(f"{base}/candidates", params={"q": "bob"}, headers=world.alice.headers)
    with world.bob as client:
        reader_list = client.get(base, headers=world.bob.headers)
        reader_search = client.get(f"{base}/candidates", headers=world.bob.headers)
    with world.admin as client:
        admin_list = client.get(base, headers=world.admin.headers)
        admin_search = client.get(f"{base}/candidates", headers=world.admin.headers)

    assert owner_list.status_code == reader_list.status_code == 200
    assert [(r["subject_id"], r["role"], r["locked"]) for r in owner_list.json()] == [
        (world.alice_id, "owner", True),
        (world.bob_id, "reader", False),
    ]
    assert owner_list.json() == reader_list.json()
    # Уже добавленный человек повторно не предлагается.
    assert found.status_code == 200
    assert found.json() == []
    assert (reader_search.status_code, reader_search.json()["code"]) == (403, "forbidden_role")
    assert reader_search.json()["required_role"] == "owner"
    assert (admin_list.status_code, admin_search.status_code) == (404, 404)


def test__matrix__admin_area__is_a_404_for_a_regular_user_and_401_for_anonymous(world: _World) -> None:
    admin_routes = sorted(
        k for k, scope in ROUTE_SCOPES.items() if scope is RouteScope.instance_admin and k[1].startswith(ADMIN_PREFIX)
    )
    assert admin_routes
    wrong: list[str] = []
    for session, status in ((world.bob, 404), (world.anonymous, 401)):
        with session as client:
            for method, template in admin_routes:
                url = _PARAM.sub(lambda m: _FILLERS.get(m[1], _UNKNOWN_ID), template)
                got = client.request(method, url, json={}, headers=session.headers).status_code
                if got != status:
                    wrong.append(f"{method} {template} -> {got}, ждали {status}")

    assert wrong == []


def test__user_data__settings_providers_signing_git_chats__are_private_per_user(world: _World) -> None:
    with world.admin as client:
        allowed = client.put(
            "/api/admin/settings/signing", json={"server_keys": "allowed"}, headers=world.admin.headers
        )
        assert allowed.status_code == 200, allowed.text
    with world.alice as client:
        headers = world.alice.headers
        assert client.put("/api/v1/settings", json={"theme": "light"}, headers=headers).status_code == 200
        provider = client.post(
            "/api/v1/ai-providers",
            json={"name": "Ключ Алисы", "type": "openai", "api_key": "sk-alice-canary", "models": ["gpt-4.1"]},
            headers=headers,
        )
        assert provider.status_code in {200, 201}, provider.text
        identity = client.post(
            "/api/v1/signing-identities/self-signed",
            json={"label": "Подпись Алисы", "subject_cn": "Alice Canary"},
            headers=headers,
        )
        assert identity.status_code in {200, 201}, identity.text
        credential = client.post(
            "/api/v1/git/credentials",
            json={"kind": "pat", "label": "Токен Алисы", "host": "github.com", "token": "ghp_ALICEcanary1234567890"},
            headers=headers,
        )
        assert credential.status_code == 201, credential.text
        chat = client.post("/api/v1/agent/chats", json={"title": "Чат Алисы"}, headers=headers)
        assert chat.status_code == 201, chat.text
        project_chat = client.post(
            f"/api/v1/projects/{world.project_id}/chats", json={"title": "Проектный чат Алисы"}, headers=headers
        )
        assert project_chat.status_code == 201, project_chat.text
    owned = {
        "provider": f"/api/v1/ai-providers/{provider.json()['id']}",
        "identity": f"/api/v1/signing-identities/{identity.json()['id']}/public-key",
        "credential": f"/api/v1/git/credentials/{credential.json()['id']}",
        "chat": f"/api/v1/agent/chats/{chat.json()['id']}",
        "project chat": f"/api/v1/projects/{world.project_id}/chats/{project_chat.json()['id']}",
    }
    canaries = (
        "Ключ Алисы",
        "sk-alice-canary",
        "Подпись Алисы",
        "Alice Canary",
        "Токен Алисы",
        "ALICEcanary",
        "Чат Алисы",
        "Проектный чат Алисы",
    )

    for session in (world.bob, world.admin):
        with session as client:
            headers = session.headers
            assert client.get("/api/v1/settings").json()["theme"] != "light"
            for path in (
                "/api/v1/ai-providers",
                "/api/v1/signing-identities",
                "/api/v1/git/credentials",
                "/api/v1/agent/chats",
            ):
                text = client.get(path).text
                assert not [c for c in canaries if c in text], path
            for name, path in owned.items():
                if name not in {"credential", "identity"}:
                    assert client.get(path).status_code == 404, name
            assert client.patch(owned["provider"], json={"name": "Взлом"}, headers=headers).status_code == 404
            assert client.delete(owned["provider"], headers=headers).status_code == 404
            assert client.delete(owned["credential"], headers=headers).status_code == 404
            assert client.post(f"{owned['credential']}/check", headers=headers).status_code == 404
            # Удаление системного чата идемпотентно (204 и для чужого id): важно, что у владельца чат остался.
            assert client.delete(owned["chat"], headers=headers).status_code in {204, 404}
            assert client.delete(owned["identity"].removesuffix("/public-key"), headers=headers).status_code == 404
            assert client.get(f"/api/v1/projects/{world.project_id}/chats").status_code == 404

    with world.alice as client:
        for name, path in owned.items():
            if name not in {"credential", "identity"}:
                assert client.get(path).status_code == 200, name
        assert "Токен Алисы" in client.get("/api/v1/git/credentials").text
        assert "Подпись Алисы" in client.get("/api/v1/signing-identities").text
        assert client.get("/api/v1/settings").json()["theme"] == "light"


def test__mutation__removed_rule__fails_the_matrix(world: _World, monkeypatch: pytest.MonkeyPatch) -> None:
    victim: RouteKey = ("GET", "/projects/{project_id}/files")
    routes = {victim: _checked_rules()[victim]}
    monkeypatch.delitem(ROUTE_ACTIONS, victim)

    assert stranger_leaks(world, routes)


def test__mutation__acl_that_lets_everyone_in__fails_the_matrix(world: _World, monkeypatch: pytest.MonkeyPatch) -> None:
    async def stranger_is_owner(_request: object, project_id: str) -> ProjectAcl:
        actor = require_actor()
        return ProjectAcl(project_id=project_id, owner_id=actor.id, grants={str(actor.id): Grant(role=Role.owner)})

    monkeypatch.setattr(guards, "load_project_acl", stranger_is_owner)

    leaks = stranger_leaks(world, _checked_rules())

    assert len(leaks) > len(_checked_rules()) // 2
