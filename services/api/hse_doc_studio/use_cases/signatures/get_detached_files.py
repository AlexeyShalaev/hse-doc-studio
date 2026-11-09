from __future__ import annotations

import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import UUID

from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
    ISignatureRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import ProjectTemplateService, SignatureSlotService
from hse_doc_studio.core.signatures.package_text import (
    BASE_SUFFIX,
    PackageSignature,
    build_readme,
    build_sign_instructions,
    embedded_note,
    public_key_files,
    signature_arcname,
)
from hse_doc_studio.core.signatures.ports import IPublicKeyExporter
from hse_doc_studio.use_cases.projects.get_project import GetProjectUC
from hse_doc_studio.use_cases.signatures._doc_context import DocContext, load_doc_context
from hse_doc_studio.use_cases.signatures._final_pdf import checked_final_pdf


@dataclass
class DetachedFileOutput:
    path: Path
    download_name: str
    # Temp file to delete after streaming; None = a file that stays.
    temp_path: Path | None = None


@dataclass
class GetDetachedSignatureFileInput:
    project_id: UUID
    doc_id: str
    slot_id: str


@dataclass
class GetFrozenPdfInput:
    project_id: UUID
    doc_id: str


@dataclass
class BuildDetachedPackageInput:
    project_id: UUID
    doc_id: str
    # request: PDF + how to sign it; signed: PDF + signatures + public keys + README.
    mode: Literal["request", "signed"]


class _DetachedFilesBase:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        signature_repo: ISignatureRepository,
        template_repo: ITemplateRepository,
        template_service: ProjectTemplateService,
    ) -> None:
        self._signature_repo = signature_repo
        self._template_repo = template_repo
        self._template_service = template_service
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def _ctx(self, project_id: UUID, doc_id: str) -> DocContext:
        return await load_doc_context(self._get_uc, self._template_repo, self._template_service, project_id, doc_id)


class GetDetachedSignatureFileUC(_DetachedFilesBase):
    async def execute(self, inp: GetDetachedSignatureFileInput) -> DetachedFileOutput:
        ctx = await self._ctx(inp.project_id, inp.doc_id)
        state = self._signature_repo.get_state(ctx.project.folder)
        sig = state.detached.get(inp.doc_id, {}).get(inp.slot_id)
        path = ctx.project.folder / sig.file if sig else None
        if sig is None or path is None or not path.is_file():
            raise NotFoundError(localized_error("Файл подписи не найден", "Signature file not found"))
        rslot = SignatureSlotService().find_runtime_slot(ctx.project, ctx.version, inp.slot_id)
        label = (rslot.label.get(ctx.lang) or rslot.label.get("ru") or inp.slot_id) if rslot else inp.slot_id
        return DetachedFileOutput(
            path=path, download_name=signature_arcname(f"{ctx.base_name}.pdf", label, path.suffix)
        )


class GetFrozenPdfUC(_DetachedFilesBase):
    async def execute(self, inp: GetFrozenPdfInput) -> DetachedFileOutput:
        ctx = await self._ctx(inp.project_id, inp.doc_id)
        state = self._signature_repo.get_state(ctx.project.folder)
        frozen = state.frozen.get(inp.doc_id)
        if frozen is None or not (ctx.project.folder / frozen.path).is_file():
            raise NotFoundError(localized_error("Зафиксированный PDF не найден", "Frozen PDF not found"))
        return DetachedFileOutput(path=ctx.project.folder / frozen.path, download_name=f"{ctx.base_name}.pdf")


class BuildDetachedPackageUC(_DetachedFilesBase):
    """Zip of the frozen PDF with what travels with it (see `BuildDetachedPackageInput.mode`).

    With embedded PAdES signatures the final file F goes in as `<Документ>.pdf` byte for byte, and the frozen
    bytes B, which detached signatures cover, as `<Документ>.для-открепленных-подписей.pdf`: the same names
    as in the LMS package (docs/design/signature-plan.md, section 8). Without PAdES, B is the final file.
    """

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        signature_repo: ISignatureRepository,
        template_repo: ITemplateRepository,
        template_service: ProjectTemplateService,
        key_exporter: IPublicKeyExporter,
    ) -> None:
        super().__init__(project_repo, project_index_repo, signature_repo, template_repo, template_service)
        self._key_exporter = key_exporter

    async def execute(self, inp: BuildDetachedPackageInput) -> DetachedFileOutput:  # noqa: C901
        ctx = await self._ctx(inp.project_id, inp.doc_id)
        folder = ctx.project.folder
        state = self._signature_repo.get_state(folder)
        frozen = state.frozen.get(inp.doc_id)
        if frozen is None or not (folder / frozen.path).is_file():
            raise ValueError(localized_error("Сначала зафиксируйте PDF на подпись", "Freeze the PDF for signing first"))
        final = await checked_final_pdf(folder, frozen)
        pdf_name = f"{ctx.base_name}.pdf"
        # Открепленные подписи покрывают зафиксированные байты: при встроенных подписях это отдельный файл.
        base_name = pdf_name
        if final.has_embedded:
            base_name = f"{ctx.base_name}.{BASE_SUFFIX.get(ctx.lang, BASE_SUFFIX['ru'])}.pdf"

        slot_service = SignatureSlotService()
        sigs: list[PackageSignature] = []
        sig_files: list[Path] = []
        if inp.mode == "signed":
            for slot_id, sig in state.detached.get(inp.doc_id, {}).items():
                path = folder / sig.file
                if sig.pdf_sha256 != frozen.sha256 or not path.is_file():
                    continue
                rslot = slot_service.find_runtime_slot(ctx.project, ctx.version, slot_id)
                label = (rslot.label.get(ctx.lang) or rslot.label.get("ru") or slot_id) if rslot else slot_id
                sigs.append(
                    PackageSignature(
                        slot_label=label,
                        arcname=signature_arcname(base_name, label, path.suffix),
                        format=sig.format,
                        signer=sig.signer,
                        signer_id=sig.signer_id,
                    )
                )
                sig_files.append(path)

        fd, tmp_name = tempfile.mkstemp(suffix=".zip")
        tmp = Path(tmp_name)
        import os  # noqa: PLC0415

        os.close(fd)
        note = (
            "\n" + embedded_note(ctx.lang, pdf_name, final.sha256, base_name, frozen.size) if final.has_embedded else ""
        )
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(final.path, pdf_name)
            if final.has_embedded:
                zf.write(final.base, base_name)
            if inp.mode == "request":
                sums = f"{frozen.sha256}  {base_name}\n"
                if final.has_embedded:
                    sums += f"{final.sha256}  {pdf_name}\n"
                zf.writestr("SHA256SUMS.txt", sums)
                zf.writestr("README.txt", build_sign_instructions(ctx.lang, base_name, frozen.sha256) + note)
            else:
                keys = public_key_files(self._key_exporter.export_public, sigs)
                for s, sig_file in zip(sigs, sig_files, strict=True):
                    zf.write(sig_file, s.arcname)
                for name, blob in keys.items():
                    zf.writestr(name, blob)
                readme = build_readme(ctx.lang, base_name, frozen.sha256, sigs, list(keys))
                zf.writestr("README.txt", readme + note)
        suffix = "на подпись" if inp.mode == "request" else "с подписями"
        if ctx.lang == "en":
            suffix = "to sign" if inp.mode == "request" else "signed"
        return DetachedFileOutput(path=tmp, download_name=f"{ctx.base_name} ({suffix}).zip", temp_path=tmp)
