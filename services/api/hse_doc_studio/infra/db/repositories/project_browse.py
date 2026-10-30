"""Список проектов серверного режима по каталогу в Postgres."""

from __future__ import annotations

from sqlalchemy import ColumnElement, func, or_, select

from hse_doc_studio.core.access.entities import Actor, ActorKind
from hse_doc_studio.core.access.repositories import IProjectMemberships
from hse_doc_studio.core.listing import Found
from hse_doc_studio.core.projects.browse import ProjectBrowseQuery, ProjectCard
from hse_doc_studio.infra.db.listing import Expr, contains, fetch_page, ordering
from hse_doc_studio.infra.db.orm.identity import UserRow
from hse_doc_studio.infra.db.orm.orgs import OrgRow
from hse_doc_studio.infra.db.orm.projects import ProjectRow
from hse_doc_studio.infra.db.repositories.projects import visible_to
from hse_doc_studio.infra.db.session import SessionProvider

_SORT: dict[str, Expr] = {
    "name": func.lower(ProjectRow.name),
    "updated_at": ProjectRow.updated_at,
    "created_at": ProjectRow.created_at,
}


def _owner_filter(query: ProjectBrowseQuery, user_id: str) -> list[ColumnElement[bool]]:
    if query.owner == "me":
        return [ProjectRow.owner_user_id == user_id]
    if query.owner == "org":
        return [ProjectRow.owner_org_id.is_not(None)]
    if query.owner == "shared":
        return [ProjectRow.owner_org_id.is_(None), ProjectRow.owner_user_id != user_id]
    return []


def _conditions(query: ProjectBrowseQuery, user_id: str) -> list[ColumnElement[bool]]:
    conditions = [ProjectRow.deleted_at.is_(None), visible_to(user_id), *_owner_filter(query, user_id)]
    if query.archived is not None:
        conditions.append(ProjectRow.archived_at.is_not(None) if query.archived else ProjectRow.archived_at.is_(None))
    if query.pinned is not None:
        conditions.append(ProjectRow.pinned.is_(query.pinned))
    if query.org_slug is not None:
        conditions.append(ProjectRow.owner_org_id.in_(select(OrgRow.id).where(OrgRow.slug == query.org_slug)))
    if query.q:
        owner_user = select(UserRow.name).where(UserRow.id == ProjectRow.owner_user_id).scalar_subquery()
        owner_org = select(OrgRow.name).where(OrgRow.id == ProjectRow.owner_org_id).scalar_subquery()
        conditions.append(
            or_(
                contains(query.q, ProjectRow.name, ProjectRow.supervisor_name), contains(query.q, owner_user, owner_org)
            )
        )
    return conditions


class PostgresProjectBrowser:
    """Страница проектов, видимых актору: фильтры и порядок в SQL, владелец и роль только для строк страницы."""

    def __init__(self, sessions: SessionProvider, memberships: IProjectMemberships) -> None:
        self._sessions = sessions
        self._memberships = memberships

    async def page(self, actor: Actor, query: ProjectBrowseQuery) -> Found[ProjectCard]:
        if actor.kind is not ActorKind.user or actor.id is None:
            return Found([], 0)
        stmt = (
            select(ProjectRow)
            .where(*_conditions(query, actor.id))
            .order_by(*ordering(query.sort, _SORT, ProjectRow.id))
        )
        async with self._sessions.use() as session:
            found, total = await fetch_page(session, stmt, query.window)
            rows = [row for (row,) in found]
        roles = await self._memberships.memberships_for(actor, [r.id for r in rows])
        cards = [
            ProjectCard(
                id=r.id,
                name=r.name,
                kind=r.kind,
                staffing="team" if r.team else "solo",
                lang=r.lang,
                owner=roles[r.id].owner,
                my_role=roles[r.id].my_role,
                updated_at=r.updated_at,
                pinned=r.pinned,
                archived=r.archived_at is not None,
                shared_enabled=r.shared_enabled,
            )
            for r in rows
            # Права отозвали между запросами: строку не показываем, как и раньше.
            if r.id in roles
        ]
        return Found(cards, total)
