from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import structlog

from hse_doc_studio.core.i18n import localized_error
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


@dataclass
class ApplyCheckFixInput:
    project_id: UUID
    path: str
    search: str
    replace: str
    line: int | None = None


class ApplyCheckFixUC:
    """Apply a deterministic quick-fix: replace the first occurrence of `search`
    with `replace` (on `line` if given, else anywhere) in a project file.

    Refuses if the text no longer matches (the file changed since the finding
    was produced) so a stale fix can never corrupt the document.
    """

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

    async def execute(self, inp: ApplyCheckFixInput) -> None:
        if not inp.search:
            raise ValueError(localized_error("Фикс содержит пустую строку поиска", "Fix has an empty search string"))

        project = (await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))).project
        content = self._file_repo.read(project.folder, inp.path).decode("utf-8", errors="replace")

        new_content = self._apply(content, inp.search, inp.replace, inp.line)
        self._file_repo.write(project.folder, inp.path, new_content.encode("utf-8"))
        logger.debug("check fix applied", project_id=str(inp.project_id), path=inp.path, line=inp.line)
        await maybe_edit_commit(self._vcs, self._vcs_locks, self._vcs_throttle, project, f"Автофикс: {inp.path}")

    @staticmethod
    def _apply(content: str, search: str, replace: str, line: int | None) -> str:
        lines = content.splitlines(keepends=True)
        if line is not None and 1 <= line <= len(lines):
            idx = line - 1
            if search not in lines[idx]:
                raise ValueError(
                    localized_error(
                        "Фикс больше не применим: текст не найден в указанной строке",
                        "Fix no longer applies: text not found on the target line",
                    )
                )
            lines[idx] = lines[idx].replace(search, replace, 1)
            return "".join(lines)
        if search not in content:
            raise ValueError(
                localized_error(
                    "Фикс больше не применим: текст не найден в файле",
                    "Fix no longer applies: text not found in the file",
                )
            )
        return content.replace(search, replace, 1)
