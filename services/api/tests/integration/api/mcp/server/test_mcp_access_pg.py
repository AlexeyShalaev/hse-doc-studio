"""MCP облака: доступ к проекту теми же сценариями и правами, что панель «Доступ» (участники, приглашения, отзыв)."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import pytest

from tests.integration.api.mcp.server.test_mcp_server_pg import _call, _created_id, _enable, _rpc, _token
from tests.integration.api.personal.conftest import ORIGIN, Person, Stand

pytestmark = pytest.mark.pg

_TEMPLATE = {"pack_id": "hse-cs-se", "template_id": "vkr", "version": "2026.1"}
_ACCESS_TOOLS = {"list_project_access", "invite_to_project", "revoke_project_invitation", "remove_project_member"}


async def _project(stand: Stand, owner: Person, *members: tuple[Person, str, bool]) -> str:
    """Проект владельца через MCP (с project.json, нужен персонам) и участники `(человек, роль, can_share)`."""
    from hse_doc_studio.infra.db.orm.projects import ProjectMemberRow  # noqa: PLC0415

    project_id = _created_id(
        _call(stand, _token(stand, owner.email, ["mcp"]), "create_project", {"name": "Диплом", **_TEMPLATE})
    )
    async with stand.sessions.use() as db:
        for person, role, can_share in members:
            db.add(
                ProjectMemberRow(
                    project_id=UUID(project_id),
                    principal_kind="user",
                    principal_id=person.id,
                    role=role,
                    can_share=can_share,
                )
            )
    return project_id


def _body(result: dict[str, Any]) -> Any:
    assert result["isError"] is False, result
    return json.loads(result["content"][0]["text"])


def _events(stand: Stand, action: str, project_id: str) -> list[dict[str, Any]]:
    items = stand.admin().get("/api/admin/audit", params={"action": action}).json()["items"]
    return [e for e in items if e["target"] == project_id]


def _assert_forbidden(result: dict[str, Any]) -> None:
    assert result["isError"] is True, result
    assert result["_meta"]["code"] == "forbidden"


async def test__tools_list__server__offers_project_access_tools(stand: Stand) -> None:
    _enable(stand)
    person = await stand.person("ira")
    headers = _token(stand, person.email, ["mcp"])

    tools = {t["name"]: t for t in _rpc(stand, headers, "tools/list").json()["result"]["tools"]}

    assert set(tools) >= _ACCESS_TOOLS
    invite = tools["invite_to_project"]["inputSchema"]
    assert invite["required"] == ["project_id", "email"]
    assert invite["properties"]["role"]["enum"] == ["reader", "reviewer", "editor"]


async def test__owner__invites_supervisor_lists_and_revokes_like_the_panel(stand: Stand) -> None:
    _enable(stand)
    owner = await stand.person("kira")
    supervisor = await stand.person("petrov")
    project_id = await _project(stand, owner)
    headers = _token(stand, owner.email, ["mcp"])

    invited = _body(
        _call(
            stand,
            headers,
            "invite_to_project",
            {"project_id": project_id, "email": supervisor.email, "role": "reviewer", "persona": "supervisor"},
        )
    )

    # Почты на стенде нет: как в окне веба, ссылку пересылает сам приглашающий.
    assert invited["delivery"] == "manual"
    assert invited["link"].startswith(f"{ORIGIN}/project-invite/")
    token = invited["link"].rsplit("/", 1)[1]
    raw = json.dumps(invited, ensure_ascii=False)
    assert raw.count(token) == 1
    assert "token_hash" not in raw
    invitation = invited["invitation"]
    assert (invitation["role"], invitation["persona"], invitation["status"]) == ("reviewer", "supervisor", "pending")
    (created,) = _events(stand, "project.invitation.create", project_id)
    assert created["actor_id"] == owner.id
    assert created["details"]["role"] == "reviewer"

    listed = _body(_call(stand, headers, "list_project_access", {"project_id": project_id}))
    assert [m["role"] for m in listed["members"]] == ["owner"]
    assert [i["invitation_id"] for i in listed["invitations"]] == [invitation["invitation_id"]]
    assert token not in json.dumps(listed)

    revoked = _call(
        stand,
        headers,
        "revoke_project_invitation",
        {"project_id": project_id, "invitation_id": invitation["invitation_id"]},
    )

    assert revoked["isError"] is False, revoked
    assert _body(_call(stand, headers, "list_project_access", {"project_id": project_id}))["invitations"] == []
    (event,) = _events(stand, "project.invitation.revoke", project_id)
    assert event["actor_id"] == owner.id
    accept = stand.client.post(f"/api/v1/project-invitations/{token}/accept", headers=supervisor.headers)
    assert accept.status_code in {403, 404}, accept.text


async def test__owner__removes_a_member(stand: Stand) -> None:
    _enable(stand)
    owner = await stand.person("lena")
    reader = await stand.person("misha")
    project_id = await _project(stand, owner, (reader, "reader", False))
    headers = _token(stand, owner.email, ["mcp"])
    member = next(
        m["member"]
        for m in _body(_call(stand, headers, "list_project_access", {"project_id": project_id}))["members"]
        if m["id"] == reader.id
    )

    removed = _call(stand, headers, "remove_project_member", {"project_id": project_id, "member": member})

    assert removed["isError"] is False, removed
    ids = [m["id"] for m in _body(_call(stand, headers, "list_project_access", {"project_id": project_id}))["members"]]
    assert reader.id not in ids
    (event,) = _events(stand, "project.member.remove", project_id)
    assert (event["actor_id"], event["details"]["principal_id"]) == (owner.id, reader.id)
    gone = _call(stand, _token(stand, reader.email, ["mcp"]), "get_project", {"project_id": project_id})
    assert gone["_meta"]["code"] == "not_found"


async def test__reader__sees_members_but_cannot_invite_revoke_or_remove(stand: Stand) -> None:
    _enable(stand)
    owner = await stand.person("nina")
    reader = await stand.person("oleg")
    reviewer = await stand.person("polina")
    project_id = await _project(stand, owner, (reader, "reader", False), (reviewer, "reviewer", False))
    outsider = await stand.person("outsider")
    owner_headers = _token(stand, owner.email, ["mcp"])
    pending = _body(
        _call(stand, owner_headers, "invite_to_project", {"project_id": project_id, "email": outsider.email})
    )["invitation"]["invitation_id"]
    headers = _token(stand, reader.email, ["mcp"])

    listed = _body(_call(stand, headers, "list_project_access", {"project_id": project_id}))
    invite = _call(stand, headers, "invite_to_project", {"project_id": project_id, "email": outsider.email})
    revoke = _call(stand, headers, "revoke_project_invitation", {"project_id": project_id, "invitation_id": pending})
    remove = _call(stand, headers, "remove_project_member", {"project_id": project_id, "member": f"user:{reviewer.id}"})

    assert {m["id"] for m in listed["members"]} >= {owner.id, reader.id, reviewer.id}
    assert listed["invitations"] is None
    for result in (invite, revoke, remove):
        _assert_forbidden(result)
    assert len(_events(stand, "project.invitation.create", project_id)) == 1
    assert not _events(stand, "project.invitation.revoke", project_id)
    assert not _events(stand, "project.member.remove", project_id)
    still = _body(_call(stand, owner_headers, "list_project_access", {"project_id": project_id}))
    assert [i["invitation_id"] for i in still["invitations"]] == [pending]


async def test__editor__invites_only_with_share_right_and_never_removes(stand: Stand) -> None:
    _enable(stand)
    owner = await stand.person("roma")
    plain = await stand.person("sveta")
    sharing = await stand.person("timur")
    project_id = await _project(stand, owner, (plain, "editor", False), (sharing, "editor", True))
    plain_headers = _token(stand, plain.email, ["mcp"])
    sharing_headers = _token(stand, sharing.email, ["mcp"])
    invitee = await stand.person("ulyana")

    denied = _call(stand, plain_headers, "invite_to_project", {"project_id": project_id, "email": invitee.email})
    too_high = _call(
        stand,
        sharing_headers,
        "invite_to_project",
        {"project_id": project_id, "email": invitee.email, "role": "editor", "can_edit_all": True},
    )
    invited = _body(
        _call(stand, sharing_headers, "invite_to_project", {"project_id": project_id, "email": invitee.email})
    )
    remove = _call(
        stand, sharing_headers, "remove_project_member", {"project_id": project_id, "member": f"user:{plain.id}"}
    )

    _assert_forbidden(denied)
    # Права выше своих («Правит всё» у редактора без него) не выдаются: отказ сценария, как в вебе.
    assert too_high["isError"] is True
    assert "выше своих" in too_high["content"][0]["text"]
    assert invited["invitation"]["role"] == "reviewer"
    _assert_forbidden(remove)
    assert [e["actor_id"] for e in _events(stand, "project.invitation.create", project_id)] == [sharing.id]
    assert not _events(stand, "project.member.remove", project_id)
