from __future__ import annotations

import asyncio
import contextlib
import shutil
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import PurePosixPath
from uuid import UUID

import structlog

from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
    ISignatureRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import ProjectTemplateService
from hse_doc_studio.core.signatures.ports import ISignatureAudit
from hse_doc_studio.core.signatures.stamps import require_slot_images, stamps_digest, stamps_for_doc
from hse_doc_studio.core.value_objects import DetachedSignature, FrozenPdf
from hse_doc_studio.infra.signatures.pdf_stamper import PdfStamper
from hse_doc_studio.use_cases.projects.get_project import GetProjectUC
from hse_doc_studio.use_cases.signatures._doc_context import (
    DETACHED_DIR,
    FROZEN_DIR,
    load_doc_context,
    safe_name,
    sha256_file,
)
from hse_doc_studio.use_cases.signatures._studio_signer import drop_signed_file

logger = structlog.get_logger()


@dataclass
class FreezePdfInput:
    project_id: UUID
    doc_id: str


@dataclass
class FreezePdfOutput:
    frozen: FrozenPdf
    # Slots whose signature files were dropped because they covered an older PDF.
    dropped_slots: list[str]


class FreezePdfUC:
    """Fixes the document for signing.

    Stamps the compiled PDF once (picture slots, text marks for detached e-signatures)
    and keeps that file untouched: detached signatures cover exactly these bytes. Signatures
    made for an earlier frozen copy of different content are dropped.
    """

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        signature_repo: ISignatureRepository,
        template_repo: ITemplateRepository,
        template_service: ProjectTemplateService,
        pdf_stamper: PdfStamper,
        audit: ISignatureAudit | None = None,
    ) -> None:
        self._signature_repo = signature_repo
        self._template_repo = template_repo
        self._template_service = template_service
        self._pdf_stamper = pdf_stamper
        self._audit = audit
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: FreezePdfInput) -> FreezePdfOutput:  # noqa: C901
        ctx = await load_doc_context(
            self._get_uc, self._template_repo, self._template_service, inp.project_id, inp.doc_id
        )
        folder = ctx.project.folder
        if not ctx.compiled_path.is_file():
            raise ValueError(
                localized_error(
                    f"Собранный PDF не найден: {ctx.compiled_path.name}. Сначала соберите документ",
                    f"Compiled PDF not found: {ctx.compiled_path.name}. Build the document first",
                )
            )

        state = self._signature_repo.get_state(folder)
        require_slot_images(state, inp.doc_id, folder)
        stamps = stamps_for_doc(state, inp.doc_id, folder, ctx.lang)

        rel = str(PurePosixPath(FROZEN_DIR) / f"{safe_name(inp.doc_id)}.pdf")
        target = folder / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".pdf.tmp")
        try:
            # Штамповщик не пишет файл без всех меток (`StampingError`): прежняя фиксация и состояние не трогаются.
            await asyncio.to_thread(self._pdf_stamper.stamp, ctx.compiled_path, tmp, stamps)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        tmp.replace(target)

        sha, source_sha = await asyncio.gather(
            asyncio.to_thread(sha256_file, target), asyncio.to_thread(sha256_file, ctx.compiled_path)
        )
        frozen = FrozenPdf(
            path=rel,
            sha256=sha,
            source_sha256=source_sha,
            size=target.stat().st_size,
            frozen_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            stamps_digest=stamps_digest(stamps, folder),
        )

        dropped: list[str] = []
        # Встроенные подписи дописаны к прежним байтам: при тех же байтах цепочка остаётся, иначе уходит целиком.
        previous = state.frozen.get(inp.doc_id)
        embedded = state.embedded.get(inp.doc_id, {})
        if previous is not None and previous.sha256 == sha and previous.signed_path:
            frozen = replace(
                frozen,
                signed_path=previous.signed_path,
                signed_sha256=previous.signed_sha256,
                signed_size=previous.signed_size,
            )
        elif embedded or (previous is not None and previous.signed_path):
            drop_signed_file(folder, previous)
            dropped.extend(embedded)
            embedded = {}
        new_embedded = {k: v for k, v in state.embedded.items() if k != inp.doc_id}
        if embedded:
            new_embedded[inp.doc_id] = embedded

        kept: dict[str, DetachedSignature] = {}
        for slot_id, sig in state.detached.get(inp.doc_id, {}).items():
            if sig.pdf_sha256 == sha:
                kept[slot_id] = sig
                continue
            dropped.append(slot_id)
            with contextlib.suppress(OSError):
                (folder / sig.file).unlink()
        new_detached = {k: v for k, v in state.detached.items() if k != inp.doc_id}
        if kept:
            new_detached[inp.doc_id] = kept
        self._signature_repo.save_state(
            folder,
            replace(state, frozen={**state.frozen, inp.doc_id: frozen}, detached=new_detached, embedded=new_embedded),
        )
        logger.info("pdf frozen", project_id=str(inp.project_id), doc_id=inp.doc_id, sha256=sha, dropped=dropped)
        if self._audit is not None:
            await self._audit.record(
                "signature.freeze",
                project_id=inp.project_id,
                details={"doc_id": inp.doc_id, "sha256": sha, "dropped_slots": sorted(dropped)},
            )
        return FreezePdfOutput(frozen=frozen, dropped_slots=dropped)


@dataclass
class UnfreezePdfInput:
    project_id: UUID
    doc_id: str


class UnfreezePdfUC:
    """Removes the frozen copy and every detached signature attached to it."""

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        signature_repo: ISignatureRepository,
        audit: ISignatureAudit | None = None,
    ) -> None:
        self._signature_repo = signature_repo
        self._audit = audit
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: UnfreezePdfInput) -> None:
        from hse_doc_studio.use_cases.projects.get_project import GetProjectInput  # noqa: PLC0415

        project = (await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))).project
        folder = project.folder
        state = self._signature_repo.get_state(folder)
        frozen = state.frozen.get(inp.doc_id)
        if frozen is None:
            raise NotFoundError(
                localized_error("PDF для этого документа не зафиксирован", "This document has no frozen PDF")
            )
        with contextlib.suppress(OSError):
            (folder / frozen.path).unlink()
        drop_signed_file(folder, frozen)
        for sig in state.detached.get(inp.doc_id, {}).values():
            with contextlib.suppress(OSError):
                (folder / sig.file).unlink()
        shutil.rmtree(folder / DETACHED_DIR / safe_name(inp.doc_id), ignore_errors=True)
        self._signature_repo.save_state(
            folder,
            replace(
                state,
                frozen={k: v for k, v in state.frozen.items() if k != inp.doc_id},
                detached={k: v for k, v in state.detached.items() if k != inp.doc_id},
                embedded={k: v for k, v in state.embedded.items() if k != inp.doc_id},
            ),
        )
        logger.info("pdf unfrozen", project_id=str(inp.project_id), doc_id=inp.doc_id)
        if self._audit is not None:
            await self._audit.record("signature.unfreeze", project_id=inp.project_id, details={"doc_id": inp.doc_id})
