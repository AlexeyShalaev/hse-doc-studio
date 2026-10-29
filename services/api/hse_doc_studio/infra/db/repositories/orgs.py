"""Postgres-репозитории организаций и групп."""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.orgs.entities import (
    Group,
    GroupMemberView,
    GroupSummary,
    Org,
    OrgMember,
    OrgMemberView,
    OrgRole,
    OrgSummary,
)
from hse_doc_studio.infra.db.orm.identity import UserRow
from hse_doc_studio.infra.db.orm.orgs import GroupMemberRow, GroupRow, OrgMemberRow, OrgRow
from hse_doc_studio.infra.db.orm.projects import ProjectRow
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


async def _summaries(session: AsyncSession, pairs: list[tuple[OrgRow, str]]) -> list[OrgSummary]:
    """Счётчики одним запросом на вид: список «моих организаций» не растёт запросами вместе с числом организаций."""
    if not pairs:
        return []
    ids = [org.id for org, _ in pairs]
    members = dict(
        (
            await session.execute(
                select(OrgMemberRow.org_id, func.count())
                .where(OrgMemberRow.org_id.in_(ids))
                .group_by(OrgMemberRow.org_id)
            )
        ).all()
    )
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
