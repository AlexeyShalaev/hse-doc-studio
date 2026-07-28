from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

import structlog

from hse_doc_studio.core.entities import CompileRecord
from hse_doc_studio.core.enums import CompileStatus, DocumentStatus
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
)
from hse_doc_studio.infra.compile.compile_runner import CompileRunner
from hse_doc_studio.infra.compile.log_bus import CompileLogBus
from hse_doc_studio.infra.persistence.compile import JsonCompileRepository
from hse_doc_studio.use_cases.compile.trigger_compile import _find_project

logger = structlog.get_logger()


@dataclass
class CancelCompileInput:
    project_id: uuid.UUID
    compile_id: uuid.UUID


@dataclass
class CancelCompileOutput:
    cancelled_task: bool
    record_finalised: bool


class CancelCompileUC:
    """Cancel an in-flight compile and finalise its record.

    Two paths:
      1. The task is alive in this process → ask the runner to terminate the
         docker subprocess and cancel the task. The task's own `except
         CancelledError` block writes the cancelled record.
      2. The task is gone (server restart, lost task ref, or already
         finished but stuck in `running`) → write a cancelled record + reset
         the document status here so the UI lock releases.
    """

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        compile_repo: JsonCompileRepository,
        compile_runner: CompileRunner,
        log_bus: CompileLogBus,
    ) -> None:
        self._project_repo = project_repo
        self._project_index_repo = project_index_repo
        self._compile_repo = compile_repo
        self._compile_runner = compile_runner
        self._log_bus = log_bus

    async def execute(self, inp: CancelCompileInput) -> CancelCompileOutput:
        if self._compile_runner.is_running(inp.compile_id):
            await self._compile_runner.cancel(inp.compile_id)
            return CancelCompileOutput(cancelled_task=True, record_finalised=False)

        # No live task → force-finalise the record so the UI lock unsticks.
        project_folder, project = _find_project(
            inp.project_id,
            self._project_repo,
            self._project_index_repo,
        )
        if project is None or project_folder is None:
            raise NotFoundError(
                localized_error(f"Проект {inp.project_id} не найден", f"Project not found: {inp.project_id}")
            )

        record = self._compile_repo.get_for_project(project_folder, inp.compile_id)
        if record is None:
            raise NotFoundError(
                localized_error(
                    f"Запись компиляции {inp.compile_id} не найдена", f"Compile record not found: {inp.compile_id}"
                )
            )

        if record.status in (CompileStatus.success, CompileStatus.failure, CompileStatus.cancelled):
            # Already terminal. Still flip the document if it's somehow
            # stuck in `building` because the previous save was interrupted.
            self._maybe_unstick_document(project_folder, record.doc_id, inp.compile_id)
            return CancelCompileOutput(cancelled_task=False, record_finalised=False)

        finished_at = datetime.now(tz=timezone.utc)
        log_tail = (record.log or "").rstrip()
        suffix = "[cancelled] cancelled by user (no live task)"
        new_log = f"{log_tail}\n{suffix}" if log_tail else suffix

        cancelled_record = CompileRecord(
            id=record.id,
            project_folder=record.project_folder,
            doc_id=record.doc_id,
            engine=record.engine,
            status=CompileStatus.cancelled,
            started_at=record.started_at,
            finished_at=finished_at,
            log=new_log,
            output_path=record.output_path,
            check_results=record.check_results,
            pages=record.pages,
        )
        self._compile_repo.save(cancelled_record)

        # Best-effort close the log bus in case any SSE subscriber is camped
        # on this id. discard() drops the channel entirely so subscribe()
        # creates a fresh one for any future replay.
        self._log_bus.close(inp.compile_id)
        self._log_bus.discard(inp.compile_id)

        self._maybe_unstick_document(project_folder, record.doc_id, inp.compile_id)

        return CancelCompileOutput(cancelled_task=False, record_finalised=True)

    def _maybe_unstick_document(
        self,
        project_folder: Path,
        doc_id: str,
        compile_id: uuid.UUID,
    ) -> None:
        project = self._project_repo.get(project_folder)
        if project is None:
            return
        changed = False
        new_docs = []
        for doc in project.documents:
            if doc.id == doc_id and doc.status == DocumentStatus.building:
                new_docs.append(replace(doc, status=DocumentStatus.err, last_compile_id=compile_id))
                changed = True
            else:
                new_docs.append(doc)
        if changed:
            project.documents[:] = new_docs
            self._project_repo.save(project)
