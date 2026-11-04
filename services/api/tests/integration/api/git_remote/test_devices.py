"""Подключённые Студии на живом сервере: присутствие по токену, права видимости, статус и выдача облачных сборок.

Сценарии идут по настоящему HTTP: сигнал присутствия шлёт настоящий клиент локальной Студии
(`HttpStudioServerClient`), люди и проекты создаются так же, как у остальных тестов git по HTTPS.
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.git_remote.client import StudioServerError, StudioServerErrorCode, StudioServerTarget
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.infra.git_remote_client.studio_client import HttpStudioServerClient
from hse_doc_studio.infra.jobs.s3_artifact_store import archived_pdf_key

from tests.integration.api.git_remote.conftest import Live, Person

pytestmark = [pytest.mark.pg, pytest.mark.timeout(240)]

PDF = b"%PDF-1.7\ncloud build\n%%EOF\n"
SHA = hashlib.sha256(PDF).hexdigest()
COMMIT = "a" * 40
DEVICE_A = "a" * 32
DEVICE_B = "b" * 32


def signal(device_id: str, project: str, **changes: object) -> dict[str, object]:
    body: dict[str, object] = {
        "device_id": device_id,
        "name": "MacBook Анны",
        "version": "0.6.0",
        "os": "macos",
        "activity": "idle",
        "runner": None,
        "endpoints": [],
        "projects": [{"project_id": project, "sync": "ahead", "ahead": 2, "behind": 1, "auto_sync": True}],
    }
    return {**body, **changes}


def send(live: Live, token: str, body: dict[str, object]) -> object:
    client = HttpStudioServerClient()
    return asyncio.run(client.send_presence(StudioServerTarget(live.base), Secret(token), body))


def raw_send(live: Live, token: str, body: dict[str, object], **kwargs: object) -> int:
    return live.call(
        "POST", "/git/-/presence", headers={"Authorization": f"Bearer {token}"}, json=body, **kwargs
    ).status_code


def project_studios(live: Live, who: Person, project: str) -> dict[str, object]:
    response = live.call("GET", f"/api/v1/projects/{project}/studios", who)
    assert response.status_code == 200, response.text
    return dict(response.json())


# --- сигнал присутствия ---


def test__presence__signal_is_accepted_and_the_device_is_listed_online_for_its_owner(live: Live) -> None:
    anna = live.person("anna")
    project = live.create_project(anna)
    token = live.token(anna, ["git:read", "git:write"])

    reply = send(live, token, signal(DEVICE_A, project, activity="syncing"))

    assert (reply.interval_s, reply.online_window_s) == (60, 180)  # type: ignore[attr-defined]
    devices = live.call("GET", "/api/v1/account/devices", anna).json()
    (device,) = devices["items"]
    assert (device["id"], device["name"], device["presence"], device["activity"]) == (
        DEVICE_A,
        "MacBook Анны",
        "online",
        "syncing",
    )
    assert device["projects_count"] == 1
    assert device["ai"]["state"] == "runner_unpaired"


def test__presence__read_only_git_token_is_enough_but_api_only_token_is_not(live: Live) -> None:
    anna = live.person("anna")
    project = live.create_project(anna)
    read_token = live.token(anna, ["git:read"], name="чтение")
    api_token = live.token(anna, ["api"], name="api")

    assert raw_send(live, read_token, signal(DEVICE_A, project)) == 200
    assert raw_send(live, api_token, signal(DEVICE_A, project)) in {401, 403}
    assert raw_send(live, "hsat_not-a-token", signal(DEVICE_A, project)) == 401


def test__presence__cookie_session_cannot_send_a_signal(live: Live) -> None:
    anna = live.person("anna")
    project = live.create_project(anna)

    with live.client() as client:
        response = client.post("/git/-/presence", json=signal(DEVICE_A, project), cookies=anna.cookies)

    assert response.status_code in {401, 403}


def test__presence__invalid_and_oversized_bodies_are_refused(live: Live) -> None:
    anna = live.person("anna")
    project = live.create_project(anna)
    token = live.token(anna, ["git:read"])
    headers = {"Authorization": f"Bearer {token}"}

    wrong_id = live.call("POST", "/git/-/presence", headers=headers, json=signal("XYZ", project))
    extra = live.call(
        "POST", "/git/-/presence", headers=headers, json={**signal(DEVICE_A, project), "path": "/Users/a"}
    )
    huge = live.call("POST", "/git/-/presence", headers=headers, json=signal(DEVICE_A, project, name="x" * 70_000))

    assert (wrong_id.status_code, extra.status_code) == (422, 422)
    assert huge.status_code in {413, 422}


def test__presence__stored_report_has_no_path_even_when_the_studio_sends_one_as_a_name(live: Live) -> None:
    anna = live.person("anna")
    project = live.create_project(anna)
    token = live.token(anna, ["git:read"])

    send(live, token, signal(DEVICE_A, project, name="/Users/anna/Documents/диплом"))

    (row,) = live.sql("SELECT name, report::text FROM connected_devices")
    assert row[0] == "Studio"
    assert "Users" not in row[1]


def test__presence__many_signals_do_not_write_the_database_every_time(live: Live) -> None:
    anna = live.person("anna")
    project = live.create_project(anna)
    token = live.token(anna, ["git:read"])

    for _ in range(5):
        send(live, token, signal(DEVICE_A, project))

    (first,) = live.sql("SELECT last_seen_at FROM connected_devices")
    send(live, token, signal(DEVICE_A, project))
    (second,) = live.sql("SELECT last_seen_at FROM connected_devices")
    assert first[0] == second[0]
    # А «онлайн» точен: время берётся из памяти, а не из устаревшей строки.
    devices = live.call("GET", "/api/v1/account/devices", anna).json()["items"]
    assert devices[0]["last_seen_at"] > first[0].isoformat().replace("+00:00", "Z")


def test__presence__a_person_cannot_hold_more_than_twenty_devices(live: Live) -> None:
    anna = live.person("anna")
    project = live.create_project(anna)
    token = live.token(anna, ["git:read"])
    for n in range(20):
        assert raw_send(live, token, signal(f"{n:032x}", project)) == 200

    assert raw_send(live, token, signal("f" * 32, project)) == 409
    with pytest.raises(StudioServerError) as refused:
        send(live, token, signal("f" * 32, project))
    assert refused.value.code == StudioServerErrorCode.too_many_devices


def test__account_devices__forget_removes_only_own_device(live: Live) -> None:
    anna, boris = live.person("anna"), live.person("boris")
    project = live.create_project(anna)
    send(live, live.token(anna, ["git:read"]), signal(DEVICE_A, project))
    send(live, live.token(boris, ["git:read"]), signal(DEVICE_B, project))

    foreign = live.call(
        "DELETE", f"/api/v1/account/devices/{DEVICE_B}", anna, headers=anna.session, cookies=anna.cookies
    )
    own = live.call("DELETE", f"/api/v1/account/devices/{DEVICE_A}", anna, headers=anna.session, cookies=anna.cookies)

    assert (foreign.status_code, own.status_code) == (404, 204)
    assert [d["id"] for d in live.call("GET", "/api/v1/account/devices", boris).json()["items"]] == [DEVICE_B]


# --- права видимости ---


def test__visibility__members_see_each_other_only_as_working_locally_and_nobody_else_sees_anything(live: Live) -> None:
    anna, boris, carol = live.person("anna"), live.person("boris"), live.person("carol")
    project = live.create_project(anna)
    live.add_member(project, boris, "editor")
    send(live, live.token(anna, ["git:read"]), signal(DEVICE_A, project, name="MacBook Анны"))
    send(live, live.token(boris, ["git:read"]), signal(DEVICE_B, project, name="Секретный ноутбук Бориса"))

    anna_view = project_studios(live, anna, project)
    boris_view = project_studios(live, boris, project)

    assert [d["name"] for d in anna_view["mine"]] == ["MacBook Анны"]  # type: ignore[index]
    assert anna_view["others"] == [{"user_id": boris.id, "name": "boris"}]
    assert [d["name"] for d in boris_view["mine"]] == ["Секретный ноутбук Бориса"]  # type: ignore[index]
    assert boris_view["others"] == [{"user_id": anna.id, "name": "anna"}]
    assert "Секретный" not in str(anna_view)
    assert "Studio" not in str(anna_view["others"])
    # Человек вне проекта не получает даже строки «работает локально».
    assert live.call("GET", f"/api/v1/projects/{project}/studios", carol).status_code in {403, 404}


def test__visibility__instance_admin_outside_the_project_sees_no_more_than_anyone(live: Live) -> None:
    anna, boris = live.person("anna"), live.person("boris")
    project = live.create_project(anna)
    send(live, live.token(boris, ["git:read"]), signal(DEVICE_B, project))
    live.sql("UPDATE users SET is_instance_admin = true WHERE id = :id", id=boris.id)
    admin_view = live.call("GET", "/api/v1/account/devices", boris).json()
    admin = live.person("root")
    live.sql("UPDATE users SET is_instance_admin = true WHERE id = :id", id=admin.id)

    through_project = live.call("GET", f"/api/v1/projects/{project}/studios", admin)
    others_devices = live.call("GET", "/api/v1/account/devices", admin).json()

    assert through_project.status_code in {403, 404}
    assert others_devices["items"] == []
    assert [d["id"] for d in admin_view["items"]] == [DEVICE_B]


def test__overview__studio_sees_how_the_cloud_sees_it_and_who_else_is_in_the_project(live: Live) -> None:
    anna, boris = live.person("anna"), live.person("boris")
    project = live.create_project(anna)
    live.add_member(project, boris, "editor")
    token = live.token(anna, ["git:read", "git:write"])
    send(live, token, signal(DEVICE_A, project, activity="building"))
    send(live, live.token(boris, ["git:read"]), signal(DEVICE_B, project))

    response = live.call(
        "GET",
        "/git/-/presence/overview",
        headers={"Authorization": f"Bearer {token}"},
        params={"device_id": DEVICE_A, "project_id": project},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["device"]["presence"] == "online"
    assert (body["device"]["activity"], body["device"]["project"]["ahead"], body["device"]["project"]["behind"]) == (
        "building",
        2,
        1,
    )
    assert body["others"] == [{"user_id": boris.id, "name": "boris"}]


def test__overview__unknown_device_gives_an_empty_answer_and_a_stranger_project_shows_nobody(live: Live) -> None:
    anna, carol = live.person("anna"), live.person("carol")
    project = live.create_project(anna)
    send(live, live.token(anna, ["git:read"]), signal(DEVICE_A, project))
    carol_token = live.token(carol, ["git:read"])

    response = live.call(
        "GET",
        "/git/-/presence/overview",
        headers={"Authorization": f"Bearer {carol_token}"},
        params={"device_id": DEVICE_A, "project_id": project},
    )

    assert response.status_code == 200
    assert response.json()["device"] is None
    assert response.json()["others"] == []


# --- сборки ---


def _doc_id(live: Live, owner: Person, project: str) -> str:
    return str(live.call("GET", f"/api/v1/projects/{project}/documents", owner).json()[0]["id"])


def _cloud_build(live: Live, project: str, doc: str, *, commit: str | None = COMMIT) -> UUID:
    compile_id = uuid4()
    finished = datetime.now(UTC) - timedelta(minutes=5)
    live.sql(
        "INSERT INTO compile_records (id, project_id, doc_id, engine, status, started_at, finished_at, pages, "
        "check_results, log, source_commit, output_sha256, output_size) VALUES (:id, :p, :d, 'xelatex', 'success', "
        ":s, :f, 3, '[]', '', :c, :h, :z)",
        id=compile_id,
        p=UUID(project),
        d=doc,
        s=finished - timedelta(minutes=1),
        f=finished,
        c=commit,
        h=SHA,
        z=len(PDF),
    )
    return compile_id


def _archive(live: Live, project: str, doc: str, compile_id: UUID) -> None:
    """Архивный PDF облачной сборки лежит в объектном хранилище сервера по ключу архива."""
    path = live.tmp / "data" / "objects" / archived_pdf_key(UUID(project), doc, compile_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(PDF)


def test__builds__owner_sees_cloud_build_with_commit_and_the_freshness_against_the_project_head(live: Live) -> None:
    anna = live.person("anna")
    project = live.create_project(anna)
    doc = _doc_id(live, anna, project)
    compile_id = _cloud_build(live, project, doc, commit=None)

    response = live.call("GET", f"/api/v1/projects/{project}/builds", anna)

    assert response.status_code == 200, response.text
    found = next(d for d in response.json()["documents"] if d["doc_id"] == doc)
    assert found["cloud"]["compile_id"] == str(compile_id)
    assert (found["cloud"]["sha256"], found["cloud"]["size"], found["cloud"]["pages"]) == (SHA, len(PDF), 3)
    assert found["cloud"]["fresh"] is None
    assert found["studio"] is None


def test__builds__cloud_pdf_commit_not_equal_to_the_head_is_stale(live: Live) -> None:
    anna = live.person("anna")
    project = live.create_project(anna)
    doc = _doc_id(live, anna, project)
    _cloud_build(live, project, doc, commit="f" * 40)

    found = next(
        d
        for d in live.call("GET", f"/api/v1/projects/{project}/builds", anna).json()["documents"]
        if d["doc_id"] == doc
    )

    assert found["cloud"]["commit"] == "f" * 40
    assert found["cloud"]["fresh"] is False


def test__builds__studio_upload_is_listed_next_to_the_cloud_build(live: Live) -> None:
    anna = live.person("anna")
    project = live.create_project(anna)
    doc = _doc_id(live, anna, project)
    token = live.token(anna, ["git:read", "git:write"])
    live.call(
        "PUT",
        f"/git/-/projects/{project}/documents/{doc}/pdf",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/pdf"},
        content=PDF,
        params={"sha256": SHA, "commit": COMMIT, "pages": 3},
    )

    found = next(
        d
        for d in live.call("GET", f"/api/v1/projects/{project}/builds", anna).json()["documents"]
        if d["doc_id"] == doc
    )

    assert found["studio"]["commit"] == COMMIT
    assert found["studio"]["by_name"] == "anna"
    assert found["cloud"] is None


def test__builds__reader_sees_the_status_but_a_stranger_does_not(live: Live) -> None:
    anna, rita, carol = live.person("anna"), live.person("rita"), live.person("carol")
    project = live.create_project(anna)
    live.add_member(project, rita, "reader", show_sources=False)

    assert live.call("GET", f"/api/v1/projects/{project}/builds", rita).status_code == 200
    assert live.call("GET", f"/api/v1/projects/{project}/builds", carol).status_code in {403, 404}


def test__builds__git_endpoint_needs_the_source_right(live: Live) -> None:
    anna, rita = live.person("anna"), live.person("rita")
    project = live.create_project(anna)
    live.add_member(project, rita, "reader", show_sources=False)
    owner_token = live.token(anna, ["git:read"])
    reader_token = live.token(rita, ["git:read"])

    ok = live.call("GET", f"/git/-/projects/{project}/builds", headers={"Authorization": f"Bearer {owner_token}"})
    denied = live.call("GET", f"/git/-/projects/{project}/builds", headers={"Authorization": f"Bearer {reader_token}"})

    assert ok.status_code == 200
    assert denied.status_code == 403


def test__cloud_pdf__studio_downloads_the_build_and_the_same_fingerprint_gets_304(live: Live, tmp_path: Path) -> None:
    anna = live.person("anna")
    project = live.create_project(anna)
    doc = _doc_id(live, anna, project)
    compile_id = _cloud_build(live, project, doc)
    _archive(live, project, doc, compile_id)
    token = live.token(anna, ["git:read"])
    client = HttpStudioServerClient()
    target = StudioServerTarget(live.base)

    first = asyncio.run(
        client.download_cloud_pdf(
            target, Secret(token), UUID(project), doc, tmp_path / "got.pdf", known_sha256=None, max_bytes=10_000_000
        )
    )
    again = asyncio.run(
        client.download_cloud_pdf(
            target, Secret(token), UUID(project), doc, tmp_path / "again.pdf", known_sha256=SHA, max_bytes=10_000_000
        )
    )

    assert (tmp_path / "got.pdf").read_bytes() == PDF
    assert (first.unchanged, first.sha256, first.source_commit, first.pages) == (False, SHA, COMMIT, 3)
    assert again.unchanged is True
    assert not (tmp_path / "again.pdf").exists()


def test__cloud_pdf__too_large_for_the_studio_limit_is_not_stored(live: Live, tmp_path: Path) -> None:
    anna = live.person("anna")
    project = live.create_project(anna)
    doc = _doc_id(live, anna, project)
    compile_id = _cloud_build(live, project, doc)
    _archive(live, project, doc, compile_id)
    token = live.token(anna, ["git:read"])

    with pytest.raises(StudioServerError) as refused:
        asyncio.run(
            HttpStudioServerClient().download_cloud_pdf(
                StudioServerTarget(live.base),
                Secret(token),
                UUID(project),
                doc,
                tmp_path / "big.pdf",
                known_sha256=None,
                max_bytes=10,
            )
        )

    assert refused.value.code == StudioServerErrorCode.cloud_pdf_too_large
    assert not (tmp_path / "big.pdf").exists()


@pytest.mark.parametrize("who", ["stranger", "reader_without_sources"])
def test__cloud_pdf__without_the_source_right_the_build_is_not_given_out(live: Live, who: str) -> None:
    anna, other = live.person("anna"), live.person("other")
    project = live.create_project(anna)
    doc = _doc_id(live, anna, project)
    compile_id = _cloud_build(live, project, doc)
    _archive(live, project, doc, compile_id)
    if who == "reader_without_sources":
        live.add_member(project, other, "reader", show_sources=False)
    token = live.token(other, ["git:read"])

    response = live.call(
        "GET",
        f"/git/-/projects/{project}/documents/{doc}/pdf",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code in {403, 404}
    assert response.content != PDF


def test__cloud_pdf__document_without_a_cloud_build_is_404(live: Live) -> None:
    anna = live.person("anna")
    project = live.create_project(anna)
    doc = _doc_id(live, anna, project)
    token = live.token(anna, ["git:read"])

    response = live.call(
        "GET", f"/git/-/projects/{project}/documents/{doc}/pdf", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404


def test__overview__studio_client_gets_the_people_of_the_project_with_their_place(live: Live) -> None:
    anna, boris = live.person("anna"), live.person("boris")
    project = live.create_project(anna)
    live.add_member(project, boris, "editor")
    token = live.token(anna, ["git:read"])
    send(live, token, signal(DEVICE_A, project))
    posted = live.call(
        "POST",
        f"/api/v1/projects/{project}/presence",
        boris,
        headers=boris.session,
        cookies=boris.cookies,
        json={"session_id": "tab-boris-0001", "activity": "reviewing", "doc_id": "zayavka"},
    )
    assert posted.status_code == 200, posted.text

    client = HttpStudioServerClient()
    body = asyncio.run(client.presence_overview(StudioServerTarget(live.base), Secret(token), DEVICE_A, UUID(project)))

    people = body["people"]["people"]  # type: ignore[index]
    assert [(p["name"], p["activity"], p["doc_id"], p["channels"], p["me"]) for p in people] == [
        ("anna", "local", None, ["studio"], True),
        ("boris", "reviewing", "zayavka", ["web"], False),
    ]
