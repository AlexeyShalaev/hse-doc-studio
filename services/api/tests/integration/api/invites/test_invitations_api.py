"""Приглашения в проект: человеку из круга владельца, на почту без аккаунта (S12), S10, повтор и отзыв, права."""

from __future__ import annotations

import pytest

from tests.integration.api.invites.conftest import (
    Stand,
    add_member,
    login,
    make_org,
    seed_shared_project,
)

pytestmark = pytest.mark.pg


def _invite(stand: Stand, project: str, headers: dict[str, str], **body: object):  # type: ignore[no-untyped-def]
    payload = {"role": "reviewer", **body}
    return stand.client.post(f"/api/v1/projects/{project}/invitations", json=payload, headers=headers)


async def test__invite_user__inbox_then_accept_makes_a_member(stand: Stand) -> None:
    anna, petr = await stand.person("anna"), await stand.person("petr")
    await make_org(stand, "kafedra", (anna, "member"), (petr, "member"))
    project = await seed_shared_project(stand, anna)

    created = _invite(stand, project, anna.headers, user_id=petr.id, message="Глава 2")
    assert created.status_code == 201, created.text
    body = created.json()
    assert (body["delivery"], body["link"]) == ("inbox", None)
    assert body["invitation"]["invitee"] == {"kind": "user", "user_id": petr.id, "name": "petr", "email_hint": None}
    invitation_id = body["invitation"]["id"]

    # До принятия доступа нет: приглашение только во «Входящих».
    assert stand.client.get(f"/api/v1/projects/{project}/members", headers=petr.headers).status_code == 404
    mine = stand.client.get("/api/v1/account/invitations", headers=petr.headers).json()["items"]
    assert [(i["id"], i["project"]["name"], i["status"]) for i in mine] == [(invitation_id, "Диплом", "pending")]
    summary = stand.client.get("/api/v1/account/inbox/summary", headers=petr.headers).json()
    assert summary == {"unread": 1, "invitations": 1, "transfers": 0, "access_requests": 0}
    kinds = [n["kind"] for n in stand.client.get("/api/v1/account/notifications", headers=petr.headers).json()["items"]]
    assert kinds == ["project_invitation"]

    accepted = stand.client.post(f"/api/v1/account/invitations/{invitation_id}/accept", headers=petr.headers)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "accepted"
    assert stand.client.get(f"/api/v1/projects/{project}/members", headers=petr.headers).status_code == 200
    again = stand.client.post(f"/api/v1/account/invitations/{invitation_id}/accept", headers=petr.headers)
    assert (again.status_code, again.json()["code"]) == (409, "invitation_not_pending")

    owner_feed = stand.client.get("/api/v1/account/notifications", headers=anna.headers).json()["items"]
    assert [(n["kind"], n["payload"]["outcome"]) for n in owner_feed] == [("invitation_accepted", "accepted")]
    member_again = _invite(stand, project, anna.headers, user_id=petr.id)
    assert (member_again.status_code, member_again.json()["code"]) == (409, "already_member")


async def test__invite_user__outside_circle_is_404_and_duplicate_is_409(stand: Stand) -> None:
    anna, petr, eve = await stand.person("anna"), await stand.person("petr"), await stand.person("eve")
    await make_org(stand, "kafedra", (anna, "member"), (petr, "member"))
    project = await seed_shared_project(stand, anna)

    assert _invite(stand, project, anna.headers, user_id=eve.id).status_code == 404
    assert _invite(stand, project, anna.headers, user_id="nobody").status_code == 404
    first = _invite(stand, project, anna.headers, user_id=petr.id)
    assert first.status_code == 201
    duplicate = _invite(stand, project, anna.headers, user_id=petr.id)
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "invitation_pending"
    assert duplicate.json()["invitation_id"] == first.json()["invitation"]["id"]


async def test__decline__notifies_inviter_and_gives_no_access(stand: Stand) -> None:
    anna, petr = await stand.person("anna"), await stand.person("petr")
    await make_org(stand, "kafedra", (anna, "member"), (petr, "member"))
    project = await seed_shared_project(stand, anna)
    invitation_id = _invite(stand, project, anna.headers, user_id=petr.id).json()["invitation"]["id"]

    other = await stand.person("vera")
    assert (
        stand.client.post(f"/api/v1/account/invitations/{invitation_id}/accept", headers=other.headers).status_code
        == 404
    )
    declined = stand.client.post(f"/api/v1/account/invitations/{invitation_id}/decline", headers=petr.headers)
    assert declined.json()["status"] == "declined"
    assert stand.client.get(f"/api/v1/projects/{project}/members", headers=petr.headers).status_code == 404
    feed = stand.client.get("/api/v1/account/notifications", headers=anna.headers).json()["items"]
    assert feed[0]["kind"] == "invitation_declined"


async def test__s10__direct_add_of_a_new_person_needs_an_invitation(stand: Stand) -> None:
    anna, petr, vera = await stand.person("anna"), await stand.person("petr"), await stand.person("vera")
    await make_org(stand, "kafedra", (anna, "member"), (petr, "member"), (vera, "member"))
    project = await seed_shared_project(stand, anna, (vera, "reader"))
    body = {"role": "editor", "persona": None, "can_share": False, "show_sources": True, "can_edit_all": False}

    refused = stand.client.put(f"/api/v1/projects/{project}/members/user:{petr.id}", json=body, headers=anna.headers)
    assert (refused.status_code, refused.json()["code"]) == (409, "invitation_required")
    # Роль уже добавленного меняется напрямую.
    changed = stand.client.put(f"/api/v1/projects/{project}/members/user:{vera.id}", json=body, headers=anna.headers)
    assert changed.status_code == 200, changed.text


async def test__s10__org_admin_adds_org_member_directly(stand: Stand) -> None:
    admin, member = await stand.person("admin"), await stand.person("member")
    org_id = await make_org(stand, "mspin", (admin, "admin"), (member, "member"))
    project = await seed_shared_project(stand, admin)
    from uuid import UUID  # noqa: PLC0415

    from hse_doc_studio.infra.db.orm.projects import ProjectRow  # noqa: PLC0415
    from sqlalchemy import update  # noqa: PLC0415

    async with stand.sessions.use() as db:
        await db.execute(
            update(ProjectRow).where(ProjectRow.id == UUID(project)).values(owner_user_id=None, owner_org_id=org_id)
        )
    body = {"role": "reader", "persona": None, "can_share": False, "show_sources": True, "can_edit_all": False}
    added = stand.client.put(f"/api/v1/projects/{project}/members/user:{member.id}", json=body, headers=admin.headers)
    assert added.status_code == 200, added.text


async def test__email_invite_without_account__manual_link_signup_and_accept(stand: Stand) -> None:
    anna = await stand.person("anna")
    project = await seed_shared_project(stand, anna)

    created = _invite(stand, project, anna.headers, email="Petr.New@Example.org", role="editor")
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["delivery"] == "manual"
    assert body["invitation"]["invitee"] == {
        "kind": "email",
        "user_id": None,
        "name": None,
        "email_hint": "petr.new@example.org",
    }
    token = body["link"].rsplit("/", 1)[1]
    assert token.startswith("hspi_")

    preview = stand.client.get(f"/api/v1/project-invitations/{token}").json()
    assert preview["state"] == "ok"
    assert (preview["project_name"], preview["role"], preview["email_hint"]) == ("Диплом", "editor", "p***@example.org")
    # Режим «по приглашению»: ссылка письма сама служит регистрационным приглашением (S12).
    assert preview["registration_token"] == token

    registered = stand.client.post(
        "/api/v1/auth/register",
        json={
            "email": "petr.new@example.org",
            "name": "Пётр",
            "password": "Very-long-password-1",
            "invitation_token": token,
        },
        headers={"Origin": "http://localhost:8100"},
    )
    assert registered.status_code in (200, 201), registered.text
    petr = login(stand, "petr.new@example.org", "Very-long-password-1")

    mine = petr.get("/api/v1/account/invitations").json()["items"]
    assert [i["role"] for i in mine] == ["editor"]
    accepted = petr.post(f"/api/v1/project-invitations/{token}/accept")
    assert accepted.status_code == 200, accepted.text
    assert petr.get(f"/api/v1/projects/{project}/members").status_code == 200
    assert stand.client.get(f"/api/v1/project-invitations/{token}").json()["state"] == "used"


async def test__email_invite__other_account_cannot_accept_by_link(stand: Stand) -> None:
    anna, vera = await stand.person("anna"), await stand.person("vera")
    project = await seed_shared_project(stand, anna)
    token = _invite(stand, project, anna.headers, email="someone@example.org").json()["link"].rsplit("/", 1)[1]

    mismatch = stand.client.post(f"/api/v1/project-invitations/{token}/accept", headers=vera.headers)
    assert mismatch.status_code == 403
    assert (mismatch.json()["code"], mismatch.json()["email_hint"]) == ("invitation_email_mismatch", "s***@example.org")
    assert stand.client.get("/api/v1/project-invitations/hspi_unknown").json()["state"] == "invalid"


async def test__email_invite_to_existing_account__same_answer_and_goes_to_inbox(stand: Stand) -> None:
    anna, petr = await stand.person("anna"), await stand.person("petr")
    project = await seed_shared_project(stand, anna)

    created = _invite(stand, project, anna.headers, email=petr.email)
    assert created.status_code == 201
    assert created.json()["delivery"] == "manual"
    assert created.json()["invitation"]["invitee"]["kind"] == "email"
    mine = stand.client.get("/api/v1/account/invitations", headers=petr.headers).json()["items"]
    accepted = stand.client.post(f"/api/v1/account/invitations/{mine[0]['id']}/accept", headers=petr.headers)
    assert accepted.status_code == 200, accepted.text


async def test__resend_and_revoke(stand: Stand) -> None:
    anna = await stand.person("anna")
    project = await seed_shared_project(stand, anna)
    created = _invite(stand, project, anna.headers, email="x@example.org").json()
    invitation_id, token = created["invitation"]["id"], created["link"].rsplit("/", 1)[1]
    base = f"/api/v1/projects/{project}/invitations"

    too_soon = stand.client.post(f"{base}/{invitation_id}/resend", headers=anna.headers)
    assert (too_soon.status_code, too_soon.json()["code"]) == (429, "invitation_resend_too_soon")

    listed = stand.client.get(base, headers=anna.headers).json()
    assert (listed["total"], listed["items"][0]["status"]) == (1, "pending")
    assert stand.client.delete(f"{base}/{invitation_id}", headers=anna.headers).status_code == 204
    assert stand.client.get(base, headers=anna.headers).json()["total"] == 0
    assert stand.client.get(base, params={"status": "all"}, headers=anna.headers).json()["items"][0]["status"] == (
        "revoked"
    )
    assert stand.client.get(f"/api/v1/project-invitations/{token}").json()["state"] == "invalid"
    assert stand.client.post(f"{base}/{invitation_id}/resend", headers=anna.headers).status_code == 409


async def test__rights__access_manage_and_role_ceiling(stand: Stand) -> None:
    anna, ed, sharer, reader, eve = (
        await stand.person("anna"),
        await stand.person("ed"),
        await stand.person("sharer"),
        await stand.person("reader"),
        await stand.person("eve"),
    )
    project = await seed_shared_project(stand, anna, (ed, "editor"), (reader, "reader"))
    await add_member(stand, project, sharer, "editor", can_share=True)
    base = f"/api/v1/projects/{project}/invitations"

    assert stand.client.get(base, headers=ed.headers).status_code == 403
    assert stand.client.get(base, headers=reader.headers).status_code == 403
    assert stand.client.get(base, headers=eve.headers).status_code == 404
    assert stand.client.get(base, headers=sharer.headers).status_code == 200

    too_high = _invite(stand, project, sharer.headers, email="a@example.org", role="editor", can_edit_all=True)
    assert (too_high.status_code, too_high.json()["code"]) == (422, "invitation_role_too_high")
    allowed = _invite(stand, project, sharer.headers, email="a@example.org", role="editor", can_share=True)
    assert allowed.status_code == 201, allowed.text
    persona = _invite(stand, project, anna.headers, email="b@example.org", persona="ghost")
    assert (persona.status_code, persona.json()["code"]) == (422, "persona_unknown")


async def test__bootstrap_carries_inbox_badge(stand: Stand) -> None:
    anna, petr = await stand.person("anna"), await stand.person("petr")
    await make_org(stand, "kafedra", (anna, "member"), (petr, "member"))
    project = await seed_shared_project(stand, anna)
    _invite(stand, project, anna.headers, user_id=petr.id)

    session = login(stand, petr.email)
    boot = session.get("/api/v1/session/bootstrap").json()
    # Непрочитанное уведомление и ожидающее приглашение.
    assert boot["inbox"] == {"unread": 2}
    assert stand.client.get("/api/v1/session/bootstrap").json()["inbox"] is None
