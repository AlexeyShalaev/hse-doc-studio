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


def test__right__person_without_grant__outcome_endpoints_are_refused_and_capability_is_off(server: TestClient) -> None:
    """Результат версии (срез O2) под тем же правом «Автор шаблонов», что весь раздел."""
    admin = _admin(server)
    _enable(admin)
    anna_id, anna = _author(server)
    outcome = f"{API}/workspaces/{uuid.uuid4()}/versions/hse-cs-se/vkr/2026.1.2/outcome"

    inputs = anna.get(f"{outcome}/inputs")
    result = anna.post(outcome, json={})
    before = anna.get("/api/v1/session/bootstrap").json()["capabilities"]
    admin.post(f"{ADMIN_API}/grants", json={"user_id": anna_id})
    allowed = anna.post(outcome, json={})
    after = anna.get("/api/v1/session/bootstrap").json()["capabilities"]

    for resp in (inputs, result):
        assert resp.status_code == 403
        assert resp.json()["code"] == "pack_studio_forbidden"
    assert (before["pack_studio"], before["pack_outcome"]) == (False, False)
    # С правом доходит до пространства: чужого или несуществующего у человека нет.
    assert allowed.status_code == 404
    assert allowed.json()["code"] == "workspace_not_found"
    assert (after["pack_studio"], after["pack_outcome"]) == (True, True)


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


# ── срез T6: служебный доступ репозитория ───────────────────────────────────

_SERVICE_TOKEN = "glpat-service0123456789abcd"


def _service_secret(access_id: str) -> tuple[str | None, str]:
    from hse_doc_studio.core.pack_studio.protocols import IServiceAccessRepository  # noqa: PLC0415
    from hse_doc_studio.infra.db.session import SessionProvider  # noqa: PLC0415
    from sqlalchemy import text  # noqa: PLC0415

    async def work(container: Any) -> tuple[str | None, str]:
        secret = await (await container.get(IServiceAccessRepository)).secret(uuid.UUID(access_id))
        sessions = await container.get(SessionProvider)
        async with sessions.use() as db:
            stored = (
                await db.execute(
                    text("SELECT secret_enc FROM pack_studio_service_access WHERE id = :i"), {"i": access_id}
                )
            ).scalar_one()
        return (None if secret is None else secret.reveal()), str(stored)

    return asyncio.run(_in_container(work))  # type: ignore[no-any-return]


def test__service_access__admin_adds_lists_and_removes__secret_sealed_and_audited(server: TestClient) -> None:
    admin = _admin(server)

    created = admin.post(
        f"{ADMIN_API}/service-access",
        json={"url": "https://gitlab.example.org/fcs/packs.git", "token": _SERVICE_TOKEN, "label": "Паки ФКН"},
    )
    duplicate = admin.post(
        f"{ADMIN_API}/service-access",
        json={"url": "https://GitLab.example.org/FCS/packs", "token": _SERVICE_TOKEN},
    )
    listed = admin.get(f"{ADMIN_API}/service-access").json()
    revealed, stored = _service_secret(created.json()["id"])
    removed = admin.delete(f"{ADMIN_API}/service-access/{created.json()['id']}")
    missing = admin.delete(f"{ADMIN_API}/service-access/{created.json()['id']}")

    assert created.status_code == 201, created.text
    body = created.json()
    assert (body["url"], body["label"], body["token_family"]) == (
        "https://gitlab.example.org/fcs/packs.git",
        "Паки ФКН",
        "glpat",
    )
    assert _SERVICE_TOKEN not in created.text
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "service_access_exists"
    assert [a["id"] for a in listed] == [body["id"]]
    assert revealed == _SERVICE_TOKEN
    assert _SERVICE_TOKEN not in stored
    assert removed.status_code == 204
    assert missing.status_code == 404
    assert missing.json()["code"] == "service_access_not_found"
    (added,) = _audit(admin, "pack_studio.service_access_add")
    assert _SERVICE_TOKEN not in str(added)
    assert len(_audit(admin, "pack_studio.service_access_remove")) == 1


def test__service_access__routes_are_admin_only(server: TestClient) -> None:
    _, anna = _author(server)

    assert anna.get(f"{ADMIN_API}/service-access").status_code == 404
    resp = anna.post(f"{ADMIN_API}/service-access", json={"url": "https://github.com/a/b", "token": "x"})
    assert resp.status_code == 404


def test__service_access__workspace_without_one__is_refused(server: TestClient) -> None:
    admin = _admin(server)
    _enable(admin)

    resp = admin.post(
        f"{API}/workspaces",
        json={"kind": "git", "url": "https://gitlab.example.org/fcs/packs.git", "service_access": True},
    )
    both = admin.post(
        f"{API}/workspaces",
        json={
            "kind": "git",
            "url": "https://gitlab.example.org/fcs/packs.git",
            "service_access": True,
            "credential_id": str(uuid.uuid4()),
        },
    )

    assert resp.status_code == 404, resp.text
    assert resp.json()["code"] == "service_access_missing"
    assert both.status_code == 422


def test__git_routes__workspace_not_ready__answer_workspace_not_ready(server: TestClient) -> None:
    admin = _admin(server)
    _enable(admin)
    anna_id, anna = _author(server)
    admin.post(f"{ADMIN_API}/grants", json={"user_id": anna_id})
    ws_id = _workspace_of(anna_id)

    resp = anna.get(f"{API}/workspaces/{ws_id}/git")
    propose = anna.post(f"{API}/workspaces/{ws_id}/git/propose", json={})

    assert resp.status_code == 409
    assert resp.json()["code"] == "workspace_not_ready"
    assert propose.json()["code"] == "workspace_not_ready"


# ── срез T22: официальные паки (вклад только своим аккаунтом) ───────────────

_OFFICIAL = "https://github.com/AlexeyShalaev/hse-doc-studio"
_GITHUB_TOKEN = "ghp_svc0123456789abcdefABCDEF012345678"


def _official_workspace_of(owner_id: str) -> str:
    now = datetime.now(UTC)
    ws = PackWorkspace(
        id=uuid.uuid4(),
        owner_id=owner_id,
        kind=WorkspaceKind.git,
        label="Официальные паки",
        packs_path="packs",
        created_at=now,
        updated_at=now,
        state=WorkspaceState.failed,
        remote_url=f"{_OFFICIAL}.git",
        base_branch="master",
    )

    async def work(container: Any) -> None:
        await (await container.get(IPackWorkspaceRepository)).add(ws)

    asyncio.run(_in_container(work))
    return str(ws.id)


def _granted_author(server: TestClient, admin: Person) -> tuple[str, Person]:
    anna_id, anna = _author(server)
    assert admin.post(f"{ADMIN_API}/grants", json={"user_id": anna_id}).status_code == 201
    return anna_id, anna


def test__official__info__repository_without_bot_and_no_workspace(server: TestClient) -> None:
    admin = _admin(server)
    _enable(admin)
    _, anna = _granted_author(server, admin)

    info = anna.get(f"{API}/official")

    assert info.status_code == 200, info.text
    assert info.json()["repo"]["url"] == _OFFICIAL
    assert info.json()["repo"]["license"] == "Apache-2.0"
    assert info.json()["workspace_id"] is None
    assert "bot" not in info.json()


def test__official__admin_view__repository_only_and_admin_only(server: TestClient) -> None:
    admin = _admin(server)
    _, anna = _author(server)

    state = admin.get(f"{ADMIN_API}/official")
    put = admin.put(f"{ADMIN_API}/official", json={"bot_enabled": True, "daily_limit": 3})

    assert state.status_code == 200, state.text
    assert state.json() == {"repo": state.json()["repo"]}
    assert state.json()["repo"]["url"] == _OFFICIAL
    assert put.status_code == 405
    assert anna.get(f"{ADMIN_API}/official").status_code == 404
    assert anna.post(f"{ADMIN_API}/service-access/{uuid.uuid4()}/check").status_code == 404


def test__service_access__no_fork_mode__plain_t6_access(server: TestClient) -> None:
    admin = _admin(server)

    bot = admin.post(
        f"{ADMIN_API}/service-access",
        json={"url": _OFFICIAL, "token": _GITHUB_TOKEN, "label": "Бот", "fork_mode": True},
    )
    plain = admin.post(f"{ADMIN_API}/service-access", json={"url": _OFFICIAL, "token": _GITHUB_TOKEN})

    assert bot.status_code == 422
    assert plain.status_code == 201, plain.text
    assert "fork_mode" not in plain.json()
    assert "fork_url" not in plain.json()
    assert _GITHUB_TOKEN not in plain.text


def test__official__existing_workspace__marked_and_opened_again(server: TestClient) -> None:
    admin = _admin(server)
    _enable(admin)
    anna_id, anna = _granted_author(server, admin)
    ws_id = _official_workspace_of(anna_id)

    info = anna.get(f"{API}/official").json()
    card = anna.get(f"{API}/workspaces/{ws_id}").json()
    opened = anna.post(f"{API}/official/workspace", json={"credential_id": str(uuid.uuid4())})

    assert info["workspace_id"] == ws_id
    assert card["official"] is True
    assert card["license_accepted_at"] is None
    assert opened.status_code == 200, opened.text
    assert opened.json()["id"] == ws_id


def test__official__open_without_own_token__refused(server: TestClient) -> None:
    admin = _admin(server)
    _enable(admin)
    _, anna = _granted_author(server, admin)

    bot = anna.post(f"{API}/official/workspace", json={"access": "bot"})
    empty = anna.post(f"{API}/official/workspace", json={})

    assert bot.status_code == 422
    assert empty.status_code == 422


def test__official__no_repository_configured__hidden_and_refused(server: TestClient) -> None:
    settings.pack_studio.official_repo_url = ""
    admin = _admin(server)
    _enable(admin)

    info = admin.get(f"{API}/official").json()
    admin_view = admin.get(f"{ADMIN_API}/official").json()
    resp = admin.post(f"{API}/official/workspace", json={"credential_id": str(uuid.uuid4())})

    assert info["repo"] is None
    assert admin_view["repo"] is None
    assert resp.status_code == 404
    assert resp.json()["code"] == "official_unavailable"
