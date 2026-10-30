"""Сущности организаций и групп. Роли организации читает загрузчик прав проекта; сама `policy.py` их не знает."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from hse_doc_studio.core.listing import SortKey, Window

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
    """Организация в админке установки: роль смотрящего пуста, если админ в ней не состоит.

    `owner_count` нужен экрану участников: последнего владельца понизить или убрать нельзя.
    """

    org: Org
    my_role: OrgRole | None
    member_count: int
    group_count: int
    project_count: int
    owner_count: int = 0


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


ORG_SORTS = ("name", "slug", "member_count", "project_count")
MEMBER_SORTS = ("name", "email", "role", "joined_at")
USER_ORG_SORTS = ("name", "role", "joined_at")
GROUP_SORTS = ("name", "member_count")
GROUP_MEMBER_SORTS = ("name", "email", "added_at")
# Порядок ролей при сортировке по роли: старшая первой.
ROLE_ORDER = (OrgRole.owner, OrgRole.admin, OrgRole.member)
GROUP_PREVIEW = 5


@dataclass(frozen=True)
class OrgQuery:
    """Список организаций админки. `mine`: только те, где смотрящий админ сам участник (False: где не участник)."""

    q: str | None = None
    mine: bool | None = None
    sort: SortKey = field(default_factory=lambda: SortKey("name"))
    window: Window = field(default_factory=Window)


@dataclass(frozen=True)
class MemberQuery:
    """Участники организации: поиск по имени и почте, фильтр ролей (любая из перечисленных)."""

    q: str | None = None
    roles: tuple[OrgRole, ...] = ()
    sort: SortKey = field(default_factory=lambda: SortKey("joined_at"))
    window: Window = field(default_factory=Window)


@dataclass(frozen=True)
class UserOrgQuery:
    """Организации одного человека: поиск по названию и адресу, фильтр ролей."""

    q: str | None = None
    roles: tuple[OrgRole, ...] = ()
    sort: SortKey = field(default_factory=lambda: SortKey("name"))
    window: Window = field(default_factory=Window)


@dataclass(frozen=True)
class UserOrgView:
    """Организация в карточке человека: его роль и когда вступил."""

    org: Org
    role: OrgRole
    joined_at: datetime


@dataclass(frozen=True)
class GroupQuery:
    q: str | None = None
    sort: SortKey = field(default_factory=lambda: SortKey("name"))
    window: Window = field(default_factory=Window)


@dataclass(frozen=True)
class GroupMemberQuery:
    q: str | None = None
    sort: SortKey = field(default_factory=lambda: SortKey("name"))
    window: Window = field(default_factory=Window)


@dataclass(frozen=True)
class MemberRef:
    user_id: str
    name: str


@dataclass(frozen=True)
class GroupPreview:
    """Группа в списке админки: число участников и первые из них по имени вместо полного состава."""

    group: Group
    member_count: int
    preview: tuple[MemberRef, ...]
