"""Сборка плана обновления проекта на версию шаблона (общая часть use case'ов).

План строится всегда одинаково — для предпросмотра, применения и CLI: база
текущей версии, чистый рендер целевой с текущими данными проекта, файлы на
диске. Применение пересобирает план и сверяет отпечаток с тем, что видел
пользователь: если что-то изменилось, план устарел.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import TemplateBaseProvenance, TemplateUpdateClass
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import ISignatureRepository, ITemplateRepository
from hse_doc_studio.core.team import is_team
from hse_doc_studio.core.template_update.entities import (
    FileOp,
    TemplateBase,
    TemplateTrackingState,
    UpdatePlan,
    UpdateWarning,
    UpdateWarningCode,
)
from hse_doc_studio.core.template_update.errors import TemplateVersionUnavailableError
from hse_doc_studio.core.template_update.layout import doc_resolver
from hse_doc_studio.core.template_update.planner import PlanInput, plan_files, plan_fingerprint
from hse_doc_studio.core.template_update.protocols import IMergeEngine, ITemplateTrackingRepository
from hse_doc_studio.core.template_versions import classify_update, parse_version_key, stricter
from hse_doc_studio.use_cases.template_update.base_service import TemplateBaseService


@dataclass(frozen=True)
class PlannedUpdate:
    project: Project
    current: TemplateVersion
    target: TemplateVersion
    base: TemplateBase
    # Чистый рендер целевой версии с текущими данными — база проекта после обновления.
    theirs: Mapping[str, bytes]
    tracking: TemplateTrackingState
    plan: UpdatePlan


def current_version(template_repo: ITemplateRepository, project: Project) -> TemplateVersion:
    version = template_repo.get_version(project.lock.pack_id, project.lock.template_id, project.lock.version)
    if version is None:
        raise TemplateVersionUnavailableError(
            localized_error(
                f"Версии шаблона проекта ({project.lock.version}) нет в этой Студии.",
                f"The project's template version ({project.lock.version}) is not available in this Studio.",
            )
        )
    return version


def target_version(template_repo: ITemplateRepository, project: Project, version_id: str) -> TemplateVersion:
    version = template_repo.get_version(project.lock.pack_id, project.lock.template_id, version_id)
    if version is None:
        raise TemplateVersionUnavailableError(
            localized_error(
                f"Версии шаблона {version_id} нет в этой Студии.",
                f"Template version {version_id} is not available in this Studio.",
            )
        )
    return version


def update_class(
    template_repo: ITemplateRepository, current: TemplateVersion, target: TemplateVersion
) -> TemplateUpdateClass | None:
    """Класс перехода: по номерам, но не мягче объявленного версиями по пути."""
    result = classify_update(current.version, target.version)
    current_key = parse_version_key(current.version)
    target_key = parse_version_key(target.version)
    if current_key is None or target_key is None:
        return result
    for version_id in template_repo.list_versions(current.pack_id, current.template_id):
        key = parse_version_key(version_id)
        if key is None or not current_key < key <= target_key:
            continue
        version = template_repo.get_version(current.pack_id, current.template_id, version_id)
        if version is not None:
            result = stricter(result, version.release_kind)
    return result


def read_project_files(folder: Path, paths: Iterable[str]) -> dict[str, bytes]:
    """Содержимое файлов проекта на диске; отсутствующих (и каталогов) нет в ответе."""
    files: dict[str, bytes] = {}
    for rel in paths:
        path = folder / rel
        if path.is_file():
            files[rel] = path.read_bytes()
    return files


def base_digest(base: TemplateBase) -> str:
    digest = hashlib.sha256()
    for path in sorted(base.files):
        digest.update(f"{path}\0{hashlib.sha256(base.files[path]).hexdigest()}\n".encode())
    return digest.hexdigest()


class TemplateUpdatePlanner:
    def __init__(
        self,
        template_repo: ITemplateRepository,
        base_service: TemplateBaseService,
        merge_engine: IMergeEngine,
        tracking_repo: ITemplateTrackingRepository,
        signature_repo: ISignatureRepository,
    ) -> None:
        self._template_repo = template_repo
        self._bases = base_service
        self._merge = merge_engine
        self._tracking = tracking_repo
        self._signatures = signature_repo

    def plan(self, project: Project, to_version: str, *, persist_base: bool = True) -> PlannedUpdate:
        current = current_version(self._template_repo, project)
        target = target_version(self._template_repo, project, to_version)
        base = self._bases.load_or_reconstruct(project, current, persist=persist_base)
        theirs = self._bases.render(project, target)
        tracking = self._tracking.get(project.folder)
        ours = read_project_files(project.folder, set(base.files) | set(theirs))
        ops = plan_files(
            PlanInput(
                base=base.files,
                theirs=theirs,
                ours=ours,
                ignored=tracking.ignored,
                approximate=base.approximate_paths,
            ),
            self._merge.merge,
            doc_of=doc_resolver(project, target),
        )
        plan = UpdatePlan(
            from_version=current.version,
            to_version=target.version,
            update_class=update_class(self._template_repo, current, target),
            provenance=base.provenance,
            base_commit=base.commit,
            ops=tuple(ops),
            fingerprint=plan_fingerprint(
                ops, to_version=target.version, base_digest=base_digest(base), ignored=tracking.ignored
            ),
            warnings=self._warnings(project, base, ops),
        )
        return PlannedUpdate(project, current, target, base, theirs, tracking, plan)

    def _warnings(self, project: Project, base: TemplateBase, ops: list[FileOp]) -> tuple[UpdateWarning, ...]:
        warnings: list[UpdateWarning] = []
        if base.provenance == TemplateBaseProvenance.approximate or any(op.approximate_base for op in ops):
            warnings.append(UpdateWarning(UpdateWarningCode.approximate_base))
        touched = {op.doc_id for op in ops if op.doc_id}
        signatures = self._signatures.get_state(project.folder)
        frozen = sorted(touched & (set(signatures.frozen) | set(signatures.detached)))
        if frozen:
            warnings.append(UpdateWarning(UpdateWarningCode.frozen_documents, tuple(frozen)))
        placed = sorted(
            doc_id
            for doc_id in touched
            if any(placement.enabled for placement in signatures.placements.get(doc_id, {}).values())
        )
        if placed:
            warnings.append(UpdateWarning(UpdateWarningCode.signature_placements, tuple(placed)))
        if is_team(project):
            warnings.append(UpdateWarning(UpdateWarningCode.team_project))
        return tuple(warnings)
