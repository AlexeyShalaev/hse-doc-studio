from __future__ import annotations

import posixpath
from dataclasses import dataclass, replace
from uuid import UUID

from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import IProjectIndexRepository, IProjectRepository
from hse_doc_studio.core.template_update.entities import TemplateTrackingState
from hse_doc_studio.core.template_update.protocols import ITemplateTrackingRepository
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC


@dataclass
class SetTemplateTrackingInput:
    project_id: UUID
    path: str
    # False — «больше не отслеживать»: обновления шаблона этот файл не трогают.
    tracked: bool


@dataclass
class SetTemplateTrackingOutput:
    state: TemplateTrackingState


def _normalize(path: str) -> str:
    normalized = posixpath.normpath(path.replace("\\", "/")).lstrip("/")
    if normalized in ("", ".") or normalized.startswith("../") or normalized.startswith(".hse-studio/"):
        raise ValueError(localized_error(f"Недопустимый путь: {path!r}", f"Invalid path: {path!r}"))
    return normalized


class SetTemplateTrackingUC:
    """Снять файл с отслеживания шаблоном (или вернуть): для файлов, переписанных
    пользователем целиком, чтобы обновления о них больше не спрашивали."""

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        tracking_repo: ITemplateTrackingRepository,
    ) -> None:
        self._get_uc = GetProjectUC(project_repo, project_index_repo)
        self._tracking = tracking_repo

    async def execute(self, inp: SetTemplateTrackingInput) -> SetTemplateTrackingOutput:
        project = (await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))).project
        path = _normalize(inp.path)
        state = self._tracking.get(project.folder)
        ignored = state.ignored - {path} if inp.tracked else state.ignored | {path}
        new_state = replace(state, ignored=frozenset(ignored))
        if new_state != state:
            self._tracking.save(project.folder, new_state)
        return SetTemplateTrackingOutput(state=new_state)
