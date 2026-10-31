"""Запросы доступа (S13) и передача владения (S14) через живое приложение."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from hse_doc_studio.infra.db.orm.projects import ProjectMemberRow, ProjectRow
from sqlalchemy import select, update

from tests.integration.api.invites.conftest import Stand, add_member, login, make_org, seed_shared_project

pytestmark = pytest.mark.pg


async def _role(stand: Stand, project: str, user_id: str) -> str | None:
    async with stand.sessions.use() as db:
        return (
            await db.execute(
                select(ProjectMemberRow.role).where(
                    ProjectMemberRow.project_id == UUID(project),
                    ProjectMemberRow.principal_kind == "user",
                    ProjectMemberRow.principal_id == user_id,
                )
            )
        ).scalar_one_or_none()


async def _owner(stand: Stand, project: str) -> tuple[str | None, str | None, str]:
    async with stand.sessions.use() as db:
        row = (
            await db.execute(
                select(ProjectRow.owner_user_id, ProjectRow.owner_org_id, ProjectRow.build_runners).where(
                    ProjectRow.id == UUID(project)
                )
            )
        ).one()
    return row.owner_user_id, row.owner_org_id, row.build_runners


async def test__access_request__same_answer_owner_approves_requester_notified(stand: Stand) -> None:
    anna, vera = await stand.person("anna"), await stand.person("vera")
    project = await seed_shared_project(stand, anna)
    session = login(stand, vera.email)

    missing = session.post("/api/v1/access-requests", json={"project_id": str(uuid4()), "message": "?"})
    created = session.post("/api/v1/access-requests", json={"project_id": project, "message": "Соавтор главы 3"})
    assert (missing.status_code, missing.json()) == (202, {"accepted": True})
    assert (created.status_code, created.json()) == (202, {"accepted": True})
    # Повтор не плодит записей, «мои запросы» показывают только созданное, имени проекта до одобрения нет.
    session.post("/api/v1/access-requests", json={"project_id": project, "message": None})
    mine = session.get("/api/v1/account/access-requests").json()["items"]
    assert [(m["project"]["id"], m["project"]["name"], m["status"]) for m in mine] == [(project, None, "pending")]

    listed = stand.client.get(f"/api/v1/projects/{project}/access-requests", headers=anna.headers).json()
    assert listed["total"] == 1
    request_id = listed["items"][0]["id"]
    assert listed["items"][0]["requester"]["email"] == vera.email
    assert stand.client.get("/api/v1/account/inbox/summary", headers=anna.headers).json()["access_requests"] == 1
    feed = stand.client.get("/api/v1/account/notifications", headers=anna.headers).json()["items"]
    assert [(n["kind"], n["payload"]["ref_id"]) for n in feed] == [("access_request", request_id)]

    approve = {"role": "editor", "persona": None, "can_share": False, "show_sources": True, "can_edit_all": False}
    approved = stand.client.post(
        f"/api/v1/projects/{project}/access-requests/{request_id}/approve", json=approve, headers=anna.headers
    )
    assert approved.status_code == 200, approved.text
    assert (approved.json()["status"], approved.json()["granted_role"]) == ("approved", "editor")
    assert approved.json()["decided_by"]["id"] == anna.id
    assert await _role(stand, project, vera.id) == "editor"
    twice = stand.client.post(
        f"/api/v1/projects/{project}/access-requests/{request_id}/approve", json=approve, headers=anna.headers
    )
    assert (twice.status_code, twice.json()["code"]) == (409, "access_request_decided")

    decided = stand.client.get("/api/v1/account/notifications", headers=vera.headers).json()["items"][0]
    assert (decided["kind"], decided["payload"]["outcome"], decided["payload"]["role"]) == (
        "access_request_decided",
        "approved",
        "editor",
    )
    mine = session.get("/api/v1/account/access-requests").json()["items"]
    assert (mine[0]["project"]["name"], mine[0]["status"]) == ("Диплом", "approved")


async def test__access_request__pat_refused_deny_and_cooldown_cancel(stand: Stand) -> None:
    anna, vera, boris = await stand.person("anna"), await stand.person("vera"), await stand.person("boris")
    project = await seed_shared_project(stand, anna)

    by_token = stand.client.post("/api/v1/access-requests", json={"project_id": project}, headers=vera.headers)
    assert by_token.status_code == 403

    session = login(stand, vera.email)
    session.post("/api/v1/access-requests", json={"project_id": project, "message": None})
    request_id = stand.client.get(f"/api/v1/projects/{project}/access-requests", headers=anna.headers).json()["items"][
        0
    ]["id"]
    denied = stand.client.post(
        f"/api/v1/projects/{project}/access-requests/{request_id}/deny", json={"message": None}, headers=anna.headers
    )
    assert denied.json()["status"] == "denied"
    # Пауза 7 дней после отказа: новый запрос не появляется.
    session.post("/api/v1/access-requests", json={"project_id": project, "message": None})
    listed = stand.client.get(f"/api/v1/projects/{project}/access-requests", headers=anna.headers).json()
    assert listed["total"] == 0

    boris_session = login(stand, boris.email)
    boris_session.post("/api/v1/access-requests", json={"project_id": project, "message": None})
    mine = boris_session.get("/api/v1/account/access-requests").json()["items"]
    assert boris_session.delete(f"/api/v1/account/access-requests/{mine[0]['id']}").status_code == 204
    assert session.delete(f"/api/v1/account/access-requests/{mine[0]['id']}").status_code == 404
    assert boris_session.get("/api/v1/account/access-requests").json()["items"][0]["status"] == "cancelled"


async def test__access_request__member_creates_nothing(stand: Stand) -> None:
    anna, vera = await stand.person("anna"), await stand.person("vera")
    project = await seed_shared_project(stand, anna, (vera, "reader"))
    login(stand, vera.email).post("/api/v1/access-requests", json={"project_id": project, "message": None})
    assert stand.client.get(f"/api/v1/projects/{project}/access-requests", headers=anna.headers).json()["total"] == 0


async def test__transfer_to_person__pending_then_accept_swaps_owner(stand: Stand) -> None:
    anna, vera, boris = await stand.person("anna"), await stand.person("vera"), await stand.person("boris")
    await make_org(stand, "kafedra", (anna, "member"), (vera, "member"))
    project = await seed_shared_project(stand, anna, (boris, "reader"))
    await add_member(stand, project, vera, "reviewer")
    async with stand.sessions.use() as db:
        await db.execute(update(ProjectRow).where(ProjectRow.id == UUID(project)).values(build_runners="owner"))
    base = f"/api/v1/projects/{project}/transfer"

    assert stand.client.get(base, headers=anna.headers).json() == {"pending": False, "transfer": None}
    outsider = await stand.person("eve")
    refused = stand.client.post(base, json={"to_kind": "user", "to_id": outsider.id}, headers=anna.headers)
    assert refused.status_code == 404
    assert stand.client.post(base, json={"to_kind": "user", "to_id": vera.id}, headers=boris.headers).status_code == 403

    started = stand.client.post(
        base, json={"to_kind": "user", "to_id": vera.id, "message": "Выпускаюсь"}, headers=anna.headers
    )
    assert started.status_code == 201, started.text
    assert started.json()["transfer"]["to"] == {"kind": "user", "id": vera.id, "name": "vera"}
    assert stand.client.get(base, headers=boris.headers).json() == {"pending": True, "transfer": None}

    mine = stand.client.get("/api/v1/account/transfers", headers=vera.headers).json()["items"]
    assert [(t["project"]["name"], t["from"]["name"], t["previous_owner_role"]) for t in mine] == [
        ("Диплом", "anna", "editor")
    ]
    accepted = stand.client.post(f"/api/v1/account/transfers/{mine[0]['id']}/accept", headers=vera.headers)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "accepted"
    assert await _owner(stand, project) == (vera.id, None, "shared")
    assert await _role(stand, project, anna.id) == "editor"
    assert await _role(stand, project, vera.id) in (None, "owner")
    assert stand.client.get(base, headers=vera.headers).json()["pending"] is False
    feed = stand.client.get("/api/v1/account/notifications", headers=anna.headers).json()["items"]
    assert feed[0]["kind"] == "transfer_decided"


async def test__transfer__decline_cancel_and_supersede(stand: Stand) -> None:
    anna, vera, petr = await stand.person("anna"), await stand.person("vera"), await stand.person("petr")
    await make_org(stand, "kafedra", (anna, "member"), (vera, "member"), (petr, "member"))
    project = await seed_shared_project(stand, anna)
    base = f"/api/v1/projects/{project}/transfer"

    stand.client.post(base, json={"to_kind": "user", "to_id": vera.id}, headers=anna.headers)
    stand.client.post(base, json={"to_kind": "user", "to_id": petr.id}, headers=anna.headers)
    # Прежняя передача заменена новой.
    assert stand.client.get("/api/v1/account/transfers", headers=vera.headers).json()["items"] == []
    petr_transfer = stand.client.get("/api/v1/account/transfers", headers=petr.headers).json()["items"][0]
    declined = stand.client.post(f"/api/v1/account/transfers/{petr_transfer['id']}/decline", headers=petr.headers)
    assert declined.json()["status"] == "declined"
    assert await _owner(stand, project) == (anna.id, None, "shared")

    stand.client.post(base, json={"to_kind": "user", "to_id": vera.id}, headers=anna.headers)
    assert stand.client.delete(base, headers=anna.headers).status_code == 204
    assert stand.client.delete(base, headers=anna.headers).status_code == 404


async def test__transfer_to_org__needs_confirm_name_and_applies_at_once(stand: Stand) -> None:
    anna, member = await stand.person("anna"), await stand.person("member")
    org_id = await make_org(stand, "mspin", (anna, "admin"), (member, "member"))
    project = await seed_shared_project(stand, anna)
    base = f"/api/v1/projects/{project}/transfer"

    wrong = stand.client.post(
        base, json={"to_kind": "org", "to_id": "mspin", "confirm_name": "Другое"}, headers=anna.headers
    )
    assert (wrong.status_code, wrong.json()["code"]) == (422, "confirm_name_mismatch")
    done = stand.client.post(
        base, json={"to_kind": "org", "to_id": "mspin", "confirm_name": "Диплом"}, headers=anna.headers
    )
    assert done.status_code == 201, done.text
    assert done.json() == {"pending": False, "transfer": None}
    assert await _owner(stand, project) == (None, org_id, "shared")
    assert await _role(stand, project, anna.id) == "editor"
