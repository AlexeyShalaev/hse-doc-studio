from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import structlog

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.git_sync.protocols import IGitRemoteRegistry
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.vcs.protocols import IVcsService
from hse_doc_studio.use_cases.vcs.excludes import project_vcs_exclude

logger = structlog.get_logger()


@dataclass
class ConnectProjectInput:
    folder: Path


@dataclass
class ConnectProjectOutput:
    project: Project


class ConnectProjectUC:
    """Register a folder that already contains a project as known.

    Reads metadata from <folder>/.hse-studio/project.json; user does not pass
    pack/template/etc. — that information must already be inside the folder.
    """

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        vcs_service: IVcsService,
        template_repo: ITemplateRepository | None = None,
        git_remotes: IGitRemoteRegistry | None = None,
    ) -> None:
        self._project_repo = project_repo
        self._project_index_repo = project_index_repo
        self._vcs = vcs_service
        self._template_repo = template_repo
        self._git_remotes = git_remotes

    async def execute(self, inp: ConnectProjectInput) -> ConnectProjectOutput:
        folder = inp.folder.expanduser().resolve()

        if not folder.exists():
            raise NotFoundError(
                localized_error(f"Папка '{folder}' не существует.", f"Folder '{folder}' does not exist.")
            )
        if not folder.is_dir():
            raise NotADirectoryError(
                localized_error(f"'{folder}' не является папкой.", f"'{folder}' is not a directory.")
            )

        project = self._project_repo.get(folder)
        if project is None:
            raise ValueError(
                localized_error(
                    f"Папка '{folder}' не является проектом HSE Studio "
                    f"(отсутствует .hse-studio/project.json). Вместо этого создайте новый проект здесь.",
                    f"Folder '{folder}' is not an HSE Studio project "
                    f"(missing .hse-studio/project.json). Create a new project here instead.",
                )
            )

        # Idempotent: register() is a no-op for an already-known folder. We
        # always return the project so the UI can navigate into it, mirroring
        # IDE "open project" semantics.
        self._project_index_repo.register(folder)
        if self._git_remotes is not None:
            # Папку скопировали с другого компьютера вместе с хранилищем, где уже записан репозиторий: фоновая
            # выборка должна подхватить её сразу, а не после перезапуска, когда реестр просматривается заново.
            await asyncio.to_thread(self._git_remotes.consider, folder)

        # Ensure the isolated VCS store exists (recreate if the user deleted it).
        # Best-effort: never block connecting a project on a VCS hiccup.
        try:
            if self._vcs.is_available(project) and not self._vcs.is_initialized(project):
                await asyncio.to_thread(self._vcs.init, project, project_vcs_exclude(project, self._template_repo))
        except Exception as exc:  # noqa: BLE001
            logger.warning("vcs init failed on connect", project_id=str(project.id), exc=str(exc))

        logger.info(
            "project connected",
            project_id=str(project.id),
            folder=str(folder),
        )
        return ConnectProjectOutput(project=project)
