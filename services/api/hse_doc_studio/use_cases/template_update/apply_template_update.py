from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from uuid import UUID

import structlog

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import ConflictResolution, TemplateBaseProvenance
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import IProjectIndexRepository, IProjectRepository, ITemplateRepository
from hse_doc_studio.core.template_update.entities import (
    FileWriteKind,
    TemplateBase,
    TemplateTrackingState,
    TemplateUpdateRecord,
    resolve_op,
)
from hse_doc_studio.core.template_update.errors import (
    TemplateUpdatePlanOutdatedError,
)
from hse_doc_studio.core.template_update.protocols import (
    ITemplateBaseStore,
    ITemplateTrackingRepository,
    IUpdateJournalRepository,
)
from hse_doc_studio.core.vcs.protocols import IVcsFolderLocks, IVcsService
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC
from hse_doc_studio.use_cases.template_update.base_service import TemplateBaseService
from hse_doc_studio.use_cases.template_update.planning import TemplateUpdatePlanner
from hse_doc_studio.use_cases.template_update.support import (
    ensure_history,
    ensure_no_active_journal,
    lock_for,
    pre_update_snapshot,
)
from hse_doc_studio.use_cases.template_update.transaction import TemplateUpdateTransaction, now_iso

logger = structlog.get_logger()


@dataclass
class ApplyTemplateUpdateInput:
    project_id: UUID
    to_version: str
    fingerprint: str
    resolutions: dict[str, ConflictResolution] = field(default_factory=dict)


@dataclass
class ApplyTemplateUpdateOutput:
    record: TemplateUpdateRecord
    written: list[str]
    deleted: list[str]
    markers: list[str]


class ApplyTemplateUpdateUC:
    """Применить предпросмотренный план обновления шаблона.

    План пересобирается и сверяется по отпечатку с тем, что видел пользователь;
    решения по конфликтам — его (по умолчанию «оставить моё»). Запись — транзакция
    с журналом (TemplateUpdateTransaction), до неё — снимок истории и тег.
    """

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        planner: TemplateUpdatePlanner,
        base_service: TemplateBaseService,
        base_store: ITemplateBaseStore,
        tracking_repo: ITemplateTrackingRepository,
        journal_repo: IUpdateJournalRepository,
        vcs_service: IVcsService,
        vcs_locks: IVcsFolderLocks,
    ) -> None:
        self._project_repo = project_repo
        self._get_uc = GetProjectUC(project_repo, project_index_repo)
        self._template_repo = template_repo
        self._planner = planner
        self._bases = base_service
        self._store = base_store
        self._tracking = tracking_repo
        self._journals = journal_repo
        self._vcs = vcs_service
        self._locks = vcs_locks
        self._transaction = TemplateUpdateTransaction(journal_repo, base_store, vcs_service)

    async def execute(self, inp: ApplyTemplateUpdateInput) -> ApplyTemplateUpdateOutput:
        project = (await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))).project
        async with self._locks.for_folder(project.folder):
            return await asyncio.to_thread(self._apply, project, inp)

    def _apply(self, project: Project, inp: ApplyTemplateUpdateInput) -> ApplyTemplateUpdateOutput:
        ensure_no_active_journal(self._journals, project)
        planned = self._planner.plan(project, inp.to_version)
        if planned.plan.fingerprint != inp.fingerprint:
            raise TemplateUpdatePlanOutdatedError(
                localized_error(
                    "Проект изменился после предпросмотра — откройте предпросмотр заново.",
                    "The project changed after the preview — open the preview again.",
                )
            )
        plan = planned.plan
        writes = [w for w in (resolve_op(op, inp.resolutions.get(op.path)) for op in plan.ops) if w is not None]

        ensure_history(self._vcs, project, planned.target)
        label = f"обновление шаблона {plan.from_version} → {plan.to_version}"
        pre_commit = pre_update_snapshot(self._vcs, self._store, project, label)
        target_base = TemplateBase(
            version=planned.target.version,
            files=planned.theirs,
            provenance=TemplateBaseProvenance.recorded,
        )
        base_commit = self._store.save(
            project,
            target_base,
            message=f"Чистый рендер шаблона: {planned.target.pack_id}/{planned.target.template_id}@{plan.to_version}",
            set_ref=False,
        )
        journal = self._transaction.start_journal(
            from_version=plan.from_version, to_version=plan.to_version, pre_commit=pre_commit, base_commit=base_commit
        )
        markers = sorted(w.path for w in writes if w.with_markers)
        record = TemplateUpdateRecord(
            id=journal.id,
            from_version=plan.from_version,
            to_version=plan.to_version,
            at=now_iso(),
            pre_commit=pre_commit,
            markers=tuple(markers),
        )

        def save_state() -> None:
            project.lock = lock_for(project.lock, planned.target, self._template_repo)
            project.updated_at = datetime.now(tz=timezone.utc)
            self._project_repo.save(project)
            self._tracking.save(project.folder, _with_record(planned.tracking, record))

        commit = self._transaction.run(project, journal, writes, save_state=save_state, message=label.capitalize())
        logger.info(
            "template update applied",
            project_id=str(project.id),
            from_version=plan.from_version,
            to_version=plan.to_version,
            files=len(writes),
            markers=len(markers),
        )
        return ApplyTemplateUpdateOutput(
            record=replace(record, commit=commit),
            written=sorted(w.path for w in writes if w.kind == FileWriteKind.write),
            deleted=sorted(w.path for w in writes if w.kind == FileWriteKind.delete),
            markers=markers,
        )


def _with_record(state: TemplateTrackingState, record: TemplateUpdateRecord) -> TemplateTrackingState:
    return replace(state, history=(*state.history, record))
