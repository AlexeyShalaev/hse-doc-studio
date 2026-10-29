"""Права из всех источников: таблица «владелец x организация x прямая запись x группы x видимость»."""

from __future__ import annotations

import pytest
from hse_doc_studio.core.access.entities import Role
from hse_doc_studio.core.access.repositories import ProjectMemberGrant
from hse_doc_studio.core.access.resolution import OrgStanding, resolve_grant

R, V, E, OWN = Role.reader, Role.reviewer, Role.editor, Role.owner
NONE = None


def _m(role: Role, kind: str = "user", pid: str = "x", **extra: object) -> ProjectMemberGrant:
    return ProjectMemberGrant(kind, pid, role, **extra)  # type: ignore[arg-type]


ADMIN = OrgStanding(is_admin=True, org_visible=False)
MEMBER_VISIBLE = OrgStanding(is_admin=False, org_visible=True)
MEMBER_HIDDEN = OrgStanding(is_admin=False, org_visible=False)


@pytest.mark.parametrize(
    ("is_owner", "direct", "groups", "org", "expected"),
    [
        (False, NONE, [], NONE, NONE),
        (True, NONE, [], NONE, OWN),
        # личный владелец не понижается ни записью, ни группой
        (True, _m(R), [_m(R, "group", "g")], MEMBER_HIDDEN, OWN),
        (False, _m(E), [], NONE, E),
        (False, NONE, [_m(V, "group", "g")], NONE, V),
        # максимум из нескольких групп и прямой записи
        (False, _m(R), [_m(V, "group", "g1"), _m(E, "group", "g2")], NONE, E),
        (False, _m(E), [_m(R, "group", "g")], NONE, E),
        # организация: участник видит проект только при org_visible, и как читатель
        (False, NONE, [], MEMBER_VISIBLE, R),
        (False, NONE, [], MEMBER_HIDDEN, NONE),
        (False, _m(E), [], MEMBER_VISIBLE, E),
        (False, NONE, [_m(V, "group", "g")], MEMBER_VISIBLE, V),
        # админ или владелец организации владеют её проектами
        (False, NONE, [], ADMIN, OWN),
        (False, _m(R), [], ADMIN, OWN),
    ],
)
def test__resolve_grant__table(is_owner, direct, groups, org, expected) -> None:  # type: ignore[no-untyped-def]
    grant = resolve_grant(is_owner=is_owner, direct=direct, groups=groups, org=org)

    assert (grant.role if grant else None) is expected


def test__resolve_grant__flags_come_from_winning_source() -> None:
    grant = resolve_grant(
        is_owner=False,
        direct=_m(R, persona="ivanov", show_sources=False),
        groups=[_m(E, "group", "g", persona="petrov", show_sources=True, can_share=True)],
    )

    assert grant is not None
    assert (grant.role, grant.persona_slug, grant.show_sources, grant.can_share) == (E, "petrov", True, True)


def test__resolve_grant__tie_prefers_direct_record() -> None:
    grant = resolve_grant(is_owner=False, direct=_m(E, persona="own"), groups=[_m(E, "group", "g", persona="grp")])

    assert grant is not None
    assert grant.persona_slug == "own"


def test__resolve_grant__org_visible_reader_has_no_sources() -> None:
    grant = resolve_grant(is_owner=False, direct=None, org=MEMBER_VISIBLE)

    assert grant is not None
    assert not grant.show_sources


def test__resolve_grant__owner_keeps_persona_of_own_row() -> None:
    grant = resolve_grant(is_owner=True, direct=_m(OWN, persona="me"))

    assert grant is not None
    assert (grant.role, grant.persona_slug, grant.can_share) == (OWN, "me", True)
