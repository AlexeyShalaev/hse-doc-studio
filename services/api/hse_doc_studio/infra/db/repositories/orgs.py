"""Postgres-репозитории организаций и групп."""

from __future__ import annotations

from typing import Any

from sqlalchemy import ColumnElement, Delete, Select, and_, case, delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
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
from hse_doc_studio.infra.db.listing import Expr, contains, contains_lower, fetch_page, ordering
from hse_doc_studio.infra.db.orm.identity import UserRow
from hse_doc_studio.infra.db.orm.orgs import GroupMemberRow, GroupRow, OrgMemberRow, OrgRow
from hse_doc_studio.infra.db.orm.projects import ProjectMemberRow, ProjectRow
from hse_doc_studio.infra.db.session import SessionProvider


def _org(row: OrgRow) -> Org:
    return Org(
        id=row.id,
        slug=row.slug,
        name=row.name,
        created_at=row.created_at,
        created_by=row.created_by,
        policies=dict(row.policies),
    )


def _member(row: OrgMemberRow) -> OrgMember:
    return OrgMember(org_id=row.org_id, user_id=row.user_id, role=OrgRole(row.role), created_at=row.created_at)


def _group(row: GroupRow) -> Group:
    return Group(id=row.id, org_id=row.org_id, name=row.name, created_at=row.created_at, external_ref=row.external_ref)


def _group_grants_of(group_ids: Select[Any]) -> Delete:
    """Роли групп на проектах: внешнего ключа на группу нет, запись убирается вместе с группой."""
    return delete(ProjectMemberRow).where(
        ProjectMemberRow.principal_kind == "group", ProjectMemberRow.principal_id.in_(group_ids)
    )


async def _counts(
    session: AsyncSession, ids: list[str]
) -> tuple[dict[str, int], dict[str, int], dict[str | None, int], dict[str, int]]:
    """Участники, группы, проекты и владельцы по организациям: по одному запросу на вид, а не на организацию."""
    found = (
        await session.execute(
            select(
                OrgMemberRow.org_id,
                func.count(),
                func.count().filter(OrgMemberRow.role == OrgRole.owner.value),
            )
            .where(OrgMemberRow.org_id.in_(ids))
            .group_by(OrgMemberRow.org_id)
        )
    ).all()
    members = {org_id: n for org_id, n, _ in found}
    owners = {org_id: n for org_id, _, n in found}
    groups = dict(
        (
            await session.execute(
                select(GroupRow.org_id, func.count()).where(GroupRow.org_id.in_(ids)).group_by(GroupRow.org_id)
            )
        ).all()
    )
    projects = dict(
        (
            await session.execute(
                select(ProjectRow.owner_org_id, func.count())
                .where(ProjectRow.owner_org_id.in_(ids))
                .group_by(ProjectRow.owner_org_id)
            )
        ).all()
    )
    return members, groups, projects, owners


async def _summaries(session: AsyncSession, pairs: list[tuple[OrgRow, str]]) -> list[OrgSummary]:
    """Счётчики одним запросом на вид: список «моих организаций» не растёт запросами вместе с числом организаций."""
    if not pairs:
        return []
    members, groups, projects, _ = await _counts(session, [org.id for org, _ in pairs])
    return [
        OrgSummary(
            org=_org(org),
            my_role=OrgRole(role),
            member_count=members.get(org.id, 0),
            group_count=groups.get(org.id, 0),
            project_count=projects.get(org.id, 0),
        )
        for org, role in pairs
    ]


async def _admin_summaries(session: AsyncSession, pairs: list[tuple[OrgRow, str | None]]) -> list[AdminOrgSummary]:
    if not pairs:
        return []
    members, groups, projects, owners = await _counts(session, [org.id for org, _ in pairs])
    return [
        AdminOrgSummary(
            org=_org(org),
            my_role=OrgRole(role) if role is not None else None,
            member_count=members.get(org.id, 0),
            group_count=groups.get(org.id, 0),
            project_count=projects.get(org.id, 0),
            owner_count=owners.get(org.id, 0),
        )
        for org, role in pairs
    ]


def _role_rank(role: Expr) -> ColumnElement[int]:
    """Старшая роль первой при сортировке по роли."""
    return case({r.value: i for i, r in enumerate(ROLE_ORDER)}, value=role, else_=len(ROLE_ORDER))


def _person_search(q: str) -> ColumnElement[bool]:
    # Те же выражения, что у списка людей: идут по индексам lower(name) и email_normalized.
    return contains_lower(q, func.lower(UserRow.name), UserRow.email_normalized)


# Счётчики для сортировки считаются подзапросом по строке организации, а не по всей установке.
_MEMBER_COUNT = select(func.count()).where(OrgMemberRow.org_id == OrgRow.id).correlate(OrgRow).scalar_subquery()
_PROJECT_COUNT = (
    select(func.count())
    .select_from(ProjectRow)
    .where(ProjectRow.owner_org_id == OrgRow.id)
    .correlate(OrgRow)
    .scalar_subquery()
)
_ORG_SORT: dict[str, Expr] = {
    "name": func.lower(OrgRow.name),
    "slug": OrgRow.slug,
    "member_count": _MEMBER_COUNT,
    "project_count": _PROJECT_COUNT,
}
_MEMBER_SORT: dict[str, Expr] = {
    "name": func.lower(UserRow.name),
    "email": UserRow.email_normalized,
    "role": _role_rank(OrgMemberRow.role),
    "joined_at": OrgMemberRow.created_at,
}
_USER_ORG_SORT: dict[str, Expr] = {
    "name": func.lower(OrgRow.name),
    "role": _role_rank(OrgMemberRow.role),
    "joined_at": OrgMemberRow.created_at,
}
_GROUP_MEMBER_COUNT = (
    select(func.count()).where(GroupMemberRow.group_id == GroupRow.id).correlate(GroupRow).scalar_subquery()
)
_GROUP_SORT: dict[str, Expr] = {
    "name": func.lower(GroupRow.name),
    "member_count": _GROUP_MEMBER_COUNT,
}
_GROUP_MEMBER_SORT: dict[str, Expr] = {
    "name": func.lower(UserRow.name),
    "email": UserRow.email_normalized,
    "added_at": GroupMemberRow.created_at,
}


async def _previews(session: AsyncSession, groups: list[GroupRow]) -> list[GroupPreview]:
    """Число участников и первые `GROUP_PREVIEW` по имени: два запроса на страницу, а не на группу."""
    ids = [g.id for g in groups]
    if not ids:
        return []
    counts = dict(
        (
            await session.execute(
                select(GroupMemberRow.group_id, func.count())
                .where(GroupMemberRow.group_id.in_(ids))
                .group_by(GroupMemberRow.group_id)
            )
        ).all()
    )
    ranked = (
        select(
            GroupMemberRow.group_id,
            GroupMemberRow.user_id,
            UserRow.name,
            func.row_number()
            .over(partition_by=GroupMemberRow.group_id, order_by=(func.lower(UserRow.name), GroupMemberRow.user_id))
            .label("n"),
        )
        .join(UserRow, UserRow.id == GroupMemberRow.user_id)
        .where(GroupMemberRow.group_id.in_(ids))
        .subquery()
    )
    first = (
        await session.execute(
            select(ranked.c.group_id, ranked.c.user_id, ranked.c.name)
            .where(ranked.c.n <= GROUP_PREVIEW)
            .order_by(ranked.c.group_id, ranked.c.n)
        )
    ).all()
    refs: dict[str, list[MemberRef]] = {}
    for group_id, user_id, name in first:
        refs.setdefault(group_id, []).append(MemberRef(user_id, name))
    return [GroupPreview(_group(g), counts.get(g.id, 0), tuple(refs.get(g.id, ()))) for g in groups]


class SqlOrgRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def add(self, org: Org) -> None:
        # ON CONFLICT вместо перехвата IntegrityError: ошибка не ломает внешнюю транзакцию
        stmt = (
            pg_insert(OrgRow)
            .values(
                id=org.id,
                slug=org.slug,
                name=org.name,
                policies=dict(org.policies),
                created_by=org.created_by,
                created_at=org.created_at,
            )
            .on_conflict_do_nothing(index_elements=[OrgRow.slug])
            .returning(OrgRow.id)
        )
        async with self._sessions.use() as session:
            if (await session.execute(stmt)).scalar_one_or_none() is None:
                raise IdentityError(IdentityErrorCode.slug_taken)

    async def get(self, org_id: str) -> Org | None:
        async with self._sessions.use() as session:
            row = await session.get(OrgRow, org_id)
            return _org(row) if row else None

    async def get_by_slug(self, slug: str) -> Org | None:
        async with self._sessions.use() as session:
            row = (await session.execute(select(OrgRow).where(OrgRow.slug == slug))).scalar_one_or_none()
            return _org(row) if row else None

    async def update(self, org: Org) -> None:
        async with self._sessions.use() as session:
            row = await session.get(OrgRow, org.id)
            if row is not None:
                row.name = org.name
                row.policies = dict(org.policies)
                await session.flush()

    async def delete(self, org_id: str) -> None:
        async with self._sessions.use() as session:
            group_ids = select(GroupRow.id).where(GroupRow.org_id == org_id)
            await session.execute(_group_grants_of(group_ids))
            await session.execute(delete(OrgRow).where(OrgRow.id == org_id))

    async def count_projects(self, org_id: str) -> int:
        async with self._sessions.use() as session:
            return (
                await session.execute(
                    select(func.count()).select_from(ProjectRow).where(ProjectRow.owner_org_id == org_id)
                )
            ).scalar_one()

    async def summary(self, org: Org, user_id: str) -> OrgSummary | None:
        async with self._sessions.use() as session:
            member = await session.get(OrgMemberRow, (org.id, user_id))
            if member is None:
                return None
            row = await session.get(OrgRow, org.id)
            return (await _summaries(session, [(row, member.role)]))[0] if row else None

    async def list_for_user(self, user_id: str) -> list[OrgSummary]:
        async with self._sessions.use() as session:
            found = (
                await session.execute(
                    select(OrgRow, OrgMemberRow.role)
                    .join(OrgMemberRow, OrgMemberRow.org_id == OrgRow.id)
                    .where(OrgMemberRow.user_id == user_id)
                    .order_by(func.lower(OrgRow.name), OrgRow.slug)
                )
            ).all()
            return await _summaries(session, [(org, role) for org, role in found])

    async def page_all(self, viewer_id: str, query: OrgQuery) -> Found[AdminOrgSummary]:
        stmt = select(OrgRow, OrgMemberRow.role).outerjoin(
            OrgMemberRow, and_(OrgMemberRow.org_id == OrgRow.id, OrgMemberRow.user_id == viewer_id)
        )
        if query.q:
            stmt = stmt.where(contains(query.q, OrgRow.name, OrgRow.slug))
        if query.mine is not None:
            stmt = stmt.where(OrgMemberRow.user_id.is_not(None) if query.mine else OrgMemberRow.user_id.is_(None))
        stmt = stmt.order_by(*ordering(query.sort, _ORG_SORT, OrgRow.id))
        async with self._sessions.use() as session:
            rows, total = await fetch_page(session, stmt, query.window)
            return Found(await _admin_summaries(session, [(org, role) for org, role in rows]), total)

    async def pick(self, q: str | None, limit: int) -> Picked[Org]:
        stmt = select(OrgRow)
        if q:
            stmt = stmt.where(contains(q, OrgRow.name, OrgRow.slug))
        stmt = stmt.order_by(func.lower(OrgRow.name), OrgRow.id).limit(limit + 1)
        async with self._sessions.use() as session:
            return Picked.of([_org(row) for row in (await session.execute(stmt)).scalars()], limit)

    async def page_for_user(self, user_id: str, query: UserOrgQuery) -> Found[UserOrgView]:
        stmt = (
            select(OrgRow, OrgMemberRow.role, OrgMemberRow.created_at)
            .join(OrgMemberRow, OrgMemberRow.org_id == OrgRow.id)
            .where(OrgMemberRow.user_id == user_id)
        )
        if query.q:
            stmt = stmt.where(contains(query.q, OrgRow.name, OrgRow.slug))
        if query.roles:
            stmt = stmt.where(OrgMemberRow.role.in_([r.value for r in query.roles]))
        stmt = stmt.order_by(*ordering(query.sort, _USER_ORG_SORT, OrgRow.id))
        async with self._sessions.use() as session:
            rows, total = await fetch_page(session, stmt, query.window)
            return Found([UserOrgView(_org(org), OrgRole(role), joined) for org, role, joined in rows], total)

    async def summary_for_admin(self, org: Org, viewer_id: str) -> AdminOrgSummary:
        async with self._sessions.use() as session:
            row = await session.get(OrgRow, org.id)
            role = await session.get(OrgMemberRow, (org.id, viewer_id))
            found = await _admin_summaries(session, [(row, role.role if role else None)]) if row else []
        if not found:
            raise IdentityError(IdentityErrorCode.not_found)
        return found[0]

    async def owner_counts(self, org_ids: list[str]) -> dict[str, int]:
        if not org_ids:
            return {}
        async with self._sessions.use() as session:
            rows = await session.execute(
                select(OrgMemberRow.org_id, func.count())
                .where(OrgMemberRow.org_id.in_(org_ids), OrgMemberRow.role == OrgRole.owner.value)
                .group_by(OrgMemberRow.org_id)
            )
            return dict(rows.all())

    async def get_member(self, org_id: str, user_id: str) -> OrgMember | None:
        async with self._sessions.use() as session:
            row = await session.get(OrgMemberRow, (org_id, user_id))
            return _member(row) if row else None

    async def list_members(self, org_id: str) -> list[OrgMemberView]:
        async with self._sessions.use() as session:
            found = (
                await session.execute(
                    select(OrgMemberRow, UserRow.name, UserRow.email)
                    .join(UserRow, UserRow.id == OrgMemberRow.user_id)
                    .where(OrgMemberRow.org_id == org_id)
                    .order_by(OrgMemberRow.created_at, OrgMemberRow.user_id)
                )
            ).all()
            return [OrgMemberView(_member(m), name, email) for m, name, email in found]

    async def page_members(self, org_id: str, query: MemberQuery) -> Found[OrgMemberView]:
        stmt = (
            select(OrgMemberRow, UserRow.name, UserRow.email)
            .join(UserRow, UserRow.id == OrgMemberRow.user_id)
            .where(OrgMemberRow.org_id == org_id)
        )
        if query.q:
            stmt = stmt.where(_person_search(query.q))
        if query.roles:
            stmt = stmt.where(OrgMemberRow.role.in_([r.value for r in query.roles]))
        if query.not_in_group is not None:
            stmt = stmt.where(
                OrgMemberRow.user_id.not_in(
                    select(GroupMemberRow.user_id).where(GroupMemberRow.group_id == query.not_in_group)
                )
            )
        stmt = stmt.order_by(*ordering(query.sort, _MEMBER_SORT, OrgMemberRow.user_id))
        async with self._sessions.use() as session:
            rows, total = await fetch_page(session, stmt, query.window)
            return Found([OrgMemberView(_member(m), name, email) for m, name, email in rows], total)

    async def role_counts(self, org_id: str, q: str | None) -> dict[OrgRole, int]:
        stmt = (
            select(OrgMemberRow.role, func.count())
            .join(UserRow, UserRow.id == OrgMemberRow.user_id)
            .where(OrgMemberRow.org_id == org_id)
            .group_by(OrgMemberRow.role)
        )
        if q:
            stmt = stmt.where(_person_search(q))
        async with self._sessions.use() as session:
            found = {OrgRole(role): n for role, n in (await session.execute(stmt)).all()}
        return {role: found.get(role, 0) for role in ROLE_ORDER}

    async def members_among(self, org_id: str, user_ids: list[str]) -> set[str]:
        if not user_ids:
            return set()
        async with self._sessions.use() as session:
            found = await session.execute(
                select(OrgMemberRow.user_id).where(OrgMemberRow.org_id == org_id, OrgMemberRow.user_id.in_(user_ids))
            )
            return set(found.scalars())

    async def add_member(self, member: OrgMember) -> None:
        stmt = (
            pg_insert(OrgMemberRow)
            .values(org_id=member.org_id, user_id=member.user_id, role=member.role.value, created_at=member.created_at)
            .on_conflict_do_nothing()
            .returning(OrgMemberRow.user_id)
        )
        async with self._sessions.use() as session:
            if (await session.execute(stmt)).scalar_one_or_none() is None:
                raise IdentityError(IdentityErrorCode.already_member)

    async def set_role(self, org_id: str, user_id: str, role: OrgRole) -> None:
        async with self._sessions.use() as session:
            row = await session.get(OrgMemberRow, (org_id, user_id))
            if row is not None:
                row.role = role.value
                await session.flush()

    async def remove_member(self, org_id: str, user_id: str) -> bool:
        async with self._sessions.use() as session:
            result = await session.execute(
                delete(OrgMemberRow)
                .where(OrgMemberRow.org_id == org_id, OrgMemberRow.user_id == user_id)
                .returning(OrgMemberRow.user_id)
            )
            return result.first() is not None

    async def lock_owners(self, org_id: str) -> list[str]:
        async with self._sessions.use() as session:
            rows = await session.execute(
                select(OrgMemberRow.user_id)
                .where(OrgMemberRow.org_id == org_id, OrgMemberRow.role == OrgRole.owner.value)
                .order_by(OrgMemberRow.user_id)
                .with_for_update()
            )
            return list(rows.scalars())


class SqlGroupRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def add(self, group: Group) -> None:
        stmt = (
            pg_insert(GroupRow)
            .values(
                id=group.id,
                org_id=group.org_id,
                name=group.name,
                external_ref=group.external_ref,
                created_at=group.created_at,
            )
            .on_conflict_do_nothing()
            .returning(GroupRow.id)
        )
        async with self._sessions.use() as session:
            if (await session.execute(stmt)).scalar_one_or_none() is None:
                raise IdentityError(IdentityErrorCode.name_taken)

    async def get(self, group_id: str) -> Group | None:
        async with self._sessions.use() as session:
            row = await session.get(GroupRow, group_id)
            return _group(row) if row else None

    async def list_for_org(self, org_id: str) -> list[GroupSummary]:
        async with self._sessions.use() as session:
            found = (
                await session.execute(
                    select(GroupRow, func.count(GroupMemberRow.user_id))
                    .outerjoin(GroupMemberRow, GroupMemberRow.group_id == GroupRow.id)
                    .where(GroupRow.org_id == org_id)
                    .group_by(GroupRow.id)
                    .order_by(func.lower(GroupRow.name), GroupRow.id)
                )
            ).all()
            return [GroupSummary(_group(g), count) for g, count in found]

    async def page_for_org(self, org_id: str, query: GroupQuery) -> Found[GroupPreview]:
        stmt = select(GroupRow).where(GroupRow.org_id == org_id)
        if query.q:
            # lower(name) рядом с org_id: то же выражение, что у индекса ux_groups_org_name_lower.
            stmt = stmt.where(contains(query.q, GroupRow.name))
        stmt = stmt.order_by(*ordering(query.sort, _GROUP_SORT, GroupRow.id))
        async with self._sessions.use() as session:
            rows, total = await fetch_page(session, stmt, query.window)
            groups = [row for (row,) in rows]
            return Found(await _previews(session, groups), total)

    async def previews(self, group_ids: list[str]) -> dict[str, GroupPreview]:
        if not group_ids:
            return {}
        async with self._sessions.use() as session:
            groups = (await session.execute(select(GroupRow).where(GroupRow.id.in_(group_ids)))).scalars().all()
            return {p.group.id: p for p in await _previews(session, list(groups))}

    async def page_members(self, group_id: str, query: GroupMemberQuery) -> Found[GroupMemberView]:
        stmt = (
            select(GroupMemberRow.user_id, UserRow.name, UserRow.email, GroupMemberRow.created_at)
            .join(UserRow, UserRow.id == GroupMemberRow.user_id)
            .where(GroupMemberRow.group_id == group_id)
        )
        if query.q:
            stmt = stmt.where(_person_search(query.q))
        stmt = stmt.order_by(*ordering(query.sort, _GROUP_MEMBER_SORT, GroupMemberRow.user_id))
        async with self._sessions.use() as session:
            rows, total = await fetch_page(session, stmt, query.window)
            return Found([GroupMemberView(*row) for row in rows], total)

    async def update(self, group: Group) -> None:
        async with self._sessions.use() as session:
            clash = (
                await session.execute(
                    select(GroupRow.id).where(
                        GroupRow.org_id == group.org_id,
                        func.lower(GroupRow.name) == group.name.lower(),
                        GroupRow.id != group.id,
                    )
                )
            ).first()
            if clash is not None:
                raise IdentityError(IdentityErrorCode.name_taken)
            row = await session.get(GroupRow, group.id)
            if row is not None:
                row.name = group.name
                await session.flush()

    async def delete(self, group_id: str) -> None:
        async with self._sessions.use() as session:
            await session.execute(_group_grants_of(select(GroupRow.id).where(GroupRow.id == group_id)))
            await session.execute(delete(GroupRow).where(GroupRow.id == group_id))

    async def list_members(self, group_id: str) -> list[GroupMemberView]:
        async with self._sessions.use() as session:
            found = (
                await session.execute(
                    select(GroupMemberRow.user_id, UserRow.name, UserRow.email, GroupMemberRow.created_at)
                    .join(UserRow, UserRow.id == GroupMemberRow.user_id)
                    .where(GroupMemberRow.group_id == group_id)
                    .order_by(GroupMemberRow.created_at, GroupMemberRow.user_id)
                )
            ).all()
            return [GroupMemberView(*row) for row in found]

    async def add_member(self, group_id: str, user_id: str) -> None:
        stmt = (
            pg_insert(GroupMemberRow)
            .values(group_id=group_id, user_id=user_id)
            .on_conflict_do_nothing()
            .returning(GroupMemberRow.user_id)
        )
        async with self._sessions.use() as session:
            if (await session.execute(stmt)).scalar_one_or_none() is None:
                raise IdentityError(IdentityErrorCode.already_member)

    async def remove_member(self, group_id: str, user_id: str) -> bool:
        async with self._sessions.use() as session:
            result = await session.execute(
                delete(GroupMemberRow)
                .where(GroupMemberRow.group_id == group_id, GroupMemberRow.user_id == user_id)
                .returning(GroupMemberRow.user_id)
            )
            return result.first() is not None

    async def names_for_user(self, user_id: str) -> dict[str, list[str]]:
        async with self._sessions.use() as session:
            found = (
                await session.execute(
                    select(GroupRow.org_id, GroupRow.name)
                    .join(GroupMemberRow, GroupMemberRow.group_id == GroupRow.id)
                    .where(GroupMemberRow.user_id == user_id)
                    .order_by(func.lower(GroupRow.name), GroupRow.id)
                )
            ).all()
        result: dict[str, list[str]] = {}
        for org_id, name in found:
            result.setdefault(org_id, []).append(name)
        return result

    async def remove_user_from_org_groups(self, org_id: str, user_id: str) -> int:
        async with self._sessions.use() as session:
            result = await session.execute(
                delete(GroupMemberRow)
                .where(
                    GroupMemberRow.user_id == user_id,
                    GroupMemberRow.group_id.in_(select(GroupRow.id).where(GroupRow.org_id == org_id)),
                )
                .returning(GroupMemberRow.group_id)
            )
            return len(result.all())
