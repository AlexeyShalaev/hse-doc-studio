"""Тулы доступа к проекту: флаги приглашения как в окне веба, ссылка только при ручной доставке, список «Ожидают»."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.access.actions import Action
from hse_doc_studio.core.access.checker import IProjectAccessChecker, ProjectForbiddenError
from hse_doc_studio.core.access.context import set_current_actor
from hse_doc_studio.core.access.entities import Actor, Role
from hse_doc_studio.core.access.repositories import ProjectAccessRow
from hse_doc_studio.core.agent.entities import AgentToolContext
from hse_doc_studio.core.enums import EditFormat
from hse_doc_studio.core.invitations.entities import (
    InvitationDelivery,
    InvitationStatus,
    InvitationView,
    MemberTerms,
    ProjectInvitation,
)
from hse_doc_studio.core.listing import Found
from hse_doc_studio.use_cases.mcp.tools._base import ArgumentError
from hse_doc_studio.use_cases.mcp.tools.access import (
    InviteToProjectTool,
    ListProjectAccessTool,
    RemoveProjectMemberTool,
    RevokeProjectInvitationTool,
    invitation_terms,
    member_principal,
)
from hse_doc_studio.use_cases.projects.access_panel import ListProjectAccessUC
from hse_doc_studio.use_cases.projects.invitations import (
    CreateInvitationUC,
    InvitationCreated,
    ListProjectInvitationsUC,
    NewInvitation,
    RevokeInvitationUC,
)
from hse_doc_studio.use_cases.projects.members import RemoveProjectMemberUC

pytestmark = pytest.mark.unit

_ACTOR = Actor.user("u-owner")
_TOKEN_HASH = "secret-token-hash"  # noqa: S105 — тестовое значение


def _invitation(project_id: UUID, terms: MemberTerms) -> ProjectInvitation:
    now = datetime.now(UTC)
    return ProjectInvitation(
        id="inv_1",
        project_id=project_id,
        invitee_user_id=None,
        invitee_email="petrov@hse.ru",
        terms=terms,
        message=None,
        token_hash=_TOKEN_HASH,
        invited_by="u-owner",
        created_at=now,
        expires_at=now + timedelta(days=7),
        status=InvitationStatus.pending,
        last_sent_at=now,
    )


@pytest.fixture(autouse=True)
def _no_actor_left() -> Iterator[None]:
    yield
    set_current_actor(None)


class _Create:
    def __init__(self, delivery: InvitationDelivery) -> None:
        self.delivery = delivery
        self.calls: list[tuple[Actor, UUID, NewInvitation]] = []

    async def execute(self, actor: Actor, project_id: UUID, new: NewInvitation) -> InvitationCreated:
        self.calls.append((actor, project_id, new))
        view = InvitationView(_invitation(project_id, new.terms), None, "Владелец")
        link = "https://studio.example.org/project-invite/hdsi_secret" if self.delivery == "manual" else None
        return InvitationCreated(view, self.delivery, link)


class _Calls:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append(args)
        if kwargs.get("pending_only"):
            return Found([InvitationView(_invitation(args[0], MemberTerms(role=Role.reviewer)), None, "Владелец")], 1)
        if len(args) == 2:
            return Found([ProjectAccessRow("user", "u-owner", "Владелец", "o@hse.ru", Role.owner, True),
                          ProjectAccessRow("user", "u-2", "Петров", "p@hse.ru", Role.reviewer, False)], 2)  # fmt: skip
        return None


class _Checker:
    def __init__(self, *, manage: bool) -> None:
        self.manage = manage

    async def require(self, project_id: UUID, action: Action, path: str | None = None) -> None:
        if action is Action.ACCESS_MANAGE and not self.manage:
            raise ProjectForbiddenError("Forbidden", Role.owner)


class _Deps:
    def __init__(self, by_type: dict[object, object]) -> None:
        self._by_type = by_type

    async def get(self, dependency_type: Any, component: str | None = None) -> Any:
        return self._by_type[dependency_type]


def _ctx(project_id: UUID) -> AgentToolContext:
    return AgentToolContext(project_id=project_id, model="mcp-client", edit_format=EditFormat.search_replace)


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ({}, MemberTerms(role=Role.reviewer)),
        ({"role": "reviewer", "persona": "supervisor"}, MemberTerms(role=Role.reviewer, persona="supervisor")),
        ({"role": "reviewer", "can_share": True, "can_edit_all": True, "show_sources": False},
         MemberTerms(role=Role.reviewer)),
        ({"role": "reader", "show_sources": False}, MemberTerms(role=Role.reader, show_sources=False)),
        ({"role": "editor", "can_share": True}, MemberTerms(role=Role.editor, can_share=True)),
    ],
)  # fmt: skip
def test__invitation_terms__flags_follow_the_web_dialog(args: dict[str, object], expected: MemberTerms) -> None:
    assert invitation_terms(args) == expected


@pytest.mark.parametrize("role", ["owner", "admin", "Reviewer"])
def test__invitation_terms__owner_or_unknown_role__rejected(role: str) -> None:
    with pytest.raises(ArgumentError, match="role"):
        invitation_terms({"role": role})


@pytest.mark.parametrize(("raw", "expected"), [("user:u-2", ("user", "u-2")), ("group:g 1 ", ("group", "g 1"))])
def test__member_principal__parses_kind_and_id(raw: str, expected: tuple[str, str]) -> None:
    assert member_principal(raw) == expected


@pytest.mark.parametrize("raw", ["u-2", "org:o1", "user:", "user: "])
def test__member_principal__bad_value__rejected(raw: str) -> None:
    with pytest.raises(ArgumentError, match="member"):
        member_principal(raw)


async def test__invite__email_delivery__no_link_and_no_token_in_the_answer() -> None:
    create, project_id = _Create("email"), uuid4()
    tool = InviteToProjectTool(_Deps({CreateInvitationUC: create}))  # type: ignore[arg-type]

    set_current_actor(_ACTOR)
    result = await tool.handle(
        _ctx(project_id), {"email": "petrov@hse.ru", "role": "reviewer", "persona": "supervisor"}
    )

    assert result.is_error is False, result.text
    body = json.loads(result.text)
    assert body["delivery"] == "email"
    assert "link" not in body
    assert _TOKEN_HASH not in result.text
    ((actor, called_project, new),) = create.calls
    assert (actor, called_project) == (_ACTOR, project_id)
    assert new == NewInvitation(
        terms=MemberTerms(role=Role.reviewer, persona="supervisor"), email="petrov@hse.ru", expires_in_days=7
    )


async def test__invite__manual_delivery__returns_the_link_like_the_web_dialog() -> None:
    tool = InviteToProjectTool(_Deps({CreateInvitationUC: _Create("manual")}))  # type: ignore[arg-type]

    set_current_actor(_ACTOR)
    result = await tool.handle(_ctx(uuid4()), {"email": "petrov@hse.ru"})

    body = json.loads(result.text)
    assert body["link"] == "https://studio.example.org/project-invite/hdsi_secret"
    assert body["invitation"]["invitation_id"] == "inv_1"
    assert "token" not in result.text.replace("project-invite", "")
    assert _TOKEN_HASH not in result.text


@pytest.mark.parametrize(
    "args",
    [{}, {"email": " "}, {"email": "a@b.c", "expires_in_days": 0}, {"email": "a@b.c", "expires_in_days": 31},
     {"email": "a@b.c", "expires_in_days": "7"}, {"email": "a@b.c", "message": "x" * 1001}],
)  # fmt: skip
async def test__invite__bad_arguments__rejected_before_the_use_case(args: dict[str, object]) -> None:
    create = _Create("email")
    tool = InviteToProjectTool(_Deps({CreateInvitationUC: create}))  # type: ignore[arg-type]

    set_current_actor(_ACTOR)
    with pytest.raises(ArgumentError):
        await tool.handle(_ctx(uuid4()), args)

    assert create.calls == []


@pytest.mark.parametrize(("manage", "has_invitations"), [(True, True), (False, False)])
async def test__list__invitations_only_for_access_managers(manage: bool, has_invitations: bool) -> None:
    access, invitations = _Calls(), _Calls()
    checker = _Checker(manage=manage)
    deps = {ListProjectAccessUC: access, ListProjectInvitationsUC: invitations, IProjectAccessChecker: checker}
    tool = ListProjectAccessTool(_Deps(deps))  # type: ignore[arg-type]

    result = await tool.handle(_ctx(uuid4()), {"q": "петров", "limit": 500})

    body = json.loads(result.text)
    owner, member = body["members"]
    assert "member" not in owner
    assert member["member"] == "user:u-2"
    assert access.calls[0][1].q == "петров"
    assert access.calls[0][1].window.limit == 100
    if has_invitations:
        assert body["invitations"][0]["invitation_id"] == "inv_1"
        assert body["invitations"][0]["email"] == "petrov@hse.ru"
        assert _TOKEN_HASH not in result.text
    else:
        assert body["invitations"] is None
        assert invitations.calls == []


async def test__revoke_and_remove__call_the_web_use_cases() -> None:
    revoke, remove, project_id = _Calls(), _Calls(), uuid4()
    deps: Any = _Deps({RevokeInvitationUC: revoke, RemoveProjectMemberUC: remove})

    set_current_actor(_ACTOR)
    revoked = await RevokeProjectInvitationTool(deps).handle(_ctx(project_id), {"invitation_id": "inv_1"})
    removed = await RemoveProjectMemberTool(deps).handle(_ctx(project_id), {"member": "group:g1"})

    assert revoked.is_error is False
    assert removed.is_error is False
    assert revoke.calls == [(_ACTOR, project_id, "inv_1")]
    assert remove.calls == [(_ACTOR, project_id, "group", "g1")]
