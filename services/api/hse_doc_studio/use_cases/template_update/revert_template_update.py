from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from uuid import UUID

import structlog

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import ConflictResolution
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import IProjectIndexRepository, IProjectRepository, ITemplateRepository
from hse_doc_studio.core.template_update.entities import (
    FileOp,
    FileWriteKind,
    TemplateTrackingState,
    TemplateUpdateRecord,
    resolve_op,
)
from hse_doc_studio.core.template_update.errors import (
    TemplateUpdateNotRevertibleError,
)
from hse_doc_studio.core.template_update.layout import doc_resolver
from hse_doc_studio.core.template_update.planner import PlanInput, plan_files
from hse_doc_studio.core.template_update.protocols import (
    IMergeEngine,
    ITemplateBaseStore,
    ITemplateTrackingRepository,
    IUpdateJournalRepository,
)
from hse_doc_studio.core.vcs.protocols import IVcsFolderLocks, IVcsService
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC
from hse_doc_studio.use_cases.template_update.planning import read_project_files
from hse_doc_studio.use_cases.template_update.support import (
    ensure_history,
    ensure_no_active_journal,
    lock_for,
    pre_update_snapshot,
)
from hse_doc_studio.use_cases.template_update.transaction import (
    UPDATE_TRAILER,
    TemplateUpdateTransaction,
    now_iso,
)

logger = structlog.get_logger()

_STUDIO_PREFIX = ".hse-studio/"


@dataclass
class RevertTemplateUpdateInput:
    project_id: UUID
    # Какое обновление отменить; None — последнее применённое.
    update_id: str | None = None
    dry_run: bool = False
    resolutions: dict[str, ConflictResolution] = field(default_factory=dict)


@dataclass
class RevertTemplateUpdateOutput:
    record: TemplateUpdateRecord
    ops: list[FileOp]
    applied: bool
    # Файлы, где отмена столкнулась с правками после обновления и оставила их как есть.
    kept: list[str]


class RevertTemplateUpdateUC:
    """Отменить обновление шаблона, сохранив правки, сделанные после него.

    Отмена — то же трёхстороннее слияние в обратную сторону: база — файлы
    сразу после обновления, «шаблон» — файлы до него, «моё» — диск. Нетронутые
    после обновления файлы возвращаются к прежнему содержимому байт в байт;
    там, где пользователь уже правил поверх, по умолчанию остаётся его вариант.
    lock возвращается на прежнюю версию; её база в истории сохранилась.
    """

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        base_store: ITemplateBaseStore,
        merge_engine: IMergeEngine,
        tracking_repo: ITemplateTrackingRepository,
        journal_repo: IUpdateJournalRepository,
        vcs_service: IVcsService,
        vcs_locks: IVcsFolderLocks,
    ) -> None:
        self._project_repo = project_repo
        self._get_uc = GetProjectUC(project_repo, project_index_repo)
        self._template_repo = template_repo
        self._store = base_store
        self._merge = merge_engine
        self._tracking = tracking_repo
        self._journals = journal_repo
        self._vcs = vcs_service
        self._locks = vcs_locks
        self._transaction = TemplateUpdateTransaction(journal_repo, base_store, vcs_service)

    async def execute(self, inp: RevertTemplateUpdateInput) -> RevertTemplateUpdateOutput:
        project = (await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))).project
        async with self._locks.for_folder(project.folder):
            return await asyncio.to_thread(self._revert, project, inp)

    def _not_revertible(self) -> TemplateUpdateNotRevertibleError:
        return TemplateUpdateNotRevertibleError(
            localized_error(
                "Это обновление шаблона нельзя отменить: его нет в истории текущей ветки.",
                "This template update cannot be reverted: it is not in the current branch history.",
            )
        )

    def _find(self, tracking: TemplateTrackingState, update_id: str | None) -> TemplateUpdateRecord:
        if update_id is None:
            record = tracking.last_applied()
        else:
            record = next((r for r in tracking.history if r.id == update_id), None)
        if record is None or record.reverted or record.reverts is not None:
            raise self._not_revertible()
        return record

    def _revert(self, project: Project, inp: RevertTemplateUpdateInput) -> RevertTemplateUpdateOutput:
        ensure_no_active_journal(self._journals, project)
        tracking = self._tracking.get(project.folder)
        record = self._find(tracking, inp.update_id)
        update_commit = self._store.find_commit(project, UPDATE_TRAILER, record.id)
        if update_commit is None or not self._store.is_ancestor(project, record.pre_commit, update_commit):
            raise self._not_revertible()

        changed = self._store.changed_paths(project, record.pre_commit, update_commit)
        paths = [p for p in changed if not p.startswith(_STUDIO_PREFIX)]
        after = self._store.files_at(project, update_commit, paths)
        before = self._store.files_at(project, record.pre_commit, paths)
        version = self._template_repo.get_version(project.lock.pack_id, project.lock.template_id, record.from_version)
        ops = plan_files(
            PlanInput(base=after, theirs=before, ours=read_project_files(project.folder, paths)),
            self._merge.merge,
            doc_of=doc_resolver(project, version) if version is not None else lambda _p: None,
        )
        kept = sorted(op.path for op in ops if op.needs_decision and op.path not in inp.resolutions)
        if inp.dry_run:
            return RevertTemplateUpdateOutput(record=record, ops=ops, applied=False, kept=kept)

        writes = [w for w in (resolve_op(op, inp.resolutions.get(op.path)) for op in ops) if w is not None]
        if version is not None:
            ensure_history(self._vcs, project, version)
        label = f"отмена обновления шаблона {record.to_version} → {record.from_version}"
        pre_commit = pre_update_snapshot(self._vcs, self._store, project, label)
        journal = self._transaction.start_journal(
            from_version=record.to_version,
            to_version=record.from_version,
            pre_commit=pre_commit,
            base_commit=None,
            reverts=record.id,
        )
        revert_record = TemplateUpdateRecord(
            id=journal.id,
            from_version=record.to_version,
            to_version=record.from_version,
            at=now_iso(),
            pre_commit=pre_commit,
            markers=tuple(sorted(w.path for w in writes if w.with_markers)),
            reverts=record.id,
        )

        def save_state() -> None:
            if version is not None:
                project.lock = lock_for(project.lock, version, self._template_repo)
            else:
                project.lock = replace(project.lock, version=record.from_version, digest=None, min_studio=None)
            project.updated_at = datetime.now(tz=timezone.utc)
            self._project_repo.save(project)
            history = tuple(replace(r, reverted=True) if r.id == record.id else r for r in tracking.history)
            self._tracking.save(project.folder, replace(tracking, history=(*history, revert_record)))

        self._transaction.run(project, journal, writes, save_state=save_state, message=label.capitalize())
        logger.info(
            "template update reverted",
            project_id=str(project.id),
            update_id=record.id,
            files=len([w for w in writes if w.kind in (FileWriteKind.write, FileWriteKind.delete)]),
            kept=len(kept),
        )
        return RevertTemplateUpdateOutput(record=replace(record, reverted=True), ops=ops, applied=True, kept=kept)
