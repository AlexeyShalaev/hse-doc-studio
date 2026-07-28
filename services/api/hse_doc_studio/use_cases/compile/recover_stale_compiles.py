from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from uuid import UUID

import structlog

from hse_doc_studio.core.entities import CompileRecord
from hse_doc_studio.core.enums import CompileStatus, DocumentStatus
from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
)
from hse_doc_studio.infra.persistence.compile import JsonCompileRepository

logger = structlog.get_logger()

_HSE_STUDIO = ".hse-studio"


@dataclass
class RecoverStaleCompilesOutput:
    recovered_compiles: int
    unstuck_documents: int


class RecoverStaleCompilesUC:
    """Fix up any compile records left in `pending`/`running` after a crash.

    A clean shutdown wouldn't leave records in those states because the task's
    finally-block would have written the terminal status. After SIGKILL or a
    bare process exit, though, the in-flight task disappears with its asyncio
    loop and the record stays mid-flight forever — and the document stays
    `building`, which keeps every Compile button disabled. We run this once
    at app startup.
    """

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        compile_repo: JsonCompileRepository,
    ) -> None:
        self._project_repo = project_repo
        self._project_index_repo = project_index_repo
        self._compile_repo = compile_repo

    def execute(self) -> RecoverStaleCompilesOutput:  # noqa: C901
        recovered_compiles = 0
        unstuck_documents = 0

        for folder in self._project_index_repo.list_known():
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

            compiles_dir = folder / _HSE_STUDIO / "compiles"
            if compiles_dir.exists():
                for record_path in compiles_dir.glob("*.json"):
                    try:
                        compile_id = UUID(record_path.stem)
                    except ValueError:
                        continue

                    record = self._compile_repo.get_for_project(folder, compile_id)
                    if record is None:
                        continue
                    if record.status not in (CompileStatus.pending, CompileStatus.running):
                        continue

                    finished_at = datetime.now(tz=timezone.utc)
                    log_tail = (record.log or "").rstrip()
                    suffix = "[stale] server restarted while build was running"
                    new_log = f"{log_tail}\n{suffix}" if log_tail else suffix

                    self._compile_repo.save(
                        CompileRecord(
                            id=record.id,
                            project_folder=record.project_folder,
                            doc_id=record.doc_id,
                            engine=record.engine,
                            status=CompileStatus.failure,
                            started_at=record.started_at,
                            finished_at=finished_at,
                            log=new_log,
                            output_path=record.output_path,
                            check_results=record.check_results,
                            pages=record.pages,
                        )
                    )
                    recovered_compiles += 1

            building_docs = [d for d in project.documents if d.status == DocumentStatus.building]
            if building_docs:
                updated_docs = [
                    replace(d, status=DocumentStatus.err) if d.status == DocumentStatus.building else d
                    for d in project.documents
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

        if recovered_compiles or unstuck_documents:
            logger.info(
                "startup recovery completed",
                recovered_compiles=recovered_compiles,
                unstuck_documents=unstuck_documents,
            )

        return RecoverStaleCompilesOutput(
            recovered_compiles=recovered_compiles,
            unstuck_documents=unstuck_documents,
        )
