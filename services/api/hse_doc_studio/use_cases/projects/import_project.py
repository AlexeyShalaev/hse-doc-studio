"""Импорт проекта из локальной Студии на сервер: zip с папкой проекта становится новым проектом владельца."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import UUID, uuid4

import structlog

from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.projects.importer import (
    ArchiveManifest,
    ILocalHistoryReader,
    ImportLimits,
    ImportReport,
    ImportWarning,
    ImportWarningCode,
    IProjectArchive,
    ProjectImportCode,
    ProjectImportError,
)
from hse_doc_studio.core.projects.lifecycle import ServerProjectStorage
from hse_doc_studio.core.projects.locator import ProjectAlreadyRegisteredError
from hse_doc_studio.core.projects.usage import IProjectQuota
from hse_doc_studio.core.repositories import IChatRepository, IProjectRepository

logger = structlog.get_logger()

# Занятый id (чужой проект, свежая гонка) лечится новым; больше трёх попыток значит, что дело не в id.
_ATTEMPTS = 3


@dataclass
class ImportProjectInput:
    archive: Path


class ImportProjectUC:
    """Идентификатор проекта сохраняется, если свободен, иначе выдаётся новый, и project.json переписывается.

    Права берутся из базы: импортёр становится владельцем, а прежние поля доступа из файла ничего не решают.
    Чаты переезжают в личные чаты импортёра, записи сборок и сдач (пути на диске автора) пропускаются.
    """

    def __init__(
        self,
        project_repo: IProjectRepository,
        server_storage: ServerProjectStorage,
        archive: IProjectArchive,
        history: ILocalHistoryReader,
        chat_repo: IChatRepository,
        quota: IProjectQuota,
        limits: ImportLimits,
    ) -> None:
        self._project_repo = project_repo
        self._server = server_storage
        self._archive = archive
        self._history = history
        self._chats = chat_repo
        self._quota = quota
        self._limits = limits

    async def check(self, archive: Path) -> ArchiveManifest:
        """Пробный запуск: тот же разбор архива, что и при приёме, но на том ничего не кладётся."""
        return await asyncio.to_thread(self._archive.inspect, archive, self._limits)

    async def execute(self, inp: ImportProjectInput) -> ImportReport:
        manifest = await asyncio.to_thread(self._archive.inspect, inp.archive, self._limits)
        for attempt in range(_ATTEMPTS):
            project_id = manifest.project_id if attempt == 0 else uuid4()
            try:
                report = await self._import(inp.archive, manifest, project_id)
            except (FileExistsError, ProjectAlreadyRegisteredError):
                continue
            if self._quota.enabled:
                await self._quota.record_change(report.project_id, report.bytes)
            logger.info(
                "project imported",
                project_id=str(report.project_id),
                id_regenerated=report.id_regenerated,
                files=report.files,
                chats=report.chats,
            )
            return report
        raise ProjectImportError(
            ProjectImportCode.unavailable,
            localized_error(
                "Не удалось выделить место под проект, попробуйте ещё раз.",
                "Could not allocate room for the project, try again.",
            ),
        )

    async def _import(self, archive: Path, manifest: ArchiveManifest, project_id: UUID) -> ImportReport:
        server = self._server
        folder: Path | None = None
        try:
            async with server.uow.begin():
                folder = server.volume.allocate(project_id)
                extracted = await asyncio.to_thread(self._archive.extract, archive, manifest, server.volume, folder)
                hardened = await asyncio.to_thread(self._archive.harden_store, folder)
                project = self._project_repo.get(folder)
                if project is None:
                    raise ProjectImportError(
                        ProjectImportCode.no_project,
                        localized_error(
                            "project.json в архиве не читается.", "project.json in the archive cannot be read."
                        ),
                    )
                if project.id != project_id:
                    self._project_repo.save(replace(project, id=project_id))
                await server.locator.register(folder)
                chats = 0
                if self._history.has_chats(folder):
                    chats = await self._history.transfer_chats(folder, project_id, self._chats)
                    await asyncio.to_thread(self._history.discard_chats, folder)
        except BaseException:
            if folder is not None:
                self._discard(project_id)
            raise
        return ImportReport(
            project_id=project_id,
            name=manifest.name,
            id_regenerated=project_id != manifest.project_id,
            files=extracted.files,
            bytes=extracted.bytes,
            chats=chats,
            warnings=_warnings(manifest, hardened),
        )

    def _discard(self, project_id: UUID) -> None:
        try:
            self._server.volume.remove(project_id)
        except OSError as exc:
            logger.exception("imported project folder not removed", project_id=str(project_id), exc=str(exc))


def _warnings(manifest: ArchiveManifest, hardened: int) -> list[ImportWarning]:
    found: list[ImportWarning] = []
    if manifest.has_remote:
        found.append(ImportWarning(ImportWarningCode.remote_needs_access))
    if manifest.records:
        found.append(ImportWarning(ImportWarningCode.records_skipped, str(manifest.records)))
    if hardened:
        found.append(ImportWarning(ImportWarningCode.store_hardened, str(hardened)))
    if manifest.junk:
        found.append(ImportWarning(ImportWarningCode.junk_skipped, str(manifest.junk)))
    return found
