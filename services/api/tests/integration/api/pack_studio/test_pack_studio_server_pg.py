"""Студия шаблонов на сервере: включение раздела админом, право «Автор шаблонов» человеку и группе, область PAT
`packs`, владелец пространства, аудит. Настоящий `create_app` на Postgres."""

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
from hse_doc_studio.core.identity.entities import RegistrationMode
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.core.orgs.entities import Group, OrgRole
from hse_doc_studio.core.orgs.protocols import IGroupRepository
from hse_doc_studio.core.pack_studio.entities import PackWorkspace, WorkspaceKind, WorkspaceState
from hse_doc_studio.core.pack_studio.protocols import IPackWorkspaceRepository
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.infra.di.containers.api import create_container
from pydantic import SecretStr

from tests.integration.api.sharing.conftest import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    ORIGIN,
    USER_PASSWORD,
    Person,
    add_org,
    add_user,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.pg

API = "/api/v1/pack-studio"
ADMIN_API = "/api/admin/pack-studio"


@pytest.fixture
def server(pg_migrated_engine: AsyncEngine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
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
    monkeypatch.setattr(settings.auth, "admin_email", ADMIN_EMAIL)
    monkeypatch.setattr(settings.auth, "admin_password", SecretStr(ADMIN_PASSWORD))
    monkeypatch.setattr(settings.cors, "allow_origins", [ORIGIN])
    monkeypatch.setattr(settings.rate_limit, "enabled", False)
    monkeypatch.setattr(settings, "pack_studio", settings.pack_studio.model_copy())
    with TestClient(create_app(), base_url=ORIGIN) as client:
        yield client


async def _in_container(work: Any) -> Any:
    container = create_container(StudioMode.server)
    try:
        return await work(container)
    finally:
        await container.close()


def _group_with(org_id: str, user_id: str) -> str:
    group_id = uuid.uuid4().hex

    async def work(container: Any) -> None:
        groups = await container.get(IGroupRepository)
        uow = await container.get(IUnitOfWork)
        async with uow.begin():
            await groups.add(Group(id=group_id, org_id=org_id, name="Методисты", created_at=datetime.now(UTC)))
            await groups.add_member(group_id, user_id)

    asyncio.run(_in_container(work))
    return group_id


def _workspace_of(owner_id: str) -> str:
    now = datetime.now(UTC)
    ws = PackWorkspace(
        id=uuid.uuid4(),
        owner_id=owner_id,
        kind=WorkspaceKind.git,
        label="packs",
        packs_path="packs",
        created_at=now,
        updated_at=now,
        state=WorkspaceState.failed,
        remote_url="https://github.com/example/packs.git",
        base_branch="main",
    )

    async def work(container: Any) -> None:
        await (await container.get(IPackWorkspaceRepository)).add(ws)

    asyncio.run(_in_container(work))
    return str(ws.id)


def _admin(server: TestClient) -> Person:
    return Person(server, ADMIN_EMAIL, ADMIN_PASSWORD)


def _author(server: TestClient, key: str = "anna") -> tuple[str, Person]:
    user_id = add_user(f"{key}@example.org", key.capitalize())
    return user_id, Person(server, f"{key}@example.org", USER_PASSWORD)


def _enable(admin: Person) -> None:
    resp = admin.put(ADMIN_API, json={"enabled": True})
    assert resp.status_code == 200, resp.text


def _audit(admin: Person, action: str) -> list[dict[str, Any]]:
    resp = admin.get("/api/admin/audit", params={"action": action})
    assert resp.status_code == 200, resp.text
    return list(resp.json()["items"])


def test__section__off_by_default__even_admin_gets_404(server: TestClient) -> None:
    admin = _admin(server)

    resp = admin.get(f"{API}/workspaces")
    state = admin.get(ADMIN_API).json()

    assert resp.status_code == 404
    assert resp.json()["code"] == "pack_studio_disabled"
    assert state == {"enabled": False, "locked": False, "grants": []}


def test__section__admin_turns_it_on__audited_and_open_for_admin(server: TestClient) -> None:
    admin = _admin(server)

    _enable(admin)

    assert admin.get(f"{API}/workspaces").status_code == 200
    assert admin.get("/api/v1/session/bootstrap").json()["capabilities"]["pack_studio"] is True
    (event,) = _audit(admin, "pack_studio.section_update")
    assert event["details"] == {"enabled": True}


def test__section__local_toggle_route__does_not_exist_on_server(server: TestClient) -> None:
    admin = _admin(server)

    resp = admin.put(f"{API}/section", json={"enabled": True})

    assert resp.status_code == 404


def test__right__person_without_grant__is_403_and_sees_why(server: TestClient) -> None:
    admin = _admin(server)
    _enable(admin)
    _, anna = _author(server)

    resp = anna.get(f"{API}/workspaces")
    section = anna.get(f"{API}/section").json()
    boot = anna.get("/api/v1/session/bootstrap").json()

    assert resp.status_code == 403
    assert resp.json()["code"] == "pack_studio_forbidden"
    assert section["enabled"] is True
    assert section["has_right"] is False
    assert boot["capabilities"]["pack_studio"] is False


def test__right__granted_to_person_then_revoked(server: TestClient) -> None:
    admin = _admin(server)
    _enable(admin)
    anna_id, anna = _author(server)

    granted = admin.post(f"{ADMIN_API}/grants", json={"user_id": anna_id})
    again = admin.post(f"{ADMIN_API}/grants", json={"user_id": anna_id})
    allowed = anna.get(f"{API}/workspaces")
    revoked = admin.delete(f"{ADMIN_API}/grants/{granted.json()['id']}")
    after = anna.get(f"{API}/workspaces")

    assert granted.status_code == 201, granted.text
    assert granted.json()["subject"] == "user"
    assert granted.json()["name"] == "Anna"
    assert granted.json()["email"] == "anna@example.org"
    assert again.status_code == 409
    assert again.json()["code"] == "grant_exists"
    assert allowed.status_code == 200
    assert revoked.status_code == 204
    assert after.status_code == 403
    (add,) = _audit(admin, "pack_studio.grant_add")
    (remove,) = _audit(admin, "pack_studio.grant_remove")
    assert add["target"] == anna_id
    assert remove["target"] == anna_id


def test__right__granted_to_group__opens_section_for_its_member(server: TestClient) -> None:
    admin = _admin(server)
    _enable(admin)
    boris_id, boris = _author(server, "boris")
    org_id = uuid.uuid4().hex
    add_org(org_id, "fcs", {boris_id: OrgRole.member})
    group_id = _group_with(org_id, boris_id)

    granted = admin.post(f"{ADMIN_API}/grants", json={"group_id": group_id})
    listed = admin.get(ADMIN_API).json()["grants"]

    assert granted.status_code == 201, granted.text
    assert boris.get(f"{API}/workspaces").status_code == 200
    assert [(g["subject"], g["name"], g["org_slug"]) for g in listed] == [("group", "Методисты", "fcs")]


def test__right__unknown_subject__is_404(server: TestClient) -> None:
    admin = _admin(server)

    resp = admin.post(f"{ADMIN_API}/grants", json={"user_id": "nobody"})

    assert resp.status_code == 404
    assert resp.json()["code"] == "grant_subject_not_found"


def test__admin_routes__are_hidden_from_a_person(server: TestClient) -> None:
    _, anna = _author(server)

    assert anna.get(ADMIN_API).status_code == 404
    assert anna.post(f"{ADMIN_API}/grants", json={"user_id": "x"}).status_code == 404


def test__folder_workspace__is_refused_on_server(server: TestClient) -> None:
    admin = _admin(server)
    _enable(admin)

    resp = admin.post(f"{API}/workspaces", json={"kind": "folder", "folder": "/etc"})

    assert resp.status_code == 403
    assert resp.json()["code"] == "folder_not_allowed"


def test__workspace__belongs_to_its_owner_only(server: TestClient) -> None:
    admin = _admin(server)
    _enable(admin)
    anna_id, anna = _author(server)
    boris_id, boris = _author(server, "boris")
    for user_id in (anna_id, boris_id):
        assert admin.post(f"{ADMIN_API}/grants", json={"user_id": user_id}).status_code == 201
    ws_id = _workspace_of(anna_id)

    own = anna.get(f"{API}/workspaces/{ws_id}")
    foreign = boris.get(f"{API}/workspaces/{ws_id}")
    foreign_delete = boris.delete(f"{API}/workspaces/{ws_id}")

    assert own.status_code == 200
    assert own.json()["label"] == "packs"
    assert [w["id"] for w in anna.get(f"{API}/workspaces").json()] == [ws_id]
    assert boris.get(f"{API}/workspaces").json() == []
    assert foreign.status_code == 404
    assert foreign.json()["code"] == "workspace_not_found"
    assert foreign_delete.status_code == 404


def test__workspace__owner_deletes_it__audited(server: TestClient) -> None:
    admin = _admin(server)
    _enable(admin)
    anna_id, anna = _author(server)
    admin.post(f"{ADMIN_API}/grants", json={"user_id": anna_id})
    ws_id = _workspace_of(anna_id)

    resp = anna.delete(f"{API}/workspaces/{ws_id}")

    assert resp.status_code == 204
    assert anna.get(f"{API}/workspaces").json() == []
    (event,) = _audit(admin, "pack_studio.workspace_delete")
    assert event["actor_id"] == anna_id
    assert event["target"] == ws_id


@pytest.mark.parametrize(
    ("scopes", "status", "code"), [(["api"], 403, "pack_scope_required"), (["api", "packs"], 200, None)]
)
def test__pat__needs_packs_scope(server: TestClient, scopes: list[str], status: int, code: str | None) -> None:
    admin = _admin(server)
    _enable(admin)
    anna_id, anna = _author(server)
    admin.post(f"{ADMIN_API}/grants", json={"user_id": anna_id})
    created = anna.post("/api/v1/account/tokens", json={"name": "CLI", "scopes": scopes, "expires_in_days": 30})
    assert created.status_code == 201, created.text
    server.cookies.clear()

    resp = server.get(f"{API}/workspaces", headers={"Authorization": f"Bearer {created.json()['token']}"})

    assert resp.status_code == status, resp.text
    if code is not None:
        assert resp.json()["code"] == code


def test__section__forced_by_environment__is_locked_for_admin(server: TestClient) -> None:
    settings.pack_studio.enabled = True
    admin = _admin(server)

    state = admin.get(ADMIN_API).json()
    resp = admin.put(ADMIN_API, json={"enabled": False})

    assert state["enabled"] is True
    assert state["locked"] is True
    assert resp.status_code == 409
    assert resp.json()["code"] == "section_locked"
