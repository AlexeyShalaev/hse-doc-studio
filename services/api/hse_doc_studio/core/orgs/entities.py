"""Сущности организаций и групп. Роли организации читает загрузчик прав проекта; сама `policy.py` их не знает."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

ORG_NAME_MAX = 120
GROUP_NAME_MAX = 80
POLICIES_VERSION = 1


class OrgRole(StrEnum):
    member = "member"
    admin = "admin"
    owner = "owner"

    @property
    def rank(self) -> int:
        return _RANK[self]


_RANK = {OrgRole.member: 1, OrgRole.admin: 2, OrgRole.owner: 3}


@dataclass(frozen=True)
class Org:
    id: str
    slug: str
    name: str
    created_at: datetime
    created_by: str | None = None
    # Содержимое политик появится в этапе 3; пока хранится только версия формата.
    policies: Mapping[str, object] = field(default_factory=lambda: {"version": POLICIES_VERSION})


@dataclass(frozen=True)
class OrgMember:
    org_id: str
    user_id: str
    role: OrgRole
    created_at: datetime


@dataclass(frozen=True)
class OrgMemberView:
    member: OrgMember
    name: str
    email: str


@dataclass(frozen=True)
class OrgSummary:
    """Организация глазами одного человека: его роль и счётчики."""

    org: Org
    my_role: OrgRole
    member_count: int
    group_count: int
    project_count: int


@dataclass(frozen=True)
class AdminOrgSummary:
    """Организация в админке установки: роль смотрящего пуста, если админ в ней не состоит."""

    org: Org
    my_role: OrgRole | None
    member_count: int
    group_count: int
    project_count: int


@dataclass(frozen=True)
class MyOrgSummary:
    """Организация в «Настройки / Организации»: названия групп человека и признак единственного владельца."""

    summary: OrgSummary
    groups: tuple[str, ...]
    sole_owner: bool


@dataclass(frozen=True)
class Group:
    id: str
    org_id: str
    name: str
    created_at: datetime
    # Зарезервировано под синхронизацию групп из SSO; в этапе 2 не используется.
    external_ref: str | None = None


@dataclass(frozen=True)
class GroupSummary:
    group: Group
    member_count: int


@dataclass(frozen=True)
class GroupMemberView:
    user_id: str
    name: str
    email: str
    added_at: datetime
