from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import structlog

from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.git_sync.error_messages import git_error
from hse_doc_studio.core.git_sync.errors import GitErrorCode
from hse_doc_studio.core.git_sync.fetch_schedule import FetchBook
from hse_doc_studio.core.git_sync.protocols import IGitOperationRegistry, IGitRemoteRegistry
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.projects.lifecycle import ServerProjectStorage
from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
)
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()


@dataclass
class UnregisterProjectInput:
    project_id: UUID


class UnregisterProjectUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        git_operations: IGitOperationRegistry,
        git_remotes: IGitRemoteRegistry,
        fetch_book: FetchBook,
        server_storage: ServerProjectStorage | None = None,
    ) -> None:
        self._project_repo = project_repo
        self._project_index_repo = project_index_repo
        self._git_operations = git_operations
        self._git_remotes = git_remotes
        self._fetch_book = fetch_book
        self._get_uc = GetProjectUC(project_repo, project_index_repo)
        self._server = server_storage

    async def execute(self, inp: UnregisterProjectInput) -> None:
        if self._server is not None:
            await self._soft_delete(self._server, inp.project_id)
            return
        result = await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))
        project = result.project

        # Синхронизация, которая ещё идёт, потеряла бы проект из-под ног: сначала её отмена или конец.
        if self._git_operations.is_busy(project.folder):
            current = self._git_operations.current_for(project.id)
            raise git_error(GitErrorCode.sync_busy, operation_id=current.id if current else None)

        # Выборка, которая ещё идёт, дописала бы состояние в папку проекта, уже убранного из списка.
        async with self._fetch_book.lock(project.folder):
            self._project_index_repo.unregister(project.folder)
            self._git_remotes.remove(project.folder)
        self._fetch_book.forget(project.folder)
        logger.info(
            "project unregistered",
            project_id=str(inp.project_id),
            folder=str(project.folder),
        )

    async def _soft_delete(self, server: ServerProjectStorage, project_id: UUID) -> None:
        """Мягкое удаление: проект уходит из списков, папка и удалённая строка живут до срока хранения.

        Настройки и ключи удалённой синхронизации не трогаем: до стирания проект можно вернуть как есть.
        """
        located = await server.locator.locate(project_id)
        if located is None:
            raise NotFoundError(
                localized_error(f"Проект {project_id!r} не найден", f"Project {project_id!r} not found")
            )
        folder, project = located
        if self._git_operations.is_busy(folder):
            current = self._git_operations.current_for(project.id)
            raise git_error(GitErrorCode.sync_busy, operation_id=current.id if current else None)
        async with self._fetch_book.lock(folder):
            await server.locator.unregister(folder)
        self._fetch_book.forget(folder)
        logger.info("project soft deleted", project_id=str(project_id))
