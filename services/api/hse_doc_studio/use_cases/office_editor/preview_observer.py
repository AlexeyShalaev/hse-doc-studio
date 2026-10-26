from __future__ import annotations

import structlog

from hse_doc_studio.core.jobs.entities import JobResult, JobSpec
from hse_doc_studio.core.jobs.enums import JobStatus
from hse_doc_studio.core.jobs.office import OfficeConvertPayload, OfficeConvertResult, OfficeConvertStatus

logger = structlog.get_logger()


class PreviewRefreshObserver:
    """Итог фонового обновления PDF-предпросмотра после сохранения из office-редактора: только лог."""

    async def on_finished(self, spec: JobSpec, result: JobResult) -> None:
        payload = spec.payload
        if not isinstance(payload, OfficeConvertPayload):
            return
        root = spec.local_root
        src = str(root / payload.source.path) if root is not None else payload.source.path
        if result.status is not JobStatus.succeeded:
            error = result.error
            logger.warning(
                "office-editor: preview refresh failed",
                path=src,
                exc=error.detail or error.code if error is not None else str(result.status),
            )
            return
        data = result.data_as(OfficeConvertResult)
        if data.status is OfficeConvertStatus.ok:
            pdf = str(root / payload.output_path) if root is not None else payload.output_path
            logger.info("office-editor: preview refreshed", path=pdf)
        elif data.detail:
            logger.warning("office-editor: preview refresh failed", path=src, exc=data.detail)
        else:
            logger.info("office-editor: preview refresh skipped", path=src)
