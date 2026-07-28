from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

import structlog

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.team import nda_bases, prefix_path
from hse_doc_studio.infra.project_init.template_renderer import instantiate_nda

logger = structlog.get_logger()


@dataclass
class NdaInput:
    project_id: UUID


@dataclass
class NdaStatusOutput:
    available: bool  # the template declares an NDA file group
    present: bool  # the project currently has NDA files on disk
    files: list[str] = field(default_factory=list)


def _resolve(
    project_id: UUID,
    project_repo: IProjectRepository,
    project_index_repo: IProjectIndexRepository,
) -> tuple[Path, Project]:
    for folder in project_index_repo.list_known():
        try:
            project = project_repo.get(folder)
        except Exception as exc:
            logger.warning("manage_nda: error loading project", folder=str(folder), exc=str(exc))
            continue
        if project is not None and project.id == project_id:
            return folder, project
    raise NotFoundError(localized_error(f"Проект {project_id!r} не найден", f"Project {project_id!r} not found"))


def _status(folder: Path, project: Project, template_repo: ITemplateRepository) -> NdaStatusOutput:
    version = template_repo.get_version(
        project.lock.pack_id,
        project.lock.template_id,
        project.lock.version,
    )
    nda_cfg = version.nda if version is not None else None
    if nda_cfg is None:
        return NdaStatusOutput(available=False, present=False, files=[])
    # Расписка NDA персональна: в команде она лежит в папке каждого автора
    # (project/<slug>/nda/…), в solo — в корне. Собираем со всех баз.
    files: list[str] = []
    for base_dir, _author in nda_bases(project):
        nda_dir = folder / prefix_path(base_dir, nda_cfg.source_dir)
        if nda_dir.exists():
            # Paths relative to the PROJECT folder (e.g. "nda/Расписка.md" or
            # "shalaev/nda/Расписка.md") so the frontend can build an absolute
            # path (project.folder + file) to open each NDA file externally.
            files.extend(p.relative_to(folder).as_posix() for p in nda_dir.rglob("*") if p.is_file())
    return NdaStatusOutput(available=True, present=bool(files), files=sorted(files))


class GetNdaStatusUC:
    """Whether the template offers NDA files and whether the project has any.

    Drives the settings UI: enabling NDA on a template without an NDA group
    surfaces an "add your own files" hint; disabling NDA while files exist
    prompts the user to keep or delete them.
    """

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
    ) -> None:
        self._project_repo = project_repo
        self._project_index_repo = project_index_repo
        self._template_repo = template_repo

    async def execute(self, inp: NdaInput) -> NdaStatusOutput:
        folder, project = _resolve(inp.project_id, self._project_repo, self._project_index_repo)
        return _status(folder, project, self._template_repo)


class InstantiateNdaUC:
    """Materialise the template's NDA files into the project (idempotent).

    Reuses `instantiate_nda`, which only acts when `meta.nda` is set — the
    caller (settings) flips the flag via PATCH first, then calls this so the
    files appear immediately instead of waiting for the next compile.
    """

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
    ) -> None:
        self._project_repo = project_repo
        self._project_index_repo = project_index_repo
        self._template_repo = template_repo

    async def execute(self, inp: NdaInput) -> NdaStatusOutput:
        folder, project = _resolve(inp.project_id, self._project_repo, self._project_index_repo)
        version = self._template_repo.get_version(
            project.lock.pack_id,
            project.lock.template_id,
            project.lock.version,
        )
        if version is not None:
            instantiate_nda(project, version, self._template_repo)
        return _status(folder, project, self._template_repo)


class DeleteNdaFilesUC:
    """Remove the project's NDA folder.

    Used when the student disables NDA and chooses to delete the files rather
    than keep them for a later re-enable. Leaves the `meta.nda` flag alone —
    that is managed via the project PATCH endpoint.
    """

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
    ) -> None:
        self._project_repo = project_repo
        self._project_index_repo = project_index_repo
        self._template_repo = template_repo

    async def execute(self, inp: NdaInput) -> NdaStatusOutput:
        folder, project = _resolve(inp.project_id, self._project_repo, self._project_index_repo)
        version = self._template_repo.get_version(
            project.lock.pack_id,
            project.lock.template_id,
            project.lock.version,
        )
        nda_cfg = version.nda if version is not None else None
        if nda_cfg is not None:
            # Удаляем расписку со всех персональных баз (в команде — из папки
            # каждого автора, в solo — из корня).
            for base_dir, _author in nda_bases(project):
                nda_dir = folder / prefix_path(base_dir, nda_cfg.source_dir)
                if nda_dir.exists():
                    shutil.rmtree(nda_dir, ignore_errors=True)
                    logger.debug("nda files deleted", folder=str(folder), nda_dir=str(nda_dir))
        return _status(folder, project, self._template_repo)
