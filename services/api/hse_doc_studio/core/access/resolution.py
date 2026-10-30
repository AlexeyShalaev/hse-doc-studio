"""Права одного человека на проект из всех источников: владение, организация, прямая роль, группы."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from hse_doc_studio.core.access.entities import Grant, Role
from hse_doc_studio.core.access.repositories import ProjectMemberGrant

ROLE_ORDER = (Role.reader, Role.reviewer, Role.editor, Role.owner)


@dataclass(frozen=True)
class OrgStanding:
    """Положение человека в организации-владельце проекта."""

    is_admin: bool
    org_visible: bool


def resolve_grant(
    *,
    is_owner: bool,
    direct: ProjectMemberGrant | None,
    groups: Iterable[ProjectMemberGrant] = (),
    org: OrgStanding | None = None,
) -> Grant | None:
    """Старшая из ролей; при равенстве первым идёт более личный источник (владение, прямая запись, группа,
    организация). Роль и флаги берутся у победившего источника, поэтому группа не понижает владельца и
    прямую запись. Админ организации владеет только проектами этой организации: к личным проектам
    её участников доступа нет."""
    candidates: list[Grant] = []
    if is_owner or (org is not None and org.is_admin):
        candidates.append(_full(Role.owner, direct.persona if direct is not None else None))
    if direct is not None:
        candidates.append(_of(direct))
    candidates.extend(_of(g) for g in sorted(groups, key=lambda g: g.principal_id))
    if org is not None and org.org_visible:
        candidates.append(Grant(role=Role.reader, show_sources=False))
    best: Grant | None = None
    for grant in candidates:
        if best is None or ROLE_ORDER.index(grant.role) > ROLE_ORDER.index(best.role):
            best = grant
    return best


def _full(role: Role, persona: str | None) -> Grant:
    return Grant(role=role, persona_slug=persona, show_sources=True, can_share=True, can_edit_all=True)


def _of(member: ProjectMemberGrant) -> Grant:
    owner = member.role is Role.owner
    return Grant(
        role=member.role,
        persona_slug=member.persona,
        show_sources=member.show_sources or owner,
        can_share=member.can_share or owner,
        can_edit_all=member.can_edit_all or owner,
    )
