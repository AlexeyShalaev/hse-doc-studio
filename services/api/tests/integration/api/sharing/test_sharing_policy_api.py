"""Политика общего доступа: организация (участник смотрит, админ правит) и установка (раздел «Общий доступ»)."""

from __future__ import annotations

import pytest
from hse_doc_studio.api.config import settings
from hse_doc_studio.core.orgs.entities import OrgRole

from tests.integration.api.sharing.conftest import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    Person,
    World,
    add_org,
    run_sql,
    token_of,
)

pytestmark = pytest.mark.pg

STRICT = {"links": "org_only", "max_link_role": "reviewer", "nda_public_links": False, "external_invites": False}


def _org_world(world: World) -> str:
    add_org(
        "org_pol",
        "pol",
        {world.ids["anna"]: OrgRole.owner, world.ids["boris"]: OrgRole.admin, world.ids["vera"]: OrgRole.member},
    )
    run_sql(
        "UPDATE projects SET owner_user_id = NULL, owner_org_id = 'org_pol' WHERE id = CAST(:id AS uuid)",
        id=world.project_id,
    )
    return "/api/v1/orgs/pol/sharing-policy"


def test__org_policy__defaults_roles_and_strangers(world: World) -> None:
    url = _org_world(world)

    member = world.vera.get(url)
    assert member.status_code == 200, member.text
    assert member.json() == {
        "links": "any",
        "max_link_role": "editor",
        "nda_public_links": False,
        "external_invites": True,
        "editable": False,
    }
    assert world.vera.put(url, json=STRICT).status_code == 403
    assert world.dina.get(url).status_code == 404
    saved = world.boris.put(url, json=STRICT)
    assert saved.status_code == 200, saved.text
    assert saved.json() == {**STRICT, "editable": True}
    assert world.anna.get(url).json() == {**STRICT, "editable": True}


def test__org_policy__tightening_blocks_existing_links_without_revoking(world: World) -> None:
    url = _org_world(world)
    link = world.create_link(role="editor")
    guest = world.anonymous()
    guest.post(f"/api/v1/links/{token_of(link)}/open", json={"password": None, "guest_name": "Борис"})
    assert guest.get(f"/api/v1/projects/{world.project_id}").status_code == 200

    world.anna.put(url, json={**STRICT, "links": "off"})

    item = world.anna.get(world.links_url).json()["items"][0]
    assert (item["state"], item["blocked_reason"]) == ("blocked", "org_links_off")
    assert guest.get(f"/api/v1/projects/{world.project_id}").status_code == 404
    world.anna.put(url, json={**STRICT, "links": "any", "max_link_role": "reviewer"})
    item = world.anna.get(world.links_url).json()["items"][0]
    assert (item["state"], item["blocked_reason"]) == ("blocked", "org_role_cap")


def test__org_policy__keeps_other_policy_keys(world: World) -> None:
    url = _org_world(world)
    run_sql("""UPDATE orgs SET policies = '{"version": 1, "other": {"x": 1}}' WHERE id = 'org_pol'""")

    world.anna.put(url, json=STRICT)

    run_sql(
        """DO $$ BEGIN IF (SELECT policies->'other'->>'x' FROM orgs WHERE id = 'org_pol') IS DISTINCT FROM '1'
        THEN RAISE EXCEPTION 'lost key'; END IF; END $$"""
    )


def _admin(world: World) -> Person:
    return Person(world.stand, ADMIN_EMAIL, ADMIN_PASSWORD)


def test__admin_sharing__read_write_and_effect(world: World) -> None:
    admin = _admin(world)

    current = admin.get("/api/admin/settings/sharing")
    assert current.status_code == 200, current.text
    assert current.json()["links_enabled"] is True
    assert current.json()["fields"]["sharing.links_enabled"] == {"source": "default", "locked": False}
    saved = admin.put(
        "/api/admin/settings/sharing",
        json={"links_enabled": False, "max_link_role": "reviewer", "project_invites_allow_signup": False},
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert (body["links_enabled"], body["max_link_role"], body["project_invites_allow_signup"]) == (
        False,
        "reviewer",
        False,
    )
    assert body["fields"]["sharing.max_link_role"]["source"] == "admin"
    refused = world.anna.post(world.links_url, json={"label": "x", "role": "reader"})
    assert refused.json()["code"] == "links_disabled"
    assert world.anna.get("/api/admin/settings/sharing").status_code == 404


@pytest.fixture
def links_locked_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """До создания стенда: значения окружения читаются при сборке контейнера."""
    monkeypatch.setattr(settings.sharing, "links_enabled", True)


@pytest.mark.usefixtures("links_locked_by_env")
def test__admin_sharing__env_lock(world: World) -> None:
    admin = _admin(world)

    fields = admin.get("/api/admin/settings/sharing").json()["fields"]
    refused = admin.put("/api/admin/settings/sharing", json={"links_enabled": False})

    assert fields["sharing.links_enabled"] == {"source": "env", "locked": True}
    assert (refused.status_code, refused.json()["code"]) == (409, "setting_locked")
