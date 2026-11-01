"""Артефакты сборки в серверном режиме: PDF остаётся рядом с исходником на томе, копия и архив лежат в хранилище.

Порядок «сначала хранилище, потом том»: копия уходит в объектное хранилище до переноса PDF на место, а архив
при следующем шаге дозагружает её, если загрузка тогда не удалась. Расхождение тома и хранилища поэтому
самолечится и не роняет сборку.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import structlog

from hse_doc_studio.core.jobs.artifacts import IArtifactStore, PublishPdfOutcome, PublishPdfRequest
from hse_doc_studio.core.storage import InvalidObjectKeyError, ObjectNotFoundError, ObjectStoreError, validate_key
from hse_doc_studio.core.storage.models import PresignedUrl
from hse_doc_studio.core.storage.ports import IObjectStore
from hse_doc_studio.infra.compile.pdf_archive import ARCHIVE_KEEP, built_pdf_path, final_pdf_path

logger = structlog.get_logger()

_PDF_TYPE = "application/pdf"
LINK_TTL_S = 120


def archive_prefix(project_id: UUID, doc_id: str) -> str:
    """Каталог архива документа: `artifacts/<project_id>/pdf/<doc_id>/`."""
    return validate_key(f"artifacts/{project_id}/pdf/{doc_id}") + "/"


def archived_pdf_key(project_id: UUID, doc_id: str, job_id: UUID) -> str:
    return f"{archive_prefix(project_id, doc_id)}{job_id}.pdf"


class S3ArtifactStore:
    """Перенос PDF на том делает ``local``, копию и архив последних ``keep`` версий держит ``objects``."""

    def __init__(
        self,
        objects: IObjectStore,
        local: IArtifactStore,
        *,
        keep: int = ARCHIVE_KEEP,
        link_ttl_s: int = LINK_TTL_S,
    ) -> None:
        self._objects = objects
        self._local = local
        self._keep = keep
        self._link_ttl_s = link_ttl_s

    async def publish_pdf(self, req: PublishPdfRequest) -> PublishPdfOutcome:
        if req.project_id is not None:
            built = built_pdf_path(req.workspace, req.doc_id, req.source_file)
            await self._upload(req.project_id, req.doc_id, req.job_id, built)
        return await self._local.publish_pdf(req)

    async def archive_pdf(self, project_id: UUID, workspace: Path, doc_id: str, job_id: UUID, source_file: str) -> None:
        try:
            key = archived_pdf_key(project_id, doc_id, job_id)
            if await self._objects.head(key) is None:
                # Свежий PDF ещё в `.build`, когда перенос к исходнику не удался; иначе он уже рядом с ним.
                built = built_pdf_path(workspace, doc_id, source_file)
                await self._upload(
                    project_id, doc_id, job_id, built if built.exists() else final_pdf_path(workspace, source_file)
                )
            await self._prune(project_id, doc_id, current=key)
        except (ObjectStoreError, OSError) as exc:
            logger.warning("pdf archive failed", doc_id=doc_id, exc=str(exc))

    async def read_archived_pdf(self, project_id: UUID, workspace: Path, doc_id: str, job_id: UUID) -> bytes:
        try:
            return await self._objects.get(archived_pdf_key(project_id, doc_id, job_id))
        except (ObjectNotFoundError, InvalidObjectKeyError) as exc:
            raise FileNotFoundError(str(exc)) from exc

    async def archived_pdf_link(self, project_id: UUID, doc_id: str, job_id: UUID) -> PresignedUrl | None:
        try:
            key = archived_pdf_key(project_id, doc_id, job_id)
        except InvalidObjectKeyError as exc:
            raise FileNotFoundError(str(exc)) from exc
        link = await self._objects.presign_get(key, expires_in_s=self._link_ttl_s)
        if link is None:
            return None
        if await self._objects.head(key) is None:
            raise FileNotFoundError(key)
        return link

    async def _upload(self, project_id: UUID, doc_id: str, job_id: UUID, source: Path) -> None:
        try:
            key = archived_pdf_key(project_id, doc_id, job_id)
            if not source.exists():
                return
            with source.open("rb") as handle:
                await self._objects.put(key, handle, content_type=_PDF_TYPE)
        except (ObjectStoreError, OSError) as exc:
            logger.warning("pdf upload failed", doc_id=doc_id, exc=str(exc))

    async def _prune(self, project_id: UUID, doc_id: str, *, current: str) -> None:
        """Оставляет текущую сборку и `keep - 1` самых свежих до неё."""
        others = [o for o in await self._objects.list_objects(archive_prefix(project_id, doc_id)) if o.key != current]
        others.sort(key=lambda o: (o.last_modified, o.key), reverse=True)
        for old in others[max(self._keep - 1, 0) :]:
            await self._objects.delete(old.key)
