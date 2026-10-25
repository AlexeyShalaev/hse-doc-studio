from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import ConflictResolution, TemplateBaseProvenance
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import IProjectIndexRepository, IProjectRepository, ITemplateRepository
from hse_doc_studio.core.template_update.entities import FileWriteKind, TemplateBase, resolve_op
from hse_doc_studio.core.template_update.layout import doc_resolver
from hse_doc_studio.core.template_update.protocols import ITemplateTrackingRepository
from hse_doc_studio.core.template_update.text import is_binary, same_content, unified_diff
from hse_doc_studio.core.vcs.protocols import IVcsFolderLocks
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC
from hse_doc_studio.use_cases.template_update.base_service import TemplateBaseService
from hse_doc_studio.use_cases.template_update.planning import (
    TemplateUpdatePlanner,
    current_version,
    read_project_files,
)


class TemplateFileStatus(StrEnum):
    modified = "modified"  # пользователь правил файл шаблона
    deleted = "deleted"  # пользователь удалил файл шаблона


@dataclass(frozen=True)
class TemplateFileState:
    path: str
    status: TemplateFileStatus
    doc_id: str | None
    binary: bool
    approximate: bool
    ignored: bool


@dataclass
class CompareWithTemplateInput:
    project_id: UUID


@dataclass
class CompareWithTemplateOutput:
    version: str
    provenance: TemplateBaseProvenance
    files: list[TemplateFileState]


class CompareWithTemplateUC:
    """«Сравнить с шаблоном»: какие файлы шаблона пользователь правил или удалил.

    Полезно само по себе (что я поменял относительно шаблона) и до всякого
    обновления проверяет восстановление базы на реальных проектах.
    """

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        base_service: TemplateBaseService,
        tracking_repo: ITemplateTrackingRepository,
        vcs_locks: IVcsFolderLocks,
    ) -> None:
        self._get_uc = GetProjectUC(project_repo, project_index_repo)
        self._template_repo = template_repo
        self._bases = base_service
        self._tracking = tracking_repo
        self._locks = vcs_locks

    async def execute(self, inp: CompareWithTemplateInput) -> CompareWithTemplateOutput:
        project = (await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))).project
        async with self._locks.for_folder(project.folder):
            return await asyncio.to_thread(self._compare, project)

    def _compare(self, project: Project) -> CompareWithTemplateOutput:
        version = current_version(self._template_repo, project)
        base = self._bases.load_or_reconstruct(project, version)
        ours = read_project_files(project.folder, base.files)
        ignored = self._tracking.get(project.folder).ignored
        doc_of = doc_resolver(project, version)
        files: list[TemplateFileState] = []
        for path in sorted(base.files):
            content = ours.get(path)
            if content is not None and same_content(path, content, base.files[path]):
                continue
            files.append(
                TemplateFileState(
                    path=path,
                    status=TemplateFileStatus.deleted if content is None else TemplateFileStatus.modified,
                    doc_id=doc_of(path),
                    binary=is_binary(path, base.files[path], content),
                    approximate=path in base.approximate_paths,
                    ignored=path in ignored,
                )
            )
        return CompareWithTemplateOutput(version=version.version, provenance=base.provenance, files=files)


class TemplateDiffView(StrEnum):
    template = "template"  # что меняет шаблон: база → новая версия
    mine = "mine"  # мои правки: база → диск
    result = "result"  # что получится: диск → итог обновления


@dataclass
class GetTemplateFileDiffInput:
    project_id: UUID
    path: str
    view: TemplateDiffView
    # None — сравнение с текущей версией шаблона (только view=mine).
    to_version: str | None = None
    resolution: ConflictResolution | None = None


@dataclass
class GetTemplateFileDiffOutput:
    path: str
    binary: bool
    patch: str
    truncated: bool


class GetTemplateFileDiffUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        base_service: TemplateBaseService,
        planner: TemplateUpdatePlanner,
        vcs_locks: IVcsFolderLocks,
    ) -> None:
        self._get_uc = GetProjectUC(project_repo, project_index_repo)
        self._template_repo = template_repo
        self._bases = base_service
        self._planner = planner
        self._locks = vcs_locks

    async def execute(self, inp: GetTemplateFileDiffInput) -> GetTemplateFileDiffOutput:
        project = (await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))).project
        async with self._locks.for_folder(project.folder):
            return await asyncio.to_thread(self._diff, project, inp)

    def _diff(self, project: Project, inp: GetTemplateFileDiffInput) -> GetTemplateFileDiffOutput:
        if inp.to_version is None:
            base = self._bases.load_or_reconstruct(project, current_version(self._template_repo, project))
            return _render_diff(inp.path, base, read_project_files(project.folder, [inp.path]).get(inp.path))
        plan = self._planner.plan(project, inp.to_version).plan
        op = plan.op(inp.path)
        if op is None:
            raise ValueError(
                localized_error(
                    f"Обновление не меняет файл {inp.path}.",
                    f"The update does not change {inp.path}.",
                )
            )
        if op.binary:
            return GetTemplateFileDiffOutput(path=op.path, binary=True, patch="", truncated=False)
        if inp.view == TemplateDiffView.template:
            patch, truncated = unified_diff(op.path, op.base, op.theirs, "template-was", "template-now")
        elif inp.view == TemplateDiffView.mine:
            patch, truncated = unified_diff(op.path, op.base, op.ours, "template", "mine")
        else:
            write = resolve_op(op, inp.resolution)
            result = op.ours if write is None else (write.content if write.kind == FileWriteKind.write else None)
            patch, truncated = unified_diff(op.path, op.ours, result, "mine", "result")
        return GetTemplateFileDiffOutput(path=op.path, binary=False, patch=patch, truncated=truncated)


def _render_diff(path: str, base: TemplateBase, ours: bytes | None) -> GetTemplateFileDiffOutput:
    original = base.files.get(path)
    if original is None:
        raise ValueError(localized_error(f"{path} — не файл шаблона.", f"{path} is not a template file."))
    if is_binary(path, original, ours):
        return GetTemplateFileDiffOutput(path=path, binary=True, patch="", truncated=False)
    patch, truncated = unified_diff(path, original, ours, "template", "mine")
    return GetTemplateFileDiffOutput(path=path, binary=False, patch=patch, truncated=truncated)
