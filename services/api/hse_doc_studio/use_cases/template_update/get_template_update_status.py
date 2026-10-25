from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import TemplateUpdateClass, TemplateVersionStatus
from hse_doc_studio.core.repositories import IProjectIndexRepository, IProjectRepository, ITemplateRepository
from hse_doc_studio.core.template_update.entities import TemplateUpdateRecord
from hse_doc_studio.core.template_update.protocols import ITemplateTrackingRepository, IUpdateJournalRepository
from hse_doc_studio.core.template_update.text import has_conflict_markers
from hse_doc_studio.core.template_versions import parse_version_key
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC
from hse_doc_studio.use_cases.template_update.planning import update_class


@dataclass(frozen=True)
class AvailableUpdate:
    version: TemplateVersion
    update_class: TemplateUpdateClass | None


@dataclass
class GetTemplateUpdateStatusInput:
    project_id: UUID


@dataclass
class GetTemplateUpdateStatusOutput:
    project: Project
    current: TemplateVersion | None
    # Проект создан на содержимом версии, отличном от выпущенного (dev-сборка).
    digest_mismatch: bool
    # Более новые выпущенные версии того же шаблона, по возрастанию.
    available: list[AvailableUpdate]
    # Что предложить первым: последний patch, иначе последний minor, иначе major.
    recommended: AvailableUpdate | None
    last_update: TemplateUpdateRecord | None
    # Файлы последнего обновления, где ещё остались маркеры конфликта.
    unresolved_markers: list[str]
    in_progress: bool


class GetTemplateUpdateStatusUC:
    """Версия шаблона проекта, доступные обновления и последнее применённое."""

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        tracking_repo: ITemplateTrackingRepository,
        journal_repo: IUpdateJournalRepository,
    ) -> None:
        self._get_uc = GetProjectUC(project_repo, project_index_repo)
        self._template_repo = template_repo
        self._tracking = tracking_repo
        self._journals = journal_repo

    async def execute(self, inp: GetTemplateUpdateStatusInput) -> GetTemplateUpdateStatusOutput:
        project = (await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))).project
        lock = project.lock
        current = self._template_repo.get_version(lock.pack_id, lock.template_id, lock.version)
        available = self._available(project, current) if current is not None else []
        tracking = self._tracking.get(project.folder)
        last = tracking.last_applied()
        return GetTemplateUpdateStatusOutput(
            project=project,
            current=current,
            digest_mismatch=bool(
                current is not None and current.frozen_digest and lock.digest and lock.digest != current.frozen_digest
            ),
            available=available,
            recommended=_recommended(current, available),
            last_update=last,
            unresolved_markers=_unresolved(project, last),
            in_progress=self._journals.get(project.folder) is not None,
        )

    def _available(self, project: Project, current: TemplateVersion) -> list[AvailableUpdate]:
        current_key = parse_version_key(current.version)
        if current_key is None:
            return []
        candidates: list[tuple[tuple[int, int, int], TemplateVersion]] = []
        for version_id in self._template_repo.list_versions(project.lock.pack_id, project.lock.template_id):
            key = parse_version_key(version_id)
            if key is None or key <= current_key:
                continue
            version = self._template_repo.get_version(project.lock.pack_id, project.lock.template_id, version_id)
            if version is not None and version.status == TemplateVersionStatus.stable:
                candidates.append((key, version))
        return [
            AvailableUpdate(version=version, update_class=update_class(self._template_repo, current, version))
            for _key, version in sorted(candidates, key=lambda item: item[0])
        ]


def _recommended(current: TemplateVersion | None, available: list[AvailableUpdate]) -> AvailableUpdate | None:
    if current is None or not available:
        return None
    for wanted in (TemplateUpdateClass.patch, TemplateUpdateClass.minor):
        same_class = [u for u in available if u.update_class == wanted]
        if same_class:
            return same_class[-1]
    return available[-1]


def _unresolved(project: Project, record: TemplateUpdateRecord | None) -> list[str]:
    if record is None:
        return []
    unresolved: list[str] = []
    for rel in record.markers:
        path = project.folder / rel
        if path.is_file() and has_conflict_markers(path.read_bytes()):
            unresolved.append(rel)
    return unresolved
