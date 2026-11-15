"""Доступ к секрету для git и API хостинга Студии шаблонов: личный доступ человека или служебный репозитория (4.2).

Сначала обычный путь (`ICredentialAccess` установки: свой доступ человека, аудит каждого использования). Если такого
доступа нет, id может быть служебным доступом репозитория паков. Он отдаётся только:

- человеку с правом «Автор шаблонов» (админ установки имеет его всегда); гостю и фоновой задаче без актора нет;
- для адреса того самого репозитория (хост, порт и путь совпадают): форк или другой репозиторий служебным токеном не
  открыть, даже подменив адрес пространства.

Этот запускатель git и клиент хостинга собираются только для Студии шаблонов: остальная Студия о служебных доступах
не знает. Каждое использование служебного секрета пишется в журнал (`pack_studio.service_access_use`).
"""

from __future__ import annotations

from uuid import UUID

from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.access.entities import ActorKind
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.git_sync.entities import CredentialStatus, GitCredential, GitCredentialKind
from hse_doc_studio.core.git_sync.protocols import ICredentialAccess
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.git_sync.url import RemoteUrl
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.identity.protocols import IAuditLog
from hse_doc_studio.core.pack_studio.git_flow import repo_key, repo_path_of
from hse_doc_studio.core.pack_studio.protocols import (
    IPackStudioGrantRepository,
    IServiceAccessRepository,
    ServiceAccess,
)

AUDIT_SERVICE_USE = "pack_studio.service_access_use"


def _not_found() -> NotFoundError:
    return NotFoundError(localized_error("Доступ не найден", "Credential not found"))


class PackStudioCredentialAccess:
    def __init__(
        self,
        base: ICredentialAccess,
        service: IServiceAccessRepository,
        grants: IPackStudioGrantRepository,
        audit: IAuditLog,
    ) -> None:
        self._base = base
        self._service = service
        self._grants = grants
        self._audit = audit

    async def get(self, credential_id: UUID, *, project_id: UUID | None) -> GitCredential | None:
        own = await self._base.get(credential_id, project_id=project_id)
        if own is not None:
            return own
        access = await self._allowed(credential_id)
        if access is None:
            return None
        return GitCredential(
            id=access.id,
            kind=GitCredentialKind.pat,
            label=access.label,
            host=access.host,
            username=None,
            status=CredentialStatus.ok,
            created_at=access.created_at,
            token_family=access.token_family,
            port=access.port,
        )

    async def get_secret(self, credential_id: UUID, *, project_id: UUID | None, remote: RemoteUrl) -> Secret:
        if await self._base.get(credential_id, project_id=project_id) is not None:
            return await self._base.get_secret(credential_id, project_id=project_id, remote=remote)
        access = await self._allowed(credential_id)
        if access is None or remote.host is None:
            raise _not_found()
        if repo_key(remote.host, remote.port, repo_path_of(remote.display_url, None)) != access.repo_key:
            raise _not_found()
        secret = await self._service.secret(access.id)
        if secret is None:
            raise _not_found()
        actor = current_actor()
        await self._audit.record(
            AUDIT_SERVICE_USE,
            actor_id=actor.id if actor is not None else None,
            target=str(access.id),
            details={"url": access.url, "remote": remote.display_url},
        )
        return secret

    async def _allowed(self, credential_id: UUID) -> ServiceAccess | None:
        actor = current_actor()
        if actor is None or actor.kind is not ActorKind.user or actor.id is None or actor.is_guest:
            return None
        if not actor.is_instance_admin and not await self._grants.has_grant(actor.id):
            return None
        return await self._service.get(credential_id)
