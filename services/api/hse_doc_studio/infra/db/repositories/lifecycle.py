"""Postgres-реализация жизненного цикла данных человека: блокеры удаления, стирание, выгрузка."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, exists, func, or_, select, update
from sqlalchemy.orm import aliased

from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.lifecycle import DeletionBlockers, ErasureReport
from hse_doc_studio.infra.db.orm import (
    ApiTokenRow,
    AuditLogRow,
    GroupMemberRow,
    GroupRow,
    MailOutboxRow,
    OrgMemberRow,
    OrgRow,
    ProjectMemberRow,
    ProjectRow,
    RunnerRegistrationTokenRow,
    RunnerRow,
    SessionRow,
    UserIdentityRow,
    UserRow,
    UserSettingRow,
)
from hse_doc_studio.infra.db.session import SessionProvider

_AUDIT_EXPORT_LIMIT = 5000


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value is not None else None


class SqlUserLifecycle:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def blockers(self, user_id: str) -> DeletionBlockers:
        peer = aliased(OrgMemberRow)
        other_owner = exists().where(peer.org_id == OrgMemberRow.org_id, peer.role == "owner", peer.user_id != user_id)
        async with self._sessions.use() as db:
            projects = (
                await db.execute(
                    select(func.count()).select_from(ProjectRow).where(ProjectRow.owner_user_id == user_id)
                )
            ).scalar_one()
            sole = (
                select(func.count())
                .select_from(OrgMemberRow)
                .where(OrgMemberRow.user_id == user_id, OrgMemberRow.role == "owner", ~other_owner)
            )
            orgs = (await db.execute(sole)).scalar_one()
        return DeletionBlockers(projects=int(projects), orgs=int(orgs))

    async def erase(self, user_id: str, pseudonym: str) -> ErasureReport:
        async with self._sessions.use() as db:
            email = (
                await db.execute(select(UserRow.email_normalized, UserRow.email).where(UserRow.id == user_id))
            ).first()
            if email is None:
                raise IdentityError(IdentityErrorCode.not_found)
            anonymized = int((await db.execute(select(func.audit_log_anonymize(user_id, pseudonym)))).scalar_one())
            tokens = (
                await db.execute(select(func.count()).select_from(ApiTokenRow).where(ApiTokenRow.user_id == user_id))
            ).scalar_one()
            sessions = (
                await db.execute(select(func.count()).select_from(SessionRow).where(SessionRow.user_id == user_id))
            ).scalar_one()
            settings = (
                await db.execute(
                    select(func.count()).select_from(UserSettingRow).where(UserSettingRow.user_id == user_id)
                )
            ).scalar_one()
            await db.execute(
                delete(ProjectMemberRow).where(
                    ProjectMemberRow.principal_kind == "user", ProjectMemberRow.principal_id == user_id
                )
            )
            await db.execute(delete(MailOutboxRow).where(MailOutboxRow.to_email.in_({email[0], email[1]})))
            await db.execute(update(RunnerRow).where(RunnerRow.created_by == user_id).values(created_by=None))
            await db.execute(
                update(RunnerRegistrationTokenRow)
                .where(RunnerRegistrationTokenRow.created_by == user_id)
                .values(created_by=None)
            )
            # Остальное уходит каскадом по внешним ключам на users.id (тест архитектуры следит, что их не забыли).
            await db.execute(delete(UserRow).where(UserRow.id == user_id))
        return ErasureReport(
            audit_anonymized=anonymized, api_tokens=int(tokens), sessions=int(sessions), settings=int(settings)
        )

    async def export(self, user_id: str) -> Mapping[str, object]:
        async with self._sessions.use() as db:
            user = (await db.execute(select(UserRow).where(UserRow.id == user_id))).scalar_one_or_none()
            if user is None:
                raise IdentityError(IdentityErrorCode.not_found)
            identities = (await db.execute(select(UserIdentityRow).where(UserIdentityRow.user_id == user_id))).scalars()
            tokens = (
                await db.execute(
                    select(ApiTokenRow).where(ApiTokenRow.user_id == user_id).order_by(ApiTokenRow.created_at)
                )
            ).scalars()
            sessions = (
                await db.execute(
                    select(SessionRow).where(SessionRow.user_id == user_id).order_by(SessionRow.created_at)
                )
            ).scalars()
            settings = (await db.execute(select(UserSettingRow).where(UserSettingRow.user_id == user_id))).scalars()
            orgs = (
                await db.execute(
                    select(OrgRow.slug, OrgRow.name, OrgMemberRow.role)
                    .join(OrgMemberRow, OrgMemberRow.org_id == OrgRow.id)
                    .where(OrgMemberRow.user_id == user_id)
                    .order_by(OrgRow.slug)
                )
            ).all()
            groups = (
                await db.execute(
                    select(OrgRow.slug, GroupRow.name)
                    .join(GroupRow, GroupRow.org_id == OrgRow.id)
                    .join(GroupMemberRow, GroupMemberRow.group_id == GroupRow.id)
                    .where(GroupMemberRow.user_id == user_id)
                    .order_by(OrgRow.slug, GroupRow.name)
                )
            ).all()
            owned = (
                await db.execute(
                    select(ProjectRow).where(ProjectRow.owner_user_id == user_id).order_by(ProjectRow.created_at)
                )
            ).scalars()
            shared = (
                await db.execute(
                    select(ProjectRow.id, ProjectRow.name, ProjectMemberRow.role)
                    .join(ProjectMemberRow, ProjectMemberRow.project_id == ProjectRow.id)
                    .where(ProjectMemberRow.principal_kind == "user", ProjectMemberRow.principal_id == user_id)
                    .order_by(ProjectRow.created_at)
                )
            ).all()
            audit = (
                await db.execute(
                    select(AuditLogRow)
                    .where(or_(AuditLogRow.actor_id == user_id, AuditLogRow.target == user_id))
                    .order_by(AuditLogRow.id.desc())
                    .limit(_AUDIT_EXPORT_LIMIT)
                )
            ).scalars()
            return {
                "exported_at": _iso(datetime.now(UTC)),
                "profile": {
                    "id": user.id,
                    "email": user.email,
                    "name": user.name,
                    "status": user.status,
                    "email_verified": user.email_verified,
                    "is_instance_admin": user.is_instance_admin,
                    "locale": user.locale,
                    "commit_name": user.commit_name,
                    "commit_email": user.commit_email,
                    "commit_use_account_email": user.commit_use_account_email,
                    "created_at": _iso(user.created_at),
                    "last_login_at": _iso(user.last_login_at),
                },
                "identities": [{"provider": i.provider, "email": i.email} for i in identities],
                "api_tokens": [
                    {
                        "name": t.name,
                        "prefix": t.prefix,
                        "scopes": list(t.scopes),
                        "created_at": _iso(t.created_at),
                        "expires_at": _iso(t.expires_at),
                        "last_used_at": _iso(t.last_used_at),
                    }
                    for t in tokens
                ],
                "sessions": [
                    {
                        "created_at": _iso(s.created_at),
                        "last_seen_at": _iso(s.last_seen_at),
                        "ip": s.ip,
                        "user_agent": s.user_agent,
                    }
                    for s in sessions
                ],
                "settings": {s.key: s.value for s in settings},
                "organizations": [{"slug": slug, "name": name, "role": role} for slug, name, role in orgs],
                "groups": [{"organization": slug, "name": name} for slug, name in groups],
                "projects_owned": [
                    {
                        "id": str(p.id),
                        "name": p.name,
                        "kind": p.kind,
                        "created_at": _iso(p.created_at),
                        "deleted_at": _iso(p.deleted_at),
                    }
                    for p in owned
                ],
                "projects_shared_with_me": [{"id": str(pid), "name": name, "role": role} for pid, name, role in shared],
                "audit": [_audit_item(a, user_id) for a in audit],
            }


def _audit_item(row: AuditLogRow, user_id: str) -> dict[str, Any]:
    return {
        "at": _iso(row.at),
        "action": row.action,
        "as_actor": row.actor_id == user_id,
        "target": row.target,
        "details": dict(row.details),
    }
