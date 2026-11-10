from __future__ import annotations

import asyncio
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import structlog

from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
    ISignatureRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import ProjectTemplateService
from hse_doc_studio.core.signatures.stamps import require_slot_images, stamps_for_doc
from hse_doc_studio.core.value_objects import SignaturesState
from hse_doc_studio.infra.signatures.pdf_stamper import PdfStamper
from hse_doc_studio.use_cases.projects.get_project import GetProjectUC
from hse_doc_studio.use_cases.signatures._doc_context import DocContext, load_doc_context
from hse_doc_studio.use_cases.signatures._final_pdf import current_final_pdf
from hse_doc_studio.use_cases.signatures.signing_source import missing_source_message, signing_source

logger = structlog.get_logger()


@dataclass
class GetSignedDocPdfInput:
    project_id: UUID
    doc_id: str


@dataclass
class GetSignedDocPdfOutput:
    """PDF to stream. `temp_path` is the file to delete after streaming (None: a project file served in place)."""

    pdf_path: Path
    temp_path: Path | None
    download_name: str


class GetSignedDocPdfUC:
    """PDF документа «С подписями» (docs/design/signature-plan.md, раздел 10).

    - Есть актуальная фиксация (источник подписи и видимый слой те же, что при фиксации): отдаётся итоговый файл плана
      байт в байт. Это F со встроенными подписями PAdES, если они есть, иначе зафиксированный B; тот же файл
      уходит в пакет для подписанта и в комплект LMS.
    - Актуальной фиксации нет: предпросмотр для печати. Источник подписи (версия на подписи маршрута, иначе
      текущая сборка, signing-route.md, 12.4) с тем видимым слоем, который поставила бы фиксация (картинки и
      плашки открепленных ЭП, `stamps_for_doc`), без электронных подписей. В плане такие
      криптослоты ждут фиксации, и подпись «на лету» при скачивании противоречила бы ему: ЭП ставятся только
      через план (фиксация, «Подписать в Студии», «Подписать комплект»).
    """

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        signature_repo: ISignatureRepository,
        template_repo: ITemplateRepository,
        template_service: ProjectTemplateService,
        pdf_stamper: PdfStamper,
    ) -> None:
        self._signature_repo = signature_repo
        self._template_repo = template_repo
        self._template_service = template_service
        self._pdf_stamper = pdf_stamper
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: GetSignedDocPdfInput) -> GetSignedDocPdfOutput:
        ctx = await load_doc_context(
            self._get_uc, self._template_repo, self._template_service, inp.project_id, inp.doc_id
        )
        suffix = "signed" if ctx.lang == "en" else "с подписями"
        download_name = f"{ctx.base_name} ({suffix}).pdf"
        state = self._signature_repo.get_state(ctx.project.folder)

        final = await current_final_pdf(ctx, state)
        if final is not None:
            logger.info(
                "signed pdf: serving the final file",
                project_id=str(inp.project_id),
                doc_id=inp.doc_id,
                embedded=final.has_embedded,
            )
            return GetSignedDocPdfOutput(pdf_path=final.path, temp_path=None, download_name=download_name)
        return await self._preview(ctx, state, download_name)

    async def _preview(self, ctx: DocContext, state: SignaturesState, download_name: str) -> GetSignedDocPdfOutput:
        """Источник подписи с видимым слоем будущей фиксации; без меток отдаётся как есть."""
        found = await signing_source(ctx, state)
        if found.path is None or not found.exists:
            raise ValueError(missing_source_message(ctx, found))
        source = found.path
        require_slot_images(state, ctx.doc.id, ctx.project.folder)
        stamps = stamps_for_doc(state, ctx.doc.id, ctx.project.folder, ctx.lang)
        if not stamps:
            return GetSignedDocPdfOutput(pdf_path=source, temp_path=None, download_name=download_name)

        fd, name = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        out = Path(name)
        try:
            await asyncio.to_thread(self._pdf_stamper.stamp, source, out, stamps)
        except Exception:
            out.unlink(missing_ok=True)
            raise
        logger.info("signed pdf: print preview", project_id=str(ctx.project.id), doc_id=ctx.doc.id, stamps=len(stamps))
        return GetSignedDocPdfOutput(pdf_path=out, temp_path=out, download_name=download_name)
