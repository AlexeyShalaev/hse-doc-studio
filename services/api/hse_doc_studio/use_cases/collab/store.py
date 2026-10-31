"""Текст файла проекта для комнат совместной правки: чтение, версия, запись как у обычного сохранения."""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID

import structlog

from hse_doc_studio.core.collab.ports import TextSnapshot
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import VcsCommitKind
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.file_version import file_etag
from hse_doc_studio.core.repositories import IFileRepository, IProjectIndexRepository, IProjectRepository
from hse_doc_studio.core.vcs.entities import VcsSettings
from hse_doc_studio.core.vcs.protocols import IVcsFolderLocks, IVcsService
from hse_doc_studio.use_cases.files.put_file import PutFileInput, PutFileUC
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()


class ProjectTextStore:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        file_repo: IFileRepository,
        put_file: PutFileUC,
        vcs: IVcsService,
        vcs_locks: IVcsFolderLocks,
    ) -> None:
        self._get = GetProjectUC(project_repo, project_index_repo)
        self._files = file_repo
        self._put = put_file
        self._vcs = vcs
        self._locks = vcs_locks

    async def _project(self, project_id: UUID) -> Project | None:
        try:
            return (await self._get.execute(GetProjectInput(project_id=project_id))).project
        except NotFoundError:
            return None

    def _raw(self, project: Project, path: str) -> bytes | None:
        try:
            return self._files.read(project.folder, path)
        except (FileNotFoundError, IsADirectoryError, NotADirectoryError, PermissionError):
            return None

    async def read(self, project_id: UUID, path: str) -> TextSnapshot | None:
        project = await self._project(project_id)
        if project is None:
            return None
        raw = await asyncio.to_thread(self._raw, project, path)
        if raw is None:
            return None
        try:
            return TextSnapshot(raw.decode("utf-8"), file_etag(raw))
        except UnicodeDecodeError:
            return None

    async def etag(self, project_id: UUID, path: str) -> str | None:
        project = await self._project(project_id)
        if project is None:
            return None
        raw = await asyncio.to_thread(self._raw, project, path)
        return None if raw is None else file_etag(raw)

    async def write(self, project_id: UUID, path: str, text: str) -> str:
        result = await self._put.execute(PutFileInput(project_id=project_id, path=path, content=text.encode("utf-8")))
        return result.etag

    async def record_external(self, project_id: UUID, path: str) -> None:
        """Правочный коммит текущего содержимого папки: чужая версия остаётся в истории до того, как её сольют."""
        project = await self._project(project_id)
        if project is None:
            return
        try:
            if not self._vcs.is_available(project) or not self._vcs.is_initialized(project):
                return
            settings = VcsSettings.from_meta(project.meta)
            if not settings.tracking_enabled:
                return
            async with self._locks.for_folder(project.folder):
                await asyncio.to_thread(
                    lambda: self._vcs.commit(
                        project,
                        message=f"Внешняя правка: {path}",
                        kind=VcsCommitKind.edit,
                        include_pdf=settings.track_pdf,
                    )
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("collab external-version commit failed", path=path, exc=str(exc))

    async def folder(self, project_id: UUID) -> Path | None:
        project = await self._project(project_id)
        return None if project is None else project.folder
