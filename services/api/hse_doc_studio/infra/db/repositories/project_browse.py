"""Список проектов серверного режима по каталогу в Postgres."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from hse_doc_studio.core.access.entities import Actor, ActorKind
from hse_doc_studio.core.access.repositories import IProjectMemberships
from hse_doc_studio.core.checkpoint_deadlines import LIST_BUILT_SINCE, NextDeadline, project_next_deadline
from hse_doc_studio.core.listing import Found
from hse_doc_studio.core.projects.browse import ProjectBrowseQuery, ProjectCard
from hse_doc_studio.infra.db.listing import Expr, contains, fetch_page, ordering
from hse_doc_studio.infra.db.orm.identity import UserRow
from hse_doc_studio.infra.db.orm.orgs import OrgRow
from hse_doc_studio.infra.db.orm.projects import ProjectRow
from hse_doc_studio.infra.db.orm.sharing import ShareLinkGrantRow, ShareLinkRow
from hse_doc_studio.infra.db.orm.submission import SubmissionRow
from hse_doc_studio.infra.db.repositories.projects import visible_to
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.projects.catalog_sync import read_catalog_deadlines

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


def _via_link(user_id: str) -> ColumnElement[bool]:
    """Проект открыт человеку действующей ссылкой (ссылочное право, S3). Политику установки и организации
    проверяет загрузчик прав: строку без права страница не показывает."""
    return (
        select(ShareLinkGrantRow.link_id)
        .join(ShareLinkRow, ShareLinkRow.id == ShareLinkGrantRow.link_id)
        .where(
            ShareLinkGrantRow.project_id == ProjectRow.id,
            ShareLinkGrantRow.user_id == user_id,
            ShareLinkRow.revoked_at.is_(None),
            or_(ShareLinkRow.expires_at.is_(None), ShareLinkRow.expires_at > func.now()),
        )
        .exists()
    )


def _conditions(query: ProjectBrowseQuery, user_id: str) -> list[ColumnElement[bool]]:
    visible = or_(visible_to(user_id), _via_link(user_id))
    conditions = [ProjectRow.deleted_at.is_(None), visible, *_owner_filter(query, user_id)]
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
        now = datetime.now(UTC)
        async with self._sessions.use() as session:
            found, total = await fetch_page(session, stmt, query.window)
            rows = [row for (row,) in found]
            deadlines = await _next_deadlines(session, rows, now)
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
                via_link=roles[r.id].via_link,
                updated_at=r.updated_at,
                pinned=r.pinned,
                archived=r.archived_at is not None,
                shared_enabled=r.shared_enabled,
                next_deadline=deadlines.get(r.id),
            )
            for r in rows
            # Права отозвали между запросами: строку не показываем, как и раньше.
            if r.id in roles
        ]
        return Found(cards, total)


async def _next_deadlines(session: AsyncSession, rows: Sequence[ProjectRow], now: datetime) -> dict[UUID, NextDeadline]:
    """Ближайший срок точки у строк страницы (signing-route.md, 16.6): сроки из копии в каталоге, «просрочено» по
    записям сдачи за последние `LIST_BUILT_SINCE`. Строки без сроков базу второй раз не трогают."""
    copies = {row.id: read_catalog_deadlines(row.deadlines) for row in rows if row.deadlines}
    if not copies:
        return {}
    stmt = select(SubmissionRow.project_id, SubmissionRow.profile_id, SubmissionRow.created_at).where(
        SubmissionRow.project_id.in_(list(copies)), SubmissionRow.created_at >= now - LIST_BUILT_SINCE
    )
    built: dict[UUID, dict[str, list[datetime]]] = {}
    for project_id, profile_id, created_at in (await session.execute(stmt)).all():
        built.setdefault(project_id, {}).setdefault(profile_id, []).append(created_at)
    result: dict[UUID, NextDeadline] = {}
    for project_id, (deadlines, names) in copies.items():
        found = project_next_deadline(deadlines, names, built.get(project_id, {}), now=now)
        if found is not None:
            result[project_id] = found
    return result
