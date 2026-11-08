from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone

import structlog

from hse_doc_studio.core.compile.failure import INTERRUPTED
from hse_doc_studio.core.entities import CompileRecord
from hse_doc_studio.core.enums import CompileStatus, DocumentStatus
from hse_doc_studio.core.jobs.protocols import IJobDispatcher
from hse_doc_studio.core.projects.locator import IProjectLocator
from hse_doc_studio.core.repositories import (
    ICompileRepository,
    IProjectRepository,
)

logger = structlog.get_logger()

STALE_LOG_LINE = "[stale] server restarted while build was running: the build was interrupted"


@dataclass
class RecoverStaleCompilesOutput:
    recovered_compiles: int
    unstuck_documents: int
    # Сборки, которые после рестарта ведёт диспетчер (задача в очереди пережила api): их не трогаем.
    continued_compiles: int = 0


class RecoverStaleCompilesUC:
    """Закрывает записи сборок, оставшиеся в `pending`/`running` от прошлого процесса.

    Сборка, которую ведёт диспетчер (на сервере задача очереди пережила рестарт api и подхвачена
    `QueueJobDispatcher.recover()`), продолжается: её запись и статус документа получат итог задачи. Поэтому
    вызывать после восстановления очереди. Остальные записи продолжить нечем (локальная сборка умерла с
    процессом, задача не успела попасть в очередь): они закрываются статусом `cancelled` с кодом `interrupted`,
    а не `failure`, так как документ тут ни при чём. Документ без идущей сборки перестаёт быть `building`,
    иначе кнопки сборки остались бы выключенными. Выполняется один раз при старте.
    """

    def __init__(
        self,
        project_repo: IProjectRepository,
        locator: IProjectLocator,
        compile_repo: ICompileRepository,
        dispatcher: IJobDispatcher | None = None,
    ) -> None:
        self._project_repo = project_repo
        self._locator = locator
        self._compile_repo = compile_repo
        self._dispatcher = dispatcher

    async def execute(self) -> RecoverStaleCompilesOutput:  # noqa: C901
        recovered_compiles = 0
        unstuck_documents = 0
        continued_compiles = 0

        for folder in await self._locator.list_all():
            try:
                project = self._project_repo.get(folder)
            except Exception as exc:
                logger.warning(
                    "startup_recovery: failed to load project",
                    folder=str(folder),
                    exc=str(exc),
                )
                continue
            if project is None:
                continue

            continued_docs: set[str] = set()
            for record in await self._compile_repo.list_unfinished(folder):
                if self._dispatcher is not None and self._dispatcher.is_active(record.id):
                    continued_docs.add(record.doc_id)
                    continued_compiles += 1
                    continue
                await self._interrupt(record)
                recovered_compiles += 1

            building_docs = [
                d for d in project.documents if d.status == DocumentStatus.building and d.id not in continued_docs
            ]
            if building_docs:
                stuck_ids = {d.id for d in building_docs}
                updated_docs = [
                    replace(d, status=DocumentStatus.err) if d.id in stuck_ids else d for d in project.documents
                ]
                project.documents[:] = updated_docs
                try:
                    self._project_repo.save(project)
                    unstuck_documents += len(building_docs)
                except Exception as exc:
                    logger.warning(
                        "startup_recovery: failed to unstick documents",
                        folder=str(folder),
                        exc=str(exc),
                    )

        if recovered_compiles or unstuck_documents or continued_compiles:
            logger.info(
                "startup recovery completed",
                recovered_compiles=recovered_compiles,
                unstuck_documents=unstuck_documents,
                continued_compiles=continued_compiles,
            )

        return RecoverStaleCompilesOutput(
            recovered_compiles=recovered_compiles,
            unstuck_documents=unstuck_documents,
            continued_compiles=continued_compiles,
        )

    async def _interrupt(self, record: CompileRecord) -> None:
        log_tail = (record.log or "").rstrip()
        await self._compile_repo.save(
            replace(
                record,
                status=CompileStatus.cancelled,
                finished_at=datetime.now(tz=timezone.utc),
                log=f"{log_tail}\n{STALE_LOG_LINE}" if log_tail else STALE_LOG_LINE,
                error_code=INTERRUPTED,
                error_detail=None,
            )
        )
