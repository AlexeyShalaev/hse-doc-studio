from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import structlog

from hse_doc_studio.core.repositories import IProjectIndexRepository, IProjectRepository
from hse_doc_studio.core.template_update.protocols import ITemplateBaseStore, IUpdateJournalRepository
from hse_doc_studio.core.vcs.protocols import IVcsService
from hse_doc_studio.use_cases.template_update.transaction import TemplateUpdateTransaction

logger = structlog.get_logger()


@dataclass
class RecoveredUpdate:
    folder: Path
    update_id: str
    # True — коммит обновления успел записаться, обновление доведено; False — откат.
    finalized: bool


@dataclass
class RecoverTemplateUpdatesOutput:
    recovered: list[RecoveredUpdate]


class RecoverTemplateUpdatesUC:
    """При старте: разобраться с обновлениями шаблона, прерванными падением процесса.

    Журнал остаётся только у прерванного обновления (успешное и упавшее с
    исключением его убирают сами). По журналу проект либо возвращается ровно в
    состояние до обновления, либо — если коммит уже сделан — обновление доводится.
    """

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        journal_repo: IUpdateJournalRepository,
        base_store: ITemplateBaseStore,
        vcs_service: IVcsService,
    ) -> None:
        self._project_repo = project_repo
        self._index = project_index_repo
        self._journals = journal_repo
        self._transaction = TemplateUpdateTransaction(journal_repo, base_store, vcs_service)

    async def execute(self) -> RecoverTemplateUpdatesOutput:
        return await asyncio.to_thread(self._recover_all)

    def _recover_all(self) -> RecoverTemplateUpdatesOutput:
        recovered: list[RecoveredUpdate] = []
        for folder in self._journals.list_active(self._index.list_known()):
            project = self._project_repo.get(folder)
            journal = self._journals.get(folder)
            if project is None or journal is None:
                logger.warning("interrupted template update left as is", folder=str(folder))
                continue
            try:
                finalized = self._transaction.recover(project, journal)
            except Exception as exc:  # noqa: BLE001 — один проект не должен мешать остальным
                logger.warning("interrupted template update recovery failed", folder=str(folder), exc=str(exc))
                continue
            recovered.append(RecoveredUpdate(folder=folder, update_id=journal.id, finalized=finalized))
        return RecoverTemplateUpdatesOutput(recovered=recovered)
