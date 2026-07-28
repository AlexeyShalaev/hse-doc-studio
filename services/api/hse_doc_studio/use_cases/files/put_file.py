from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import structlog

from hse_doc_studio.core.file_version import etag_matches, file_etag
from hse_doc_studio.core.repositories import (
    IFileRepository,
    IProjectIndexRepository,
    IProjectRepository,
)
from hse_doc_studio.core.vcs.protocols import (
    IVcsEditThrottle,
    IVcsFolderLocks,
    IVcsService,
)
from hse_doc_studio.use_cases.files._vcs_edit import maybe_edit_commit
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()


class StaleFileError(Exception):
    """Файл на диске изменился с момента, на который опирался клиент.

    Несёт актуальные содержимое и версию: развилку «взять с диска / оставить
    своё» показывает интерфейс, и данные для неё у него должны быть сразу.
    """

    def __init__(self, current_content: bytes, current_etag: str) -> None:
        super().__init__("file changed on disk since it was loaded")
        self.current_content = current_content
        self.current_etag = current_etag


@dataclass
class PutFileInput:
    project_id: UUID
    path: str
    content: bytes
    # Версия, на которую опирался клиент (HTTP `If-Match`). None — безусловная
    # запись: так пишут агент и внутренние операции, у которых нет буфера.
    if_match: str | None = None


@dataclass
class PutFileOutput:
    etag: str


class PutFileUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        file_repo: IFileRepository,
        vcs_service: IVcsService,
        vcs_locks: IVcsFolderLocks,
        vcs_throttle: IVcsEditThrottle,
    ) -> None:
        self._file_repo = file_repo
        self._vcs = vcs_service
        self._vcs_locks = vcs_locks
        self._vcs_throttle = vcs_throttle
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: PutFileInput) -> PutFileOutput:
        result = await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))
        project = result.project

        if inp.if_match is not None:
            self._ensure_not_stale(project.folder, inp.path, inp.if_match)

        self._file_repo.write(project.folder, inp.path, inp.content)

        logger.debug(
            "file written via use case",
            project_id=str(inp.project_id),
            path=inp.path,
        )
        await maybe_edit_commit(self._vcs, self._vcs_locks, self._vcs_throttle, project, f"Правка: {inp.path}")
        return PutFileOutput(etag=file_etag(inp.content))

    def _ensure_not_stale(self, folder: Path, path: str, if_match: str) -> None:
        try:
            current = self._file_repo.read(folder, path)
        except FileNotFoundError:
            # Файла нет: клиент опирался на версию, которой больше не существует
            # (удалили снаружи). Создавать его заново молча — не наше решение.
            raise StaleFileError(b"", file_etag(b"")) from None
        if not etag_matches(if_match, current):
            raise StaleFileError(current, file_etag(current))
