"""Студия шаблонов на Postgres: рабочие пространства владельца, право «Автор шаблонов», включение раздела."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import delete, exists, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert

from hse_doc_studio.core.identity.protocols import IInstanceSettingsRepository
from hse_doc_studio.core.pack_studio.entities import (
    GrantSubjectKind,
    PackStudioGrant,
    PackWorkspace,
    WorkspaceError,
    WorkspaceKind,
    WorkspaceState,
)
from hse_doc_studio.core.settings_scope import SOURCE_ADMIN
from hse_doc_studio.infra.db.orm.identity import UserRow
from hse_doc_studio.infra.db.orm.orgs import GroupMemberRow, GroupRow, OrgRow
from hse_doc_studio.infra.db.orm.pack_studio import PackStudioGrantRow, PackWorkspaceRow
from hse_doc_studio.infra.db.session import SessionProvider

SECTION_KEY = "pack_studio.enabled"


def _entity(row: PackWorkspaceRow) -> PackWorkspace:
    return PackWorkspace(
        id=row.id,
        owner_id=row.owner_id,
        kind=WorkspaceKind(row.kind),
        label=row.label,
        packs_path=row.packs_path,
        created_at=row.created_at,
        updated_at=row.updated_at,
        state=WorkspaceState(row.state),
        remote_url=row.remote_url,
        credential_id=row.credential_id,
        insecure_http=row.insecure_http,
        base_branch=row.base_branch,
        base_sha=row.base_sha,
        fetched_at=row.fetched_at,
        work_branch=row.work_branch,
        pr_url=row.pr_url,
        pr_number=row.pr_number,
        ci_status=row.ci_status,
        folder=row.folder,
        error=WorkspaceError(row.error_code, row.error_detail or "") if row.error_code else None,
    )


def _values(ws: PackWorkspace) -> dict[str, Any]:
    return {
        "kind": ws.kind.value,
        "label": ws.label,
        "packs_path": ws.packs_path,
        "state": ws.state.value,
        "remote_url": ws.remote_url,
        "credential_id": ws.credential_id,
        "insecure_http": ws.insecure_http,
        "base_branch": ws.base_branch,
        "base_sha": ws.base_sha,
        "fetched_at": ws.fetched_at,
        "work_branch": ws.work_branch,
        "pr_url": ws.pr_url,
        "pr_number": ws.pr_number,
        "ci_status": ws.ci_status,
        "folder": ws.folder,
        "error_code": ws.error.code if ws.error else None,
        "error_detail": ws.error.detail if ws.error else None,
        "updated_at": ws.updated_at,
    }


def _owned(owner_id: str | None) -> Any:
    # Без владельца на сервере строк нет: актор без id ничего не видит.
    return PackWorkspaceRow.owner_id == (owner_id or "")


class PostgresPackWorkspaceRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def list(self, owner_id: str | None) -> list[PackWorkspace]:
        stmt = (
            select(PackWorkspaceRow).where(_owned(owner_id)).order_by(PackWorkspaceRow.created_at, PackWorkspaceRow.id)
        )
        async with self._sessions.use() as db:
            return [_entity(row) for row in (await db.execute(stmt)).scalars().all()]

    async def get(self, workspace_id: UUID, owner_id: str | None) -> PackWorkspace | None:
        stmt = select(PackWorkspaceRow).where(PackWorkspaceRow.id == workspace_id, _owned(owner_id))
        async with self._sessions.use() as db:
            row = (await db.execute(stmt)).scalar_one_or_none()
        return None if row is None else _entity(row)

    async def count(self, owner_id: str | None) -> int:
        stmt = select(func.count()).select_from(PackWorkspaceRow).where(_owned(owner_id))
        async with self._sessions.use() as db:
            return int((await db.execute(stmt)).scalar_one())

    async def add(self, workspace: PackWorkspace) -> None:
        if workspace.owner_id is None:
            raise ValueError("a server workspace needs an owner")
        async with self._sessions.use() as db:
            db.add(
                PackWorkspaceRow(
                    id=workspace.id, owner_id=workspace.owner_id, created_at=workspace.created_at, **_values(workspace)
                )
            )
            await db.flush()

    async def update(self, workspace: PackWorkspace) -> None:
        stmt = update(PackWorkspaceRow).where(PackWorkspaceRow.id == workspace.id).values(**_values(workspace))
        async with self._sessions.use() as db:
            await db.execute(stmt)

    async def delete(self, workspace_id: UUID, owner_id: str | None) -> bool:
        stmt = delete(PackWorkspaceRow).where(PackWorkspaceRow.id == workspace_id, _owned(owner_id))
        async with self._sessions.use() as db:
            result = await db.execute(stmt)
        return bool(getattr(result, "rowcount", 0))


class PostgresPackStudioGrantRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def has_grant(self, user_id: str) -> bool:
        in_group = select(GroupMemberRow.group_id).where(GroupMemberRow.user_id == user_id)
        stmt = select(
            exists().where(or_(PackStudioGrantRow.user_id == user_id, PackStudioGrantRow.group_id.in_(in_group)))
        )
        async with self._sessions.use() as db:
            return bool((await db.execute(stmt)).scalar_one())

    async def list(self) -> list[PackStudioGrant]:
        stmt = (
            select(PackStudioGrantRow, UserRow.name, UserRow.email, GroupRow.name, OrgRow.slug, OrgRow.name)
            .outerjoin(UserRow, UserRow.id == PackStudioGrantRow.user_id)
            .outerjoin(GroupRow, GroupRow.id == PackStudioGrantRow.group_id)
            .outerjoin(OrgRow, OrgRow.id == GroupRow.org_id)
            .order_by(PackStudioGrantRow.created_at, PackStudioGrantRow.id)
        )
        async with self._sessions.use() as db:
            rows = (await db.execute(stmt)).all()
        return [
            _grant(row, user_name, email, group_name, org_slug, org_name)
            for row, user_name, email, group_name, org_slug, org_name in rows
        ]

    async def subject_exists(self, kind: GrantSubjectKind, subject_id: str) -> bool:
        table = UserRow if kind is GrantSubjectKind.user else GroupRow
        stmt = select(exists().where(table.id == subject_id))
        async with self._sessions.use() as db:
            return bool((await db.execute(stmt)).scalar_one())

    async def add(self, grant: PackStudioGrant) -> bool:
        user_id = grant.subject_id if grant.subject is GrantSubjectKind.user else None
        group_id = grant.subject_id if grant.subject is GrantSubjectKind.group else None
        stmt = (
            insert(PackStudioGrantRow)
            .values(
                id=grant.id,
                user_id=user_id,
                group_id=group_id,
                granted_by=grant.granted_by,
                created_at=grant.created_at,
            )
            .on_conflict_do_nothing()
            .returning(PackStudioGrantRow.id)
        )
        async with self._sessions.use() as db:
            return (await db.execute(stmt)).scalar_one_or_none() is not None

    async def remove(self, grant_id: UUID) -> PackStudioGrant | None:
        found = next((grant for grant in await self.list() if grant.id == grant_id), None)
        if found is None:
            return None
        async with self._sessions.use() as db:
            await db.execute(delete(PackStudioGrantRow).where(PackStudioGrantRow.id == grant_id))
        return found


def _grant(
    row: PackStudioGrantRow,
    user_name: str | None,
    email: str | None,
    group_name: str | None,
    org_slug: str | None,
    org_name: str | None,
) -> PackStudioGrant:
    if row.user_id is not None:
        return PackStudioGrant(
            id=row.id,
            subject=GrantSubjectKind.user,
            subject_id=row.user_id,
            created_at=row.created_at,
            granted_by=row.granted_by,
            name=user_name,
            email=email,
        )
    return PackStudioGrant(
        id=row.id,
        subject=GrantSubjectKind.group,
        subject_id=row.group_id or "",
        created_at=row.created_at,
        granted_by=row.granted_by,
        name=group_name,
        org_slug=org_slug,
        org_name=org_name,
    )


class InstanceSectionStore:
    """Включение раздела на сервере: ключ `pack_studio.enabled` в настройках установки, источник «админ»."""

    def __init__(self, settings: IInstanceSettingsRepository) -> None:
        self._settings = settings

    async def get(self) -> bool | None:
        value = (await self._settings.get_all()).get(SECTION_KEY)
        return value if isinstance(value, bool) else None

    async def set(self, enabled: bool) -> None:
        await self._settings.set(SECTION_KEY, enabled, source=SOURCE_ADMIN)
