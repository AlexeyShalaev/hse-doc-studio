"""Ссылки проекта через API: права (S8), пределы роли, принуждение входа, лимит, перевыпуск, отзыв, аудит."""

from __future__ import annotations

import pytest
from hse_doc_studio.core.orgs.entities import OrgRole

from tests.integration.api.sharing.conftest import ORIGIN, World, add_org, run_sql

pytestmark = pytest.mark.pg


def test__create__owner_gets_link_with_url_and_audit(world: World) -> None:
    link = world.create_link(expires_in_days=60)

    assert link["url"].startswith(f"{ORIGIN}/s/hsl_")
    assert link["state"] == "active"
    assert link["token_prefix"] == link["url"].rsplit("hsl_", 1)[1][:8]
    assert link["created_by"]["name"] == "Анна Петрова"
    assert link["editable"] is True
    assert link["expires_at"] is not None
    listing = world.anna.get(world.links_url).json()
    assert [x["id"] for x in listing["items"]] == [link["id"]]
    assert listing["items"][0]["url"] == link["url"]
    assert listing["can_create"] is True
    assert listing["max_role"] == "editor"


def test__create__reviewer_and_editor_links_always_show_sources(world: World) -> None:
    link = world.create_link(role="reviewer", show_sources=False)

    assert link["show_sources"] is True


def test__create__password_rules(world: World) -> None:
    short = world.anna.post(world.links_url, json={"label": "x", "role": "reader", "password": "1234"})
    assert (short.status_code, short.json()["code"]) == (422, "link_password_invalid")

    link = world.create_link(password="long-enough-pass")
    assert link["has_password"] is True


def test__create__label_must_not_be_blank(world: World) -> None:
    response = world.anna.post(world.links_url, json={"label": "  \n ", "role": "reader"})

    assert response.status_code == 422


def test__permissions__editor_without_share_reader_and_stranger(world: World) -> None:
    assert world.vera.get(world.links_url).status_code == 403
    assert world.gleb.get(world.links_url).status_code == 403
    assert world.dina.get(world.links_url).status_code == 404
    assert world.anonymous().get(world.links_url).status_code == 401


def test__s8__editor_sees_and_edits_only_own_links(world: World) -> None:
    owners = world.create_link(label="Анна")
    own = world.create_link(world.boris, label="Борис")

    listed = world.boris.get(world.links_url).json()["items"]
    assert [x["id"] for x in listed] == [own["id"]]
    assert listed[0]["created_by"] is None
    assert world.boris.patch(f"{world.links_url}/{owners['id']}", json={"label": "чужая"}).status_code == 404
    assert world.boris.delete(f"{world.links_url}/{owners['id']}").status_code == 404
    assert {x["id"] for x in world.anna.get(world.links_url).json()["items"]} == {owners["id"], own["id"]}
    assert world.anna.delete(f"{world.links_url}/{own['id']}").status_code == 204


def test__role_limits__creator_instance_and_org(world: World) -> None:
    run_sql(
        "INSERT INTO instance_settings (key, value, source, updated_at) VALUES "
        "('sharing.max_link_role', '\"reviewer\"', 'admin', now())"
    )
    too_high = world.anna.post(world.links_url, json={"label": "x", "role": "editor"})

    assert (too_high.status_code, too_high.json()["code"]) == (422, "link_role_too_high")
    assert world.anna.get(world.links_url).json()["max_role"] == "reviewer"


def test__links_disabled_by_instance(world: World) -> None:
    run_sql(
        "INSERT INTO instance_settings (key, value, source, updated_at) VALUES "
        "('sharing.links_enabled', 'false', 'admin', now())"
    )

    response = world.anna.post(world.links_url, json={"label": "x", "role": "reader"})

    assert (response.status_code, response.json()["code"]) == (403, "links_disabled")
    assert world.anna.get(world.links_url).json()["can_create"] is False


def test__nda_project__forces_login_and_blocks_existing_public_link(world: World) -> None:
    public = world.create_link()
    run_sql("UPDATE projects SET nda = true WHERE id = CAST(:id AS uuid)", id=world.project_id)

    forced = world.create_link(require_login=False)
    listing = world.anna.get(world.links_url).json()

    assert forced["require_login"] is True
    assert listing["forced_login"] is True
    states = {x["id"]: (x["state"], x["blocked_reason"]) for x in listing["items"]}
    assert states[public["id"]] == ("blocked", "nda")
    assert states[forced["id"]] == ("active", None)


def test__org_policy__off_blocks_links_and_org_only_forces_login(world: World) -> None:
    add_org("org_links", "links", {world.ids["anna"]: OrgRole.owner})
    link = world.create_link()
    run_sql(
        "UPDATE projects SET owner_user_id = NULL, owner_org_id = 'org_links' WHERE id = CAST(:id AS uuid)",
        id=world.project_id,
    )
    run_sql("""UPDATE orgs SET policies = '{"version": 1, "sharing": {"links": "off"}}' WHERE id = 'org_links'""")

    listing = world.anna.get(world.links_url).json()
    assert listing["items"][0]["state"] == "blocked"
    assert listing["items"][0]["blocked_reason"] == "org_links_off"
    assert listing["items"][0]["url"] == link["url"]
    assert world.anna.post(world.links_url, json={"label": "x", "role": "reader"}).json()["code"] == "links_disabled"

    run_sql(
        """UPDATE orgs SET policies = '{"version": 1, "sharing": {"links": "org_only", "max_link_role": "reviewer"}}'
        WHERE id = 'org_links'"""
    )
    forced = world.create_link(role="reviewer")
    assert forced["require_login"] is True
    assert world.anna.get(world.links_url).json()["max_role"] == "reviewer"


def test__limit_of_active_links(world: World) -> None:
    for _ in range(50):
        world.create_link()

    response = world.anna.post(world.links_url, json={"label": "x", "role": "reader"})

    assert (response.status_code, response.json()["code"]) == (409, "link_limit")


def test__update__fields_password_expiry_and_revoked(world: World) -> None:
    link = world.create_link(password="long-enough-pass", expires_in_days=7)
    url = f"{world.links_url}/{link['id']}"

    changed = world.anna.patch(
        url, json={"label": "Новая", "role": "editor", "clear_password": True, "clear_expiry": True}
    )
    assert changed.status_code == 200, changed.text
    body = changed.json()
    assert (body["label"], body["role"], body["has_password"], body["expires_at"]) == ("Новая", "editor", False, None)
    assert body["show_sources"] is True
    assert body["url"] == link["url"]

    assert world.anna.delete(url).status_code == 204
    again = world.anna.patch(url, json={"label": "x"})
    assert (again.status_code, again.json()["code"]) == (409, "link_revoked")


def test__rotate__new_token_old_revoked(world: World) -> None:
    link = world.create_link(password="long-enough-pass")

    rotated = world.anna.post(f"{world.links_url}/{link['id']}/rotate")

    assert rotated.status_code == 200, rotated.text
    new = rotated.json()
    assert new["id"] != link["id"]
    assert new["url"] != link["url"]
    assert new["has_password"] is True
    listing = world.anna.get(world.links_url, params={"include_revoked": True}).json()
    states = {x["id"]: x["state"] for x in listing["items"]}
    assert states == {new["id"]: "active", link["id"]: "revoked"}
    revoked = next(x for x in listing["items"] if x["id"] == link["id"])
    assert revoked["url"] is None
    assert revoked["editable"] is False
    assert listing["revoked_count"] == 1
    again = world.anna.post(f"{world.links_url}/{link['id']}/rotate")
    assert again.json()["code"] == "link_revoked"


def test__revoke__idempotent_and_hidden_by_default(world: World) -> None:
    link = world.create_link()
    url = f"{world.links_url}/{link['id']}"

    assert world.anna.delete(url).status_code == 204
    assert world.anna.delete(url).status_code == 204
    assert world.anna.get(world.links_url).json()["items"] == []
    assert world.anna.delete(f"{world.links_url}/lnk_missing").status_code == 404


def test__visits__empty_page(world: World) -> None:
    link = world.create_link()

    page = world.anna.get(f"{world.links_url}/{link['id']}/visits").json()

    assert page == {"items": [], "total": 0, "limit": 50, "offset": 0}


def test__audit__create_update_rotate_revoke(world: World) -> None:
    link = world.create_link(password="long-enough-pass")
    world.anna.patch(f"{world.links_url}/{link['id']}", json={"password": "another-password"})
    rotated = world.anna.post(f"{world.links_url}/{link['id']}/rotate").json()
    world.anna.delete(f"{world.links_url}/{rotated['id']}")

    admin = world.stand
    from tests.integration.api.sharing.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, Person  # noqa: PLC0415

    events = Person(admin, ADMIN_EMAIL, ADMIN_PASSWORD).get("/api/admin/audit", params={"limit": 50}).json()
    actions = [e["action"] for e in events["items"]]
    assert {"link.create", "link.update", "link.rotate", "link.revoke"} <= set(actions)
    assert "another-password" not in str(events)
