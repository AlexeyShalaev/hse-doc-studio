from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

import structlog

from hse_doc_studio.core.repositories import (
    IFileRepository,
    IProjectIndexRepository,
    IProjectRepository,
    ITemplateRepository,
)
from hse_doc_studio.use_cases.files._template_guard import (
    is_protected_path,
    template_protected_paths,
)
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()


@dataclass
class FileTreeItem:
    path: str
    size: int
    modified_at: str
    # False for items that belong to the template (documents, preamble, generated
    # includes, and folders holding them) — these can't be deleted/renamed/moved.
    deletable: bool
    is_dir: bool = False


@dataclass
class ListFileTreeInput:
    project_id: UUID


@dataclass
class ListFileTreeOutput:
    items: list[FileTreeItem]


class ListFileTreeUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        file_repo: IFileRepository,
        template_repo: ITemplateRepository,
    ) -> None:
        self._file_repo = file_repo
        self._template_repo = template_repo
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: ListFileTreeInput) -> ListFileTreeOutput:
        result = await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))
        project = result.project

        protected = template_protected_paths(self._template_repo, project)
        # Папки отдаются наравне с файлами, чтобы пустые пользовательские каталоги
        # были самостоятельными узлами, а не только выводились из своих файлов.
        # Размер и время правки приходят из самого обхода: отдельный `stat()` на
        # каждый элемент удваивал число системных вызовов, а на бинд-маунте
        # Docker они дорогие.
        items = [
            FileTreeItem(
                path=entry.path,
                size=0 if entry.is_dir else entry.size,
                modified_at=_ts(entry.mtime),
                deletable=not is_protected_path(entry.path, protected),
                is_dir=entry.is_dir,
            )
            for entry in self._file_repo.scan(project.folder)
        ]
        return ListFileTreeOutput(items=items)


def _ts(mtime: float) -> str:
    return datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
