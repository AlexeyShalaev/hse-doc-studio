"""InMemory-реализации портов организаций и групп: те же правила, что у Postgres, без БД."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.orgs.entities import (
    AdminOrgSummary,
    Group,
    GroupMemberView,
    GroupSummary,
    Org,
    OrgMember,
    OrgMemberView,
    OrgRole,
    OrgSummary,
)

from tests.fakes.identity import InMemoryIdentityStore


@dataclass
class InMemoryOrgStore:
    users: InMemoryIdentityStore
    orgs: dict[str, Org] = field(default_factory=dict)
    members: dict[tuple[str, str], OrgMember] = field(default_factory=dict)
    groups: dict[str, Group] = field(default_factory=dict)
    group_members: dict[tuple[str, str], int] = field(default_factory=dict)
    # org_id -> число проектов; тест задаёт его сам
    projects: dict[str, int] = field(default_factory=dict)
    clock: int = 0

    def tick(self) -> int:
        self.clock += 1
        return self.clock


class InMemoryOrgRepository:
    def __init__(self, store: InMemoryOrgStore) -> None:
        self._s = store

    async def add(self, org: Org) -> None:
        if any(o.slug == org.slug for o in self._s.orgs.values()):
            raise IdentityError(IdentityErrorCode.slug_taken)
        self._s.orgs[org.id] = org

    async def get(self, org_id: str) -> Org | None:
        return self._s.orgs.get(org_id)

    async def get_by_slug(self, slug: str) -> Org | None:
        return next((o for o in self._s.orgs.values() if o.slug == slug), None)

    async def update(self, org: Org) -> None:
        self._s.orgs[org.id] = org

    async def delete(self, org_id: str) -> None:
        self._s.orgs.pop(org_id, None)
        for key in [k for k in self._s.members if k[0] == org_id]:
            del self._s.members[key]
        for group in [g for g in self._s.groups.values() if g.org_id == org_id]:
            del self._s.groups[group.id]
            for key in [k for k in self._s.group_members if k[0] == group.id]:
                del self._s.group_members[key]

    async def count_projects(self, org_id: str) -> int:
        return self._s.projects.get(org_id, 0)

    def _summary(self, org: Org, role: OrgRole) -> OrgSummary:
        return OrgSummary(
            org=org,
            my_role=role,
            member_count=sum(1 for k in self._s.members if k[0] == org.id),
            group_count=sum(1 for g in self._s.groups.values() if g.org_id == org.id),
            project_count=self._s.projects.get(org.id, 0),
        )

    async def summary(self, org: Org, user_id: str) -> OrgSummary | None:
        member = self._s.members.get((org.id, user_id))
        return self._summary(org, member.role) if member else None

    async def list_for_user(self, user_id: str) -> list[OrgSummary]:
        found = [
            self._summary(self._s.orgs[m.org_id], m.role) for m in self._s.members.values() if m.user_id == user_id
        ]
        return sorted(found, key=lambda x: (x.org.name.lower(), x.org.slug))

    def _admin_summary(self, org: Org, role: OrgRole | None) -> AdminOrgSummary:
        base = self._summary(org, role or OrgRole.member)
        return AdminOrgSummary(org, role, base.member_count, base.group_count, base.project_count)

    async def list_all(self, viewer_id: str) -> list[AdminOrgSummary]:
        found = [
            self._admin_summary(org, m.role if (m := self._s.members.get((org.id, viewer_id))) is not None else None)
            for org in self._s.orgs.values()
        ]
        return sorted(found, key=lambda x: (x.org.name.lower(), x.org.slug))

    async def summary_for_admin(self, org: Org, viewer_id: str) -> AdminOrgSummary:
        member = self._s.members.get((org.id, viewer_id))
        return self._admin_summary(org, member.role if member else None)

    async def owner_counts(self, org_ids: list[str]) -> dict[str, int]:
        return {
            org_id: n
            for org_id in org_ids
            if (n := sum(1 for m in self._s.members.values() if m.org_id == org_id and m.role is OrgRole.owner))
        }

    async def get_member(self, org_id: str, user_id: str) -> OrgMember | None:
        return self._s.members.get((org_id, user_id))

    async def list_members(self, org_id: str) -> list[OrgMemberView]:
        found = sorted((m for m in self._s.members.values() if m.org_id == org_id), key=lambda m: self._order(m))
        return [
            OrgMemberView(m, self._s.users.users[m.user_id].name, self._s.users.users[m.user_id].email) for m in found
        ]

    def _order(self, member: OrgMember) -> tuple[object, str]:
        return (member.created_at, member.user_id)

    async def add_member(self, member: OrgMember) -> None:
        if (member.org_id, member.user_id) in self._s.members:
            raise IdentityError(IdentityErrorCode.already_member)
        self._s.members[(member.org_id, member.user_id)] = member

    async def set_role(self, org_id: str, user_id: str, role: OrgRole) -> None:
        self._s.members[(org_id, user_id)] = replace(self._s.members[(org_id, user_id)], role=role)

    async def remove_member(self, org_id: str, user_id: str) -> bool:
        return self._s.members.pop((org_id, user_id), None) is not None

    async def lock_owners(self, org_id: str) -> list[str]:
        return sorted(m.user_id for m in self._s.members.values() if m.org_id == org_id and m.role is OrgRole.owner)


class InMemoryGroupRepository:
    def __init__(self, store: InMemoryOrgStore) -> None:
        self._s = store

    def _name_taken(self, org_id: str, name: str, *, except_id: str | None = None) -> bool:
        return any(
            g.org_id == org_id and g.name.lower() == name.lower() and g.id != except_id for g in self._s.groups.values()
        )

    async def add(self, group: Group) -> None:
        if self._name_taken(group.org_id, group.name):
            raise IdentityError(IdentityErrorCode.name_taken)
        self._s.groups[group.id] = group

    async def get(self, group_id: str) -> Group | None:
        return self._s.groups.get(group_id)

    async def list_for_org(self, org_id: str) -> list[GroupSummary]:
        found = [g for g in self._s.groups.values() if g.org_id == org_id]
        return [
            GroupSummary(g, sum(1 for k in self._s.group_members if k[0] == g.id))
            for g in sorted(found, key=lambda g: (g.name.lower(), g.id))
        ]

    async def update(self, group: Group) -> None:
        if self._name_taken(group.org_id, group.name, except_id=group.id):
            raise IdentityError(IdentityErrorCode.name_taken)
        self._s.groups[group.id] = group

    async def delete(self, group_id: str) -> None:
        self._s.groups.pop(group_id, None)
        for key in [k for k in self._s.group_members if k[0] == group_id]:
            del self._s.group_members[key]

    async def list_members(self, group_id: str) -> list[GroupMemberView]:
        keys = sorted((k for k in self._s.group_members if k[0] == group_id), key=lambda k: self._s.group_members[k])
        return [
            GroupMemberView(
                user_id=k[1],
                name=self._s.users.users[k[1]].name,
                email=self._s.users.users[k[1]].email,
                added_at=self._s.users.users[k[1]].created_at,
            )
            for k in keys
        ]

    async def add_member(self, group_id: str, user_id: str) -> None:
        if (group_id, user_id) in self._s.group_members:
            raise IdentityError(IdentityErrorCode.already_member)
        self._s.group_members[(group_id, user_id)] = self._s.tick()

    async def remove_member(self, group_id: str, user_id: str) -> bool:
        return self._s.group_members.pop((group_id, user_id), None) is not None

    async def member_ids_by_org(self, org_id: str) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {g.id: [] for g in self._s.groups.values() if g.org_id == org_id}
        for (group_id, user_id), _ in sorted(self._s.group_members.items(), key=lambda kv: kv[1]):
            if group_id in result:
                result[group_id].append(user_id)
        return result

    async def names_for_user(self, user_id: str) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for (group_id, uid), _ in self._s.group_members.items():
            if uid == user_id:
                group = self._s.groups[group_id]
                result.setdefault(group.org_id, []).append(group.name)
        return {k: sorted(v, key=str.lower) for k, v in result.items()}

    async def remove_user_from_org_groups(self, org_id: str, user_id: str) -> int:
        doomed = [k for k in self._s.group_members if k[1] == user_id and self._s.groups[k[0]].org_id == org_id]
        for key in doomed:
            del self._s.group_members[key]
        return len(doomed)
