"""Открытие ссылки и гость: превью, пароль, имя, cookie, ссылочное право вошедшего, отзыв посреди работы, CSRF."""

from __future__ import annotations

import pytest
from hse_doc_studio.core.orgs.entities import OrgRole

from tests.integration.api.sharing.conftest import ORIGIN, PROJECT_NAME, Person, World, add_org, run_sql, token_of

pytestmark = pytest.mark.pg


def _open(person: Person, token: str, **body: object) -> object:
    return person.post(f"/api/v1/links/{token}/open", json={"password": None, "guest_name": None, **body})


def _guest_headers(person: Person) -> None:
    """Гость берёт CSRF-токен своей сессии из bootstrap, как это делает интерфейс."""
    boot = person.get("/api/v1/session/bootstrap").json()
    assert boot["guest"] is not None
    person.headers["X-CSRF-Token"] = boot["csrf_token"]


def test__preview__states_and_inactive_is_uniform(world: World) -> None:
    reader = token_of(world.create_link())
    editor = token_of(world.create_link(role="editor", label="Для группы"))
    locked = token_of(world.create_link(password="long-enough-pass"))
    login = token_of(world.create_link(require_login=True))
    guest = world.anonymous()

    ok = guest.get(f"/api/v1/links/{reader}")
    assert ok.headers["Referrer-Policy"] == "no-referrer"
    assert ok.json() == {
        "state": "ok",
        "project_name": PROJECT_NAME,
        "owner_name": "Анна Петрова",
        "role": "reader",
        "show_sources": False,
        "guest_name_required": False,
        "signed_in": False,
    }
    assert guest.get(f"/api/v1/links/{editor}").json()["guest_name_required"] is True
    hidden = guest.get(f"/api/v1/links/{locked}").json()
    assert hidden["state"] == "password_required"
    assert hidden["project_name"] is None
    assert hidden["role"] is None
    assert guest.get(f"/api/v1/links/{login}").json()["state"] == "login_required"
    assert world.vera.get(f"/api/v1/links/{login}").json()["state"] == "ok"
    missing = guest.get("/api/v1/links/hsl_doesNotExistAtAllAnywhere0000000000000").json()
    world.anna.delete(f"{world.links_url}/{world.anna.get(world.links_url).json()['items'][-1]['id']}")
    revoked = guest.get(f"/api/v1/links/{reader}").json()
    assert (
        missing
        == revoked
        == {
            "state": "inactive",
            "project_name": None,
            "owner_name": None,
            "role": None,
            "show_sources": False,
            "guest_name_required": False,
            "signed_in": False,
        }
    )


def test__guest_reader__opens_and_reads_only_output(world: World) -> None:
    token = token_of(world.create_link())
    guest = world.anonymous()

    opened = _open(guest, token)

    assert opened.status_code == 200, opened.text  # type: ignore[attr-defined]
    assert opened.json() == {  # type: ignore[attr-defined]
        "project_id": world.project_id,
        "mode": "guest",
        "role": "reader",
        "show_sources": False,
        "landing": "view",
    }
    assert "hse_guest" in guest.cookies
    project = guest.get(f"/api/v1/projects/{world.project_id}")
    assert project.status_code == 200, project.text
    assert project.json()["my_role"] == "reader"
    assert guest.get(f"/api/v1/projects/{world.project_id}/files/main.tex").status_code == 403
    boot = guest.get("/api/v1/session/bootstrap").json()
    assert boot["user"] is None
    assert boot["guest"]["links"][0]["project_name"] == PROJECT_NAME
    assert boot["csrf_token"]
    assert not any(boot["capabilities"].values())


def test__guest__closed_routes_outside_project(world: World) -> None:
    guest = world.anonymous()
    _open(guest, token_of(world.create_link()))

    assert guest.get("/api/v1/account").status_code == 404
    assert guest.get("/api/v1/projects").status_code == 404
    assert guest.get("/api/v1/account/tokens").status_code == 404
    assert guest.get("/api/admin/users").status_code in {401, 404}
    assert guest.get(f"{world.links_url}").status_code == 403


def test__guest_editor__name_required_and_password_lock(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    token = token_of(world.create_link(role="editor", label="Для группы", password="long-enough-pass"))
    guest = world.anonymous()

    wrong = _open(guest, token, password="wrong-password")
    assert (wrong.status_code, wrong.json()["code"]) == (403, "link_password_wrong")  # type: ignore[attr-defined]
    unnamed = _open(guest, token, password="long-enough-pass")
    assert unnamed.json()["code"] == "guest_name_required"  # type: ignore[attr-defined]
    opened = _open(guest, token, password="long-enough-pass", guest_name="Борис")
    assert opened.status_code == 200  # type: ignore[attr-defined]
    assert opened.json()["landing"] == "workspace"  # type: ignore[attr-defined]

    attacker = world.anonymous()
    codes = [_open(attacker, token, password=f"bad-{i}-pass").json()["code"] for i in range(12)]  # type: ignore[attr-defined]
    assert codes[:10] == ["link_password_wrong"] * 10
    assert "link_password_locked" in codes[10:]


def test__guest_editor__writes_files_with_csrf(world: World) -> None:
    token = token_of(world.create_link(role="editor", label="Для группы"))
    guest = world.anonymous()
    _open(guest, token, guest_name="Борис")

    without = guest.put(f"/api/v1/projects/{world.project_id}/files/notes/guest.txt", content=b"x")
    assert (without.status_code, without.json()["code"]) == (403, "csrf_failed")
    _guest_headers(guest)
    written = guest.put(f"/api/v1/projects/{world.project_id}/files/notes/guest.txt", content=b"hello")
    assert written.status_code in {200, 201, 204}, written.text
    assert guest.post(f"/api/v1/projects/{world.project_id}/vcs/snapshots", json={}).status_code == 403


def test__revoked_mid_session__link_inactive_then_bootstrap_forgets(world: World) -> None:
    link = world.create_link(role="reviewer")
    guest = world.anonymous()
    _open(guest, token_of(link), guest_name="Пётр")
    assert guest.get(f"/api/v1/projects/{world.project_id}").status_code == 200

    world.anna.delete(f"{world.links_url}/{link['id']}")

    gone = guest.get(f"/api/v1/projects/{world.project_id}")
    assert (gone.status_code, gone.json()["code"]) == (404, "link_inactive")
    assert guest.get("/api/v1/session/bootstrap").json()["guest"]["links"] == []
    stranger = world.dina.get(f"/api/v1/projects/{world.project_id}")
    assert stranger.json()["code"] == "not_found"


def test__rotate__old_guest_sessions_lose_access(world: World) -> None:
    link = world.create_link()
    guest = world.anonymous()
    _open(guest, token_of(link))

    world.anna.post(f"{world.links_url}/{link['id']}/rotate")

    assert guest.get(f"/api/v1/projects/{world.project_id}").status_code == 404


def test__second_link_of_same_project_replaces_first_in_session(world: World) -> None:
    reader = world.create_link()
    editor = world.create_link(role="editor", label="Для группы")
    guest = world.anonymous()
    _open(guest, token_of(reader))
    _guest_headers(guest)
    _open(guest, token_of(editor), guest_name="Борис")

    assert guest.get(f"/api/v1/projects/{world.project_id}").json()["my_role"] == "editor"
    links = guest.get("/api/v1/session/bootstrap").json()["guest"]["links"]
    assert [x["link_label"] for x in links] == ["Для группы"]


def test__signed_in__gets_link_grant_and_sees_project_in_list(world: World) -> None:
    token = token_of(world.create_link(role="reviewer", label="Для научрука"))

    opened = _open(world.dina, token)

    assert opened.json()["mode"] == "user"  # type: ignore[attr-defined]
    items = world.dina.get("/api/v1/projects").json()["items"]
    assert [(x["name"], x["my_role"], x["via_link"]) for x in items] == [(PROJECT_NAME, "reviewer", True)]
    detail = world.dina.get(f"/api/v1/projects/{world.project_id}").json()
    assert (detail["via_link"], detail["link_label"]) == (True, "Для научрука")
    assert world.dina.get(f"{world.links_url}").status_code == 403
    assert "hse_guest" not in world.dina.cookies


def test__signed_in__membership_beats_link(world: World) -> None:
    token = token_of(world.create_link(role="editor"))

    _open(world.gleb, token)

    detail = world.gleb.get(f"/api/v1/projects/{world.project_id}").json()
    assert (detail["my_role"], detail["via_link"]) == ("reader", False)


def test__require_login__guest_gets_401(world: World) -> None:
    token = token_of(world.create_link(require_login=True))

    response = _open(world.anonymous(), token)

    assert (response.status_code, response.json()["code"]) == (401, "link_login_required")  # type: ignore[attr-defined]


def test__org_only__outsider_refused_member_admitted(world: World) -> None:
    add_org("org_only", "only", {world.ids["anna"]: OrgRole.owner, world.ids["vera"]: OrgRole.member})
    token = token_of(world.create_link())
    run_sql(
        "UPDATE projects SET owner_user_id = NULL, owner_org_id = 'org_only' WHERE id = CAST(:id AS uuid)",
        id=world.project_id,
    )
    run_sql("""UPDATE orgs SET policies = '{"version": 1, "sharing": {"links": "org_only"}}' WHERE id = 'org_only'""")

    assert world.anonymous().get(f"/api/v1/links/{token}").json()["state"] == "org_only"
    refused = _open(world.dina, token)
    assert (refused.status_code, refused.json()["code"]) == (403, "link_org_only")  # type: ignore[attr-defined]
    assert _open(world.anonymous(), token).status_code == 401  # type: ignore[attr-defined]


def test__policy_tightening_closes_open_guest_session(world: World) -> None:
    token = token_of(world.create_link())
    guest = world.anonymous()
    _open(guest, token)
    run_sql(
        "INSERT INTO instance_settings (key, value, source, updated_at) VALUES "
        "('sharing.links_enabled', 'false', 'admin', now())"
    )

    assert guest.get(f"/api/v1/projects/{world.project_id}").status_code == 404


def test__guest_session__rename_and_leave(world: World) -> None:
    guest = world.anonymous()
    _open(guest, token_of(world.create_link(role="editor", label="Для группы")), guest_name="Борис")
    _guest_headers(guest)

    renamed = guest.patch("/api/v1/links/session", json={"name": "Борис К."})
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "Борис К."
    assert guest.delete("/api/v1/links/session").status_code == 204
    assert guest.get(f"/api/v1/projects/{world.project_id}").status_code == 401
    assert world.anonymous().patch("/api/v1/links/session", json={"name": "x"}).status_code == 401


def test__visits_and_open_audit(world: World) -> None:
    link = world.create_link()
    token = token_of(link)
    guest = world.anonymous()
    _open(guest, token)
    _guest_headers(guest)
    _open(guest, token)
    _open(world.dina, token)

    page = world.anna.get(f"{world.links_url}/{link['id']}/visits").json()
    assert page["total"] == 2
    assert {(x["visitor_kind"], x["opens"]) for x in page["items"]} == {("guest", 2), ("user", 1)}
    listed = world.anna.get(world.links_url).json()["items"][0]["visits"]
    assert (listed["visitors"], listed["opens"]) == (2, 3)


def test__cookie_is_httponly_and_lax(world: World) -> None:
    guest = world.anonymous()
    with guest as client:
        response = client.post(
            f"/api/v1/links/{token_of(world.create_link())}/open",
            json={"password": None, "guest_name": None},
            headers={"Origin": ORIGIN},
        )
    cookie = response.headers["set-cookie"].lower()
    assert "hse_guest=" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie


def test__guest_open_with_existing_session_needs_csrf(world: World) -> None:
    token = token_of(world.create_link())
    guest = world.anonymous()
    _open(guest, token)

    again = _open(guest, token)

    assert (again.status_code, again.json()["code"]) == (403, "csrf_failed")  # type: ignore[attr-defined]


def test__acl__include_links_false_ignores_link_grants_and_guests(world: World) -> None:
    import asyncio  # noqa: PLC0415
    import uuid  # noqa: PLC0415

    from hse_doc_studio.core.access.entities import Actor  # noqa: PLC0415
    from hse_doc_studio.core.mode import StudioMode  # noqa: PLC0415
    from hse_doc_studio.infra.db.repositories.project_acl import PostgresProjectAclRepository  # noqa: PLC0415
    from hse_doc_studio.infra.di.containers.api import create_container  # noqa: PLC0415

    _open(world.dina, token_of(world.create_link(role="editor")))
    dina = Actor.user(world.ids["dina"])

    async def check() -> tuple[object, object, object]:
        container = create_container(StudioMode.server)
        try:
            acl = await container.get(PostgresProjectAclRepository)
            project_id = uuid.UUID(world.project_id)
            return (
                await acl.load_for(dina, project_id),
                await acl.load_for(dina, project_id, include_links=False),
                await acl.load_for(Actor.guest("gs_unknown"), project_id),
            )
        finally:
            await container.close()

    with_links, without_links, unknown_guest = asyncio.run(check())
    assert with_links is not None
    assert without_links is None
    assert unknown_guest is None


def test__access_panel__guest_and_link_user_see_only_owner(world: World) -> None:
    token = token_of(world.create_link(role="reviewer"))
    guest = world.anonymous()
    _open(guest, token, guest_name="Пётр")
    _open(world.dina, token)
    members = f"/api/v1/projects/{world.project_id}/members"

    full = world.anna.get(members).json()
    assert full["total"] >= 4
    for person in (guest, world.dina):
        page = person.get(members).json()
        assert [x["name"] for x in page["items"]] == ["Анна Петрова"]
        assert page["total"] == 1
