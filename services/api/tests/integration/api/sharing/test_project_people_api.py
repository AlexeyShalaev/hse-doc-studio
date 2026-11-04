"""Люди в проекте: сигнал вкладки и список онлайн по настоящему HTTP (docs/design/connected-devices.md, раздел 15)."""

from __future__ import annotations

from typing import Any

import pytest

from tests.integration.api.sharing.conftest import Person, World, token_of

pytestmark = pytest.mark.pg


def signal(session: str, activity: str = "viewing", doc: str | None = None) -> dict[str, Any]:
    return {"session_id": session, "activity": activity, "doc_id": doc}


def ping(world: World, who: Person, session: str, activity: str = "viewing", doc: str | None = None) -> Any:
    return who.post(f"/api/v1/projects/{world.project_id}/presence", json=signal(session, activity, doc))


def names(body: dict[str, Any]) -> list[str]:
    return [p["name"] for p in body["people"]]


def test__presence__members_see_each_other_with_role_place_and_own_icon_marked(world: World) -> None:
    ping(world, world.boris, "tab-boris-1", "editing", "zayavka")

    reply = ping(world, world.anna, "tab-anna-01", "reviewing", "zayavka")

    assert reply.status_code == 200, reply.text
    body = reply.json()
    assert (body["interval_s"], body["online_window_s"], body["total"]) == (60, 180, 2)
    anna, boris = body["people"]
    assert (anna["name"], anna["me"], anna["role"], anna["activity"], anna["doc_id"]) == (
        "Анна Петрова",
        True,
        "owner",
        "reviewing",
        "zayavka",
    )
    assert (boris["name"], boris["me"], boris["role"], boris["activity"], boris["channels"]) == (
        "Борис",
        False,
        "editor",
        "editing",
        ["web"],
    )
    assert anna["initials"] == "АП"
    assert anna["color"].startswith("#")


def test__presence__the_colour_matches_the_cursor_colour_from_the_collab_room(world: World) -> None:
    from hse_doc_studio.infra.collab.manager import CollabIdentity  # noqa: PLC0415

    body = ping(world, world.anna, "tab-anna-01").json()

    cursor = CollabIdentity(key=world.ids["anna"], name="Анна Петрова", can_write=True).color
    assert body["people"][0]["color"] == cursor


def test__presence__two_tabs_of_one_person_are_one_icon(world: World) -> None:
    ping(world, world.anna, "tab-anna-01", "viewing", "a")
    ping(world, world.anna, "tab-anna-02", "editing", "b")

    body = ping(world, world.boris, "tab-boris-1").json()

    assert names(body) == ["Борис", "Анна Петрова"]
    assert body["total"] == 2


def test__presence__leaving_the_tab_removes_it_at_once_and_another_person_cannot_do_it(world: World) -> None:
    ping(world, world.boris, "tab-boris-1")
    url = f"/api/v1/projects/{world.project_id}/presence/tab-boris-1"

    assert world.vera.delete(url).status_code == 204
    assert names(ping(world, world.anna, "tab-anna-01").json()) == ["Анна Петрова", "Борис"]
    assert world.boris.delete(url).status_code == 204
    assert names(ping(world, world.anna, "tab-anna-01").json()) == ["Анна Петрова"]


def test__presence__reader_and_reviewer_cannot_claim_to_edit(world: World) -> None:
    ping(world, world.gleb, "tab-gleb-01", "editing", "zayavka")

    body = ping(world, world.anna, "tab-anna-01").json()

    gleb = next(p for p in body["people"] if p["name"] == "Глеб")
    assert (gleb["role"], gleb["activity"]) == ("reader", "viewing")


def test__presence__reader_without_sources_still_sees_the_documents_people_work_on(world: World) -> None:
    ping(world, world.boris, "tab-boris-1", "editing", "zayavka")

    body = ping(world, world.gleb, "tab-gleb-01").json()

    assert names(body) == ["Глеб", "Борис"]


def test__presence__stranger_gets_no_list_and_is_not_recorded(world: World) -> None:
    reply = ping(world, world.dina, "tab-dina-01")

    assert reply.status_code in {403, 404}
    assert names(ping(world, world.anna, "tab-anna-01").json()) == ["Анна Петрова"]


def test__presence__guest_by_link_and_signed_in_person_by_link_see_nobody_and_are_not_shown(world: World) -> None:
    link = token_of(world.create_link(role="editor"))
    guest = world.anonymous()
    opened = guest.post(f"/api/v1/links/{link}/open", json={"password": None, "guest_name": "Гость Игорь"})
    assert opened.status_code == 200, opened.text
    guest.headers["X-CSRF-Token"] = guest.get("/api/v1/session/bootstrap").json()["csrf_token"]
    assert world.dina.post(f"/api/v1/links/{link}/open", json={"password": None, "guest_name": None}).status_code == 200

    as_guest = ping(world, guest, "tab-guest-01", "editing", "zayavka")
    as_dina = ping(world, world.dina, "tab-dina-01", "editing", "zayavka")
    owner_view = ping(world, world.anna, "tab-anna-01").json()

    assert (as_guest.status_code, as_guest.json()["people"]) == (200, [])
    assert (as_dina.status_code, as_dina.json()["people"]) == (200, [])
    assert names(owner_view) == ["Анна Петрова"]


@pytest.mark.parametrize(
    "body",
    [
        {"session_id": "short", "activity": "viewing"},
        {"session_id": "tab-anna-01", "activity": "local"},
        {"session_id": "tab-anna-01", "activity": "viewing", "doc_id": "../etc/passwd"},
        {"session_id": "tab-anna-01", "activity": "viewing", "path": "/Users/anna"},
        {"session_id": "tab-anna-01", "activity": "viewing", "doc_id": "x" * 200},
    ],
)
def test__presence__invalid_signals_are_refused(world: World, body: dict[str, Any]) -> None:
    reply = world.anna.post(f"/api/v1/projects/{world.project_id}/presence", json=body)

    assert reply.status_code == 422


def test__presence__signals_do_not_write_the_database_or_the_audit_log(world: World) -> None:
    from sqlalchemy import text  # noqa: PLC0415

    def count(table: str) -> int:
        out: list[int] = []

        async def work(container: Any) -> None:
            from hse_doc_studio.infra.db.session import SessionProvider  # noqa: PLC0415

            async with (await container.get(SessionProvider)).use() as db:
                out.append((await db.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one())  # noqa: S608

        import asyncio  # noqa: PLC0415

        from tests.integration.api.sharing.conftest import _in_container  # noqa: PLC0415

        asyncio.run(_in_container(work))
        return out[0]

    before = (count("audit_log"), count("connected_devices"))
    for n in range(10):
        ping(world, world.anna, "tab-anna-01", "editing", f"doc{n}")
        ping(world, world.boris, "tab-boris-1")

    assert (count("audit_log"), count("connected_devices")) == before


def test__overview__people_come_only_when_the_studio_asks_for_them(world: World) -> None:
    anna_token = _token(world, world.anna)
    ping(world, world.boris, "tab-boris-1", "editing", "zayavka")
    headers = {"Authorization": f"Bearer {anna_token}"}
    params = {"device_id": "a" * 32, "project_id": world.project_id}

    old = world.anonymous().request("GET", "/git/-/presence/overview", headers=headers, params=params).json()
    new = (
        world.anonymous()
        .request("GET", "/git/-/presence/overview", headers=headers, params={**params, "people": "true"})
        .json()
    )

    assert "people" not in old
    assert [(p["name"], p["activity"], p["doc_id"]) for p in new["people"]["people"]] == [
        ("Борис", "editing", "zayavka")
    ]


def _token(world: World, who: Person) -> str:
    created = who.post("/api/v1/account/tokens", json={"name": "git", "scopes": ["git:read"], "expires_in_days": 30})
    assert created.status_code == 201, created.text
    return str(created.json()["token"])
