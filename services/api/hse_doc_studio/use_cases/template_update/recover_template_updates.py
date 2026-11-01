from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import structlog

from hse_doc_studio.core.projects.locator import IProjectLocator
from hse_doc_studio.core.repositories import IProjectRepository
from hse_doc_studio.core.template_update.entities import UpdateJournalKind
from hse_doc_studio.core.template_update.protocols import ITemplateBaseStore, IUpdateJournalRepository
from hse_doc_studio.core.vcs.protocols import IVcsService
from hse_doc_studio.use_cases.template_update.transaction import TemplateUpdateTransaction, sync_transaction

logger = structlog.get_logger()


@dataclass
class RecoveredUpdate:
    folder: Path
    update_id: str
    # True — коммит обновления успел записаться, обновление доведено; False — откат.
    finalized: bool
    kind: UpdateJournalKind = UpdateJournalKind.template


@dataclass
class RecoverTemplateUpdatesOutput:
    recovered: list[RecoveredUpdate]


class RecoverTemplateUpdatesUC:
    """При старте: разобраться с обновлениями шаблона и слияниями синхронизации, прерванными падением процесса.

    Журнал остаётся только у прерванной операции (успешная и упавшая с
    исключением его убирают сами). По журналу проект либо возвращается ровно в
    состояние до неё, либо — если коммит уже сделан — операция доводится.
    Вид журнала (`kind`) выбирает, как узнать, что коммит сделан.
    """

    def __init__(
        self,
        project_repo: IProjectRepository,
        locator: IProjectLocator,
        journal_repo: IUpdateJournalRepository,
        base_store: ITemplateBaseStore,
        vcs_service: IVcsService,
    ) -> None:
        self._project_repo = project_repo
        self._locator = locator
        self._journals = journal_repo
        self._transactions = {
            UpdateJournalKind.template: TemplateUpdateTransaction(journal_repo, base_store, vcs_service),
            UpdateJournalKind.sync: sync_transaction(journal_repo, base_store, vcs_service),
        }

    async def execute(self) -> RecoverTemplateUpdatesOutput:
        known = await self._locator.list_all()
        return await asyncio.to_thread(self._recover_all, known)

    def _recover_all(self, known: list[Path]) -> RecoverTemplateUpdatesOutput:
        recovered: list[RecoveredUpdate] = []
        for folder in self._journals.list_active(known):
            project = self._project_repo.get(folder)
            journal = self._journals.get(folder)
            if project is None or journal is None:
                logger.warning("interrupted update journal left as is", folder=str(folder))
                continue
            try:
                finalized = self._transactions[journal.kind].recover(project, journal)
            except Exception as exc:  # noqa: BLE001 — один проект не должен мешать остальным
                logger.warning("interrupted update recovery failed", folder=str(folder), exc=str(exc))
                continue
            recovered.append(
                RecoveredUpdate(folder=folder, update_id=journal.id, finalized=finalized, kind=journal.kind)
            )
        return RecoverTemplateUpdatesOutput(recovered=recovered)
