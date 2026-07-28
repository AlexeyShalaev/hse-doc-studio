from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import IProjectRepository


@dataclass
class InspectFolderInput:
    path: str


@dataclass
class InspectFolderOutput:
    resolved_path: Path
    exists: bool
    is_dir: bool
    has_project: bool
    project: Project | None


class InspectFolderUC:
    """Inspect a filesystem path: does it exist, is it a folder, is it a project?"""

    def __init__(self, project_repo: IProjectRepository) -> None:
        self._project_repo = project_repo

    async def execute(self, inp: InspectFolderInput) -> InspectFolderOutput:
        target = Path(inp.path).expanduser()
        try:
            target = target.resolve(strict=False)
        except OSError as exc:
            raise ValueError(
                localized_error(f"Не удалось разрешить путь: '{inp.path}'", f"Cannot resolve path: '{inp.path}'")
            ) from exc

        exists = target.exists()
        is_dir = exists and target.is_dir()

        project: Project | None = None
        if is_dir:
            project = self._project_repo.get(target)

        return InspectFolderOutput(
            resolved_path=target,
            exists=exists,
            is_dir=is_dir,
            has_project=project is not None,
            project=project,
        )
