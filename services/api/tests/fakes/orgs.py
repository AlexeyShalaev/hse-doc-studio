"""InMemory-реализации портов организаций и групп: те же правила, что у Postgres, без БД."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace

from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.normalize import normalize_email
from hse_doc_studio.core.listing import Found, Picked
from hse_doc_studio.core.orgs.entities import (
    GROUP_PREVIEW,
    ROLE_ORDER,
    AdminOrgSummary,
    Group,
    GroupMemberQuery,
    GroupMemberView,
    GroupPreview,
    GroupQuery,
    GroupSummary,
    MemberQuery,
    MemberRef,
    Org,
    OrgMember,
    OrgMemberView,
    OrgQuery,
    OrgRole,
    OrgSummary,
    UserOrgQuery,
    UserOrgView,
)

from tests.fakes.identity import InMemoryIdentityStore
from tests.fakes.listing import matches, ordered, page, picked


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
        owners = sum(1 for m in self._s.members.values() if m.org_id == org.id and m.role is OrgRole.owner)
        return AdminOrgSummary(org, role, base.member_count, base.group_count, base.project_count, owners)

    async def page_all(self, viewer_id: str, query: OrgQuery) -> Found[AdminOrgSummary]:
        found = [
            self._admin_summary(org, m.role if (m := self._s.members.get((org.id, viewer_id))) is not None else None)
            for org in self._s.orgs.values()
            if matches(query.q, org.name, org.slug)
        ]
        if query.mine is not None:
            found = [x for x in found if (x.my_role is not None) is query.mine]
        keys: dict[str, Callable[[AdminOrgSummary], object]] = {
            "name": lambda x: x.org.name.lower(),
            "slug": lambda x: x.org.slug,
            "member_count": lambda x: x.member_count,
            "project_count": lambda x: x.project_count,
        }
        return page(ordered(found, query.sort, keys, lambda x: x.org.id), query.window)

    async def pick(self, q: str | None, limit: int) -> Picked[Org]:
        found = [o for o in self._s.orgs.values() if matches(q, o.name, o.slug)]
        return picked(sorted(found, key=lambda o: (o.name.lower(), o.id)), limit)

    async def page_for_user(self, user_id: str, query: UserOrgQuery) -> Found[UserOrgView]:
        found = [
            UserOrgView(self._s.orgs[m.org_id], m.role, m.created_at)
            for m in self._s.members.values()
            if m.user_id == user_id
            and matches(query.q, self._s.orgs[m.org_id].name, self._s.orgs[m.org_id].slug)
            and (not query.roles or m.role in query.roles)
        ]
        keys: dict[str, Callable[[UserOrgView], object]] = {
            "name": lambda x: x.org.name.lower(),
            "role": lambda x: ROLE_ORDER.index(x.role),
            "joined_at": lambda x: x.joined_at,
        }
        return page(ordered(found, query.sort, keys, lambda x: x.org.id), query.window)

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

    def _member_matches(self, member: OrgMember, q: str | None) -> bool:
        user = self._s.users.users[member.user_id]
        return matches(q, user.name, user.email_normalized)

    async def page_members(self, org_id: str, query: MemberQuery) -> Found[OrgMemberView]:
        found = [
            OrgMemberView(m, self._s.users.users[m.user_id].name, self._s.users.users[m.user_id].email)
            for m in self._s.members.values()
            if m.org_id == org_id
            and self._member_matches(m, query.q)
            and (not query.roles or m.role in query.roles)
            and (query.not_in_group is None or (query.not_in_group, m.user_id) not in self._s.group_members)
        ]
        keys: dict[str, Callable[[OrgMemberView], object]] = {
            "name": lambda v: v.name.lower(),
            "email": lambda v: v.email.lower(),
            "role": lambda v: ROLE_ORDER.index(v.member.role),
            "joined_at": lambda v: v.member.created_at,
        }
        return page(ordered(found, query.sort, keys, lambda v: v.member.user_id), query.window)

    async def role_counts(self, org_id: str, q: str | None) -> dict[OrgRole, int]:
        found = [m for m in self._s.members.values() if m.org_id == org_id and self._member_matches(m, q)]
        return {role: sum(1 for m in found if m.role is role) for role in ROLE_ORDER}

    async def members_among(self, org_id: str, user_ids: list[str]) -> set[str]:
        return {uid for uid in user_ids if (org_id, uid) in self._s.members}

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

    def _preview(self, group: Group) -> GroupPreview:
        ids = [k[1] for k in self._s.group_members if k[0] == group.id]
        users = sorted((self._s.users.users[uid] for uid in ids), key=lambda u: (u.name.lower(), u.id))
        refs = tuple(MemberRef(u.id, u.name) for u in users[:GROUP_PREVIEW])
        return GroupPreview(group, len(ids), refs)

    async def page_for_org(self, org_id: str, query: GroupQuery) -> Found[GroupPreview]:
        found = [self._preview(g) for g in self._s.groups.values() if g.org_id == org_id and matches(query.q, g.name)]
        keys: dict[str, Callable[[GroupPreview], object]] = {
            "name": lambda p: p.group.name.lower(),
            "member_count": lambda p: p.member_count,
        }
        return page(ordered(found, query.sort, keys, lambda p: p.group.id), query.window)

    async def previews(self, group_ids: list[str]) -> dict[str, GroupPreview]:
        return {gid: self._preview(self._s.groups[gid]) for gid in group_ids if gid in self._s.groups}

    async def page_members(self, group_id: str, query: GroupMemberQuery) -> Found[GroupMemberView]:
        ticks = {k[1]: tick for k, tick in self._s.group_members.items() if k[0] == group_id}
        found = [v for v in await self.list_members(group_id) if matches(query.q, v.name, normalize_email(v.email))]
        keys: dict[str, Callable[[GroupMemberView], object]] = {
            "name": lambda v: v.name.lower(),
            "email": lambda v: v.email.lower(),
            "added_at": lambda v: ticks[v.user_id],
        }
        return page(ordered(found, query.sort, keys, lambda v: v.user_id), query.window)

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
