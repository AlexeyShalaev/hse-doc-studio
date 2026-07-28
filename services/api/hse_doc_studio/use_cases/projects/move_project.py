from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import structlog

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
)
from hse_doc_studio.infra.compile.compile_runner import CompileRunner
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()


@dataclass
class MoveProjectInput:
    project_id: UUID
    new_folder: Path


@dataclass
class MoveProjectOutput:
    project: Project


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


class MoveProjectUC:
    """Relocate a project's files to a new folder and update the index.

    The on-disk `project.json` does not store its own folder (it's derived from
    where it's loaded), so moving the tree + repointing the index is all that's
    needed — the project id and contents are preserved. Refuses while a build is
    in flight: that compile's docker container has the old folder bind-mounted,
    so moving it would corrupt the build.
    """

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        compile_runner: CompileRunner,
    ) -> None:
        self._project_repo = project_repo
        self._project_index_repo = project_index_repo
        self._compile_runner = compile_runner
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: MoveProjectInput) -> MoveProjectOutput:  # noqa: C901
        result = await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))
        project = result.project

        old = project.folder.resolve()
        new = inp.new_folder.expanduser().resolve()

        en = current_interface_language() is Lang.en

        if new == old:
            raise ValueError(
                "The new folder is the same as the current one." if en else "Новая папка совпадает с текущей."
            )
        if _is_within(new, old):
            raise ValueError(
                "A project cannot be moved inside its own folder."
                if en
                else "Нельзя перенести проект внутрь его же папки."
            )
        if _is_within(old, new):
            raise ValueError(
                "The target folder contains the project's current folder."
                if en
                else "Целевая папка содержит текущую папку проекта."
            )

        if self._compile_runner.has_active_for_folder(old):
            raise ValueError(
                "Wait for the active build to finish before moving the project."
                if en
                else "Дождитесь завершения активной сборки перед переносом проекта."
            )

        if new.exists() and any(new.iterdir()):
            raise ValueError(
                f"Folder '{new}' is not empty. Choose an empty or new folder."
                if en
                else f"Папка '{new}' не пуста. Выберите пустую или новую папку."
            )

        known_resolved = [p.resolve() for p in self._project_index_repo.list_known()]
        if new in known_resolved:
            raise ValueError(
                f"Folder '{new}' is already registered as a project."
                if en
                else f"Папка '{new}' уже зарегистрирована как проект."
            )

        # Move the tree. shutil.move renames within a device and copies+removes
        # across devices. When the (empty) target already exists, move children
        # into it and drop the old shell.
        new.parent.mkdir(parents=True, exist_ok=True)
        if new.exists():
            for entry in old.iterdir():
                shutil.move(str(entry), str(new / entry.name))
            try:
                old.rmdir()
            except OSError as exc:
                logger.warning("move_project: could not remove old folder shell", old=str(old), exc=str(exc))
        else:
            shutil.move(str(old), str(new))

        # Repoint the index: drop the old location, register the new one.
        self._project_index_repo.unregister(old)
        self._project_index_repo.register(new)

        # Reload from the new location and refresh updated_at so the move shows
        # up as activity. folder is set from the load path, not the JSON.
        moved = self._project_repo.get(new)
        if moved is None:
            raise NotFoundError(
                f"Project file not found after move at '{new}'."
                if en
                else f"Файл проекта не найден после переноса в '{new}'."
            )
        moved.updated_at = datetime.now(tz=timezone.utc)
        self._project_repo.save(moved)

        logger.info(
            "project moved",
            project_id=str(inp.project_id),
            old=str(old),
            new=str(new),
        )
        return MoveProjectOutput(project=moved)
