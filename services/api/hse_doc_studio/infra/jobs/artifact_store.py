from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from uuid import UUID

from hse_doc_studio.core.jobs.artifacts import PublishPdfOutcome, PublishPdfRequest
from hse_doc_studio.infra.compile.pdf_archive import (
    archive_compiled_pdf,
    archived_pdf_path,
    built_pdf_path,
    final_pdf_path,
)

# Повторы переноса PDF на место: в Windows целевой файл может ненадолго
# блокироваться антивирусом, индексатором или открытым просмотрщиком (WinError 32).
DEFAULT_MOVE_ATTEMPTS = 5
DEFAULT_MOVE_RETRY_DELAY_S = 0.6


class LocalDiskArtifactStore:
    """Публикует и архивирует PDF на локальном диске проекта."""

    def __init__(
        self,
        move_attempts: int = DEFAULT_MOVE_ATTEMPTS,
        retry_delay_s: float = DEFAULT_MOVE_RETRY_DELAY_S,
    ) -> None:
        self._move_attempts = move_attempts
        self._retry_delay_s = retry_delay_s

    async def publish_pdf(self, req: PublishPdfRequest) -> PublishPdfOutcome:
        built = built_pdf_path(req.workspace, req.doc_id, req.source_file)
        final = final_pdf_path(req.workspace, req.source_file)
        move_error: OSError | None = None
        for attempt in range(self._move_attempts):
            try:
                shutil.move(str(built), str(final))
                move_error = None
                break
            except OSError as exc:
                move_error = exc
                if attempt < self._move_attempts - 1:
                    await asyncio.sleep(self._retry_delay_s)
        return PublishPdfOutcome(replaced=move_error is None, final_name=final.name)

    def archive_pdf(self, workspace: Path, doc_id: str, job_id: UUID, source_file: str) -> None:
        archive_compiled_pdf(workspace, doc_id, job_id, source_file)

    def read_archived_pdf(self, workspace: Path, doc_id: str, job_id: UUID) -> bytes:
        return archived_pdf_path(workspace, doc_id, job_id).read_bytes()
