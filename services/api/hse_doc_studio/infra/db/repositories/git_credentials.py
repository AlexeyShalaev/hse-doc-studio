"""Git-доступы в Postgres: токен или ключ ssh принадлежит пользователю, проект пользуется им по привязке.

Секрет лежит шифртекстом с привязкой к таблице, колонке и id записи и расшифровывается только в
`PostgresCredentialAccess.get_secret` (и в `get_secret` владельца, когда он проверяет свой токен).
Чужой доступ неотличим от несуществующего. В журнал и в логи секрет не попадает никогда.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import structlog
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from hse_doc_studio.core.access.context import ActorRequired, current_actor, require_actor
from hse_doc_studio.core.access.entities import Actor, ActorKind, Role
from hse_doc_studio.core.access.repositories import IProjectAclRepository
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.git_sync.entities import (
    CredentialStatus,
    CredentialUsage,
    GitCredential,
    GitCredentialKind,
    RemoteBinding,
)
from hse_doc_studio.core.git_sync.protocols import ISecretCipher
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.git_sync.url import RemoteUrl
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.identity.protocols import IAuditLog
from hse_doc_studio.core.secrets import column_aad
from hse_doc_studio.infra.db.orm.git_credentials import GitCredentialRow, GitRemoteBindingRow
from hse_doc_studio.infra.db.orm.projects import ProjectRow
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.git_sync.auth_env import check_credential_matches

logger = structlog.get_logger()

_TABLE = "git_credentials"
_COLUMN = "secret_enc"
_EDIT_ROLES = frozenset({Role.editor, Role.owner})
AUDIT_USE = "git.credential.use"
AUDIT_BIND = "git.remote.bind"
AUDIT_UNBIND = "git.remote.unbind"


def _not_found() -> NotFoundError:
    return NotFoundError(localized_error("Доступ не найден", "Credential not found"))


def _owner_id() -> str:
    actor = require_actor()
    if actor.kind is not ActorKind.user or actor.id is None:
        raise ActorRequired("git-доступы принадлежат пользователю")
    return actor.id


def _to_entity(row: GitCredentialRow, *, readable: bool) -> GitCredential:
    status = CredentialStatus(row.status) if readable else CredentialStatus.unreadable
    return GitCredential(
        id=row.id,
        kind=GitCredentialKind(row.kind),
        label=row.label,
        host=row.host,
        username=row.username,
        status=status,
        created_at=row.created_at,
        token_family=row.token_family,
        public_key=row.public_key,
        fingerprint_sha256=row.fingerprint_sha256,
        port=row.port,
        last_used_at=row.last_used_at,
        expires_at=row.expires_at,
    )


def _stored_status(status: CredentialStatus) -> str:
    # unreadable вычисляется при чтении и не хранится: ключ шифрования могут вернуть.
    return (CredentialStatus.unverified if status is CredentialStatus.unreadable else status).value


class PostgresGitCredentialRepository:
    """IGitCredentialRepository сервера: видит и меняет только владелец, `mark` доступен раннеру без актора."""

    def __init__(self, sessions: SessionProvider, cipher: ISecretCipher) -> None:
        self._sessions = sessions
        self._cipher = cipher

    async def list(self) -> list[GitCredential]:
        owner = _owner_id()
        stmt = (
            select(GitCredentialRow)
            .where(GitCredentialRow.owner_id == owner)
            .order_by(GitCredentialRow.created_at, GitCredentialRow.id)
        )
        async with self._sessions.use() as session:
            rows = (await session.execute(stmt)).scalars().all()
        return [self._entity(row) for row in rows]

    async def get(self, credential_id: UUID) -> GitCredential | None:
        row = await self._row(credential_id)
        return None if row is None else self._entity(row)

    async def add(self, credential: GitCredential, secret: Secret) -> None:
        owner = _owner_id()
        sealed = self._cipher.encrypt(secret, aad=column_aad(_TABLE, _COLUMN, credential.id))
        async with self._sessions.use() as session:
            session.add(
                GitCredentialRow(
                    id=credential.id,
                    owner_id=owner,
                    kind=credential.kind.value,
                    label=credential.label,
                    host=credential.host,
                    port=credential.port,
                    username=credential.username,
                    status=_stored_status(credential.status),
                    token_family=credential.token_family,
                    public_key=credential.public_key,
                    fingerprint_sha256=credential.fingerprint_sha256,
                    created_at=credential.created_at,
                    last_used_at=credential.last_used_at,
                    expires_at=credential.expires_at,
                    secret_enc=sealed,
                )
            )
        logger.info("git credential added", credential_id=str(credential.id), kind=credential.kind.value)

    async def update(self, credential: GitCredential, secret: Secret | None = None) -> None:
        owner = _owner_id()
        values: dict[str, object] = {
            "label": credential.label,
            "host": credential.host,
            "port": credential.port,
            "username": credential.username,
            "status": _stored_status(credential.status),
            "token_family": credential.token_family,
            "public_key": credential.public_key,
            "fingerprint_sha256": credential.fingerprint_sha256,
            "last_used_at": credential.last_used_at,
            "expires_at": credential.expires_at,
        }
        if secret is not None:
            values[_COLUMN] = self._cipher.encrypt(secret, aad=column_aad(_TABLE, _COLUMN, credential.id))
        stmt = (
            update(GitCredentialRow)
            .where(GitCredentialRow.id == credential.id, GitCredentialRow.owner_id == owner)
            .values(**values)
            .returning(GitCredentialRow.id)
        )
        async with self._sessions.use() as session:
            if (await session.execute(stmt)).first() is None:
                raise _not_found()

    async def delete(self, credential_id: UUID) -> bool:
        owner = _owner_id()
        stmt = (
            delete(GitCredentialRow)
            .where(GitCredentialRow.id == credential_id, GitCredentialRow.owner_id == owner)
            .returning(GitCredentialRow.id)
        )
        async with self._sessions.use() as session:
            deleted = (await session.execute(stmt)).first() is not None
        if deleted:
            logger.info("git credential deleted", credential_id=str(credential_id))
        return deleted

    async def get_secret(self, credential_id: UUID) -> Secret:
        row = await self._row(credential_id)
        if row is None:
            raise _not_found()
        return self._cipher.decrypt(row.secret_enc, aad=column_aad(_TABLE, _COLUMN, row.id))

    async def mark(self, credential_id: UUID, status: CredentialStatus, *, used_at: datetime | None = None) -> None:
        """Статус и время использования ставит раннер после операции, в том числе от лица участника проекта."""
        if status is CredentialStatus.unreadable:
            return
        values: dict[str, object] = {"status": status.value}
        if used_at is not None:
            values["last_used_at"] = used_at
        async with self._sessions.use() as session:
            await session.execute(update(GitCredentialRow).where(GitCredentialRow.id == credential_id).values(**values))

    def _entity(self, row: GitCredentialRow) -> GitCredential:
        return _to_entity(row, readable=self._cipher.can_read(row.secret_enc))

    async def _row(self, credential_id: UUID) -> GitCredentialRow | None:
        owner = _owner_id()
        stmt = select(GitCredentialRow).where(GitCredentialRow.id == credential_id, GitCredentialRow.owner_id == owner)
        async with self._sessions.use() as session:
            return (await session.execute(stmt)).scalar_one_or_none()


def _binding(row: GitRemoteBindingRow) -> RemoteBinding:
    return RemoteBinding(
        project_id=row.project_id,
        credential_id=row.credential_id,
        bound_by=row.bound_by,
        scheme=row.scheme,
        host=row.host,
        port=row.port,
    )


class PostgresGitRemoteBindings:
    """Привязка доступа к проекту: её ставит владелец доступа при подключении репозитория, а снимает отключение."""

    def __init__(self, sessions: SessionProvider, audit: IAuditLog) -> None:
        self._sessions = sessions
        self._audit = audit

    async def bind(self, project_id: UUID, credential_id: UUID, remote: RemoteUrl) -> None:
        owner = _owner_id()
        async with self._sessions.use() as session:
            credential = (
                await session.execute(
                    select(GitCredentialRow).where(
                        GitCredentialRow.id == credential_id, GitCredentialRow.owner_id == owner
                    )
                )
            ).scalar_one_or_none()
            if credential is None:
                raise _not_found()
            check_credential_matches(remote, _to_entity(credential, readable=True))
            now = datetime.now(timezone.utc)
            values = {
                "credential_id": credential_id,
                "bound_by": owner,
                "scheme": remote.kind.value,
                "host": str(remote.host).lower(),
                "port": remote.port,
                "created_at": now,
            }
            await session.execute(
                pg_insert(GitRemoteBindingRow)
                .values(project_id=project_id, **values)
                .on_conflict_do_update(index_elements=[GitRemoteBindingRow.project_id], set_=values)
            )
        await self._audit.record(
            AUDIT_BIND,
            actor_id=owner,
            target=str(project_id),
            details={"credential_id": str(credential_id), "scheme": remote.kind.value, "host": remote.host},
        )

    async def unbind(self, project_id: UUID) -> None:
        async with self._sessions.use() as session:
            removed = (
                await session.execute(
                    delete(GitRemoteBindingRow)
                    .where(GitRemoteBindingRow.project_id == project_id)
                    .returning(GitRemoteBindingRow.credential_id)
                )
            ).first()
        if removed is not None:
            actor = current_actor()
            await self._audit.record(
                AUDIT_UNBIND,
                actor_id=actor.id if actor else None,
                target=str(project_id),
                details={"credential_id": str(removed[0])},
            )

    async def get(self, project_id: UUID) -> RemoteBinding | None:
        async with self._sessions.use() as session:
            row = await session.get(GitRemoteBindingRow, project_id)
        return None if row is None else _binding(row)


class PostgresCredentialUsage:
    """Проекты, подключённые с доступами актора."""

    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def by_credential(self) -> dict[UUID, list[CredentialUsage]]:
        owner = _owner_id()
        stmt = (
            select(GitRemoteBindingRow.credential_id, ProjectRow.id, ProjectRow.name)
            .join(GitCredentialRow, GitCredentialRow.id == GitRemoteBindingRow.credential_id)
            .join(ProjectRow, ProjectRow.id == GitRemoteBindingRow.project_id)
            .where(GitCredentialRow.owner_id == owner, ProjectRow.deleted_at.is_(None))
            .order_by(ProjectRow.name, ProjectRow.id)
        )
        async with self._sessions.use() as session:
            rows = (await session.execute(stmt)).all()
        usage: dict[UUID, list[CredentialUsage]] = {}
        for credential_id, project_id, name in rows:
            usage.setdefault(credential_id, []).append(CredentialUsage(project_id, name))
        return usage


class PostgresCredentialAccess:
    """ICredentialAccess сервера: владелец или Редактор проекта с привязанным доступом, каждое использование в аудит.

    Фоновые операции без актора (опрос удалённых репозиториев) пользуются только привязанным доступом:
    для них это единственный способ дойти до секрета, и в журнале у такого события нет актора.
    """

    def __init__(
        self,
        sessions: SessionProvider,
        cipher: ISecretCipher,
        acl: IProjectAclRepository,
        audit: IAuditLog,
    ) -> None:
        self._sessions = sessions
        self._cipher = cipher
        self._acl = acl
        self._audit = audit

    async def get(self, credential_id: UUID, *, project_id: UUID | None) -> GitCredential | None:
        row, _ = await self._authorized(credential_id, project_id, None)
        return None if row is None else _to_entity(row, readable=self._cipher.can_read(row.secret_enc))

    async def get_secret(self, credential_id: UUID, *, project_id: UUID | None, remote: RemoteUrl) -> Secret:
        row, via = await self._authorized(credential_id, project_id, remote)
        if row is None:
            raise _not_found()
        secret = self._cipher.decrypt(row.secret_enc, aad=column_aad(_TABLE, _COLUMN, row.id))
        actor = current_actor()
        await self._audit.record(
            AUDIT_USE,
            actor_id=actor.id if actor is not None else None,
            target=str(credential_id),
            details={
                "project_id": None if project_id is None else str(project_id),
                "scheme": remote.kind.value,
                "host": remote.host,
                "via": via,
            },
        )
        return secret

    async def _authorized(
        self, credential_id: UUID, project_id: UUID | None, remote: RemoteUrl | None
    ) -> tuple[GitCredentialRow | None, str]:
        actor = current_actor()
        if actor is not None and actor.kind is ActorKind.user and actor.id is not None:
            async with self._sessions.use() as session:
                own = (
                    await session.execute(
                        select(GitCredentialRow).where(
                            GitCredentialRow.id == credential_id, GitCredentialRow.owner_id == actor.id
                        )
                    )
                ).scalar_one_or_none()
            if own is not None:
                return own, "owner"
        elif actor is not None:
            return None, ""
        if project_id is None:
            return None, ""
        row = await self._bound_row(credential_id, project_id, remote)
        if row is None:
            return None, ""
        if actor is not None and not await self._can_edit(actor, project_id):
            return None, ""
        return row, "binding"

    async def _bound_row(
        self, credential_id: UUID, project_id: UUID, remote: RemoteUrl | None
    ) -> GitCredentialRow | None:
        stmt = (
            select(GitCredentialRow, GitRemoteBindingRow)
            .join(GitRemoteBindingRow, GitRemoteBindingRow.credential_id == GitCredentialRow.id)
            .where(GitRemoteBindingRow.project_id == project_id, GitCredentialRow.id == credential_id)
        )
        async with self._sessions.use() as session:
            found = (await session.execute(stmt)).first()
        if found is None:
            return None
        credential, binding = found
        if remote is not None and not _same_remote(binding, remote):
            logger.warning("git credential refused: remote differs from the bound one", project_id=str(project_id))
            return None
        return credential

    async def _can_edit(self, actor: Actor, project_id: UUID) -> bool:
        acl = await self._acl.load_for(actor, project_id)
        grant = acl.grant_for(actor) if acl is not None else None
        return grant is not None and grant.role in _EDIT_ROLES


def _same_remote(binding: GitRemoteBindingRow, remote: RemoteUrl) -> bool:
    return (
        binding.scheme == remote.kind.value
        and remote.host is not None
        and binding.host == remote.host.lower()
        and binding.port == remote.port
    )
