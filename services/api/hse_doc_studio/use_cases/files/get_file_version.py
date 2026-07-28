from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from hse_doc_studio.core.file_version import file_etag
from hse_doc_studio.core.repositories import (
    IFileRepository,
    IProjectIndexRepository,
    IProjectRepository,
)
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC


@dataclass
class GetFileVersionInput:
    project_id: UUID
    path: str


@dataclass
class GetFileVersionOutput:
    etag: str
    size: int


class GetFileVersionUC:
    """Версия файла без его содержимого — для опроса открытых вкладок.

    Отдельно от `GetFileUC`, потому что вопрос другой: не «дай текст», а «тот же
    ли он». Ответ в десяток байт, поэтому опрашивать открытые файлы раз в
    несколько секунд дёшево — а слежение за файловой системой изнутри контейнера
    не работает: события inotify не переходят границу бинд-маунта на Docker
    Desktop, и правку из VS Code мы бы попросту не заметили.
    """

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        file_repo: IFileRepository,
    ) -> None:
        self._file_repo = file_repo
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: GetFileVersionInput) -> GetFileVersionOutput:
        result = await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))
        content = self._file_repo.read(result.project.folder, inp.path)
        return GetFileVersionOutput(etag=file_etag(content), size=len(content))
