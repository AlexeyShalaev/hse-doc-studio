"""Доступ к секрету git-доступа в локальной установке: пользователь один, привязок и аудита нет."""

from __future__ import annotations

from uuid import UUID

from hse_doc_studio.core.git_sync.entities import GitCredential, RemoteBinding
from hse_doc_studio.core.git_sync.protocols import IGitCredentialRepository
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.git_sync.url import RemoteUrl


class DirectCredentialAccess:
    """ICredentialAccess поверх репозитория: всё, что в нём лежит, принадлежит единственному пользователю."""

    def __init__(self, credentials: IGitCredentialRepository) -> None:
        self._credentials = credentials

    async def get(self, credential_id: UUID, *, project_id: UUID | None) -> GitCredential | None:
        return await self._credentials.get(credential_id)

    async def get_secret(self, credential_id: UUID, *, project_id: UUID | None, remote: RemoteUrl) -> Secret:
        return await self._credentials.get_secret(credential_id)


class LocalGitRemoteBindings:
    """IGitRemoteBindings локальной установки: привязка лежит в настройках хранилища проекта, а не в БД."""

    async def bind(self, project_id: UUID, credential_id: UUID, remote: RemoteUrl) -> None:
        return None

    async def unbind(self, project_id: UUID) -> None:
        return None

    async def get(self, project_id: UUID) -> RemoteBinding | None:
        return None
