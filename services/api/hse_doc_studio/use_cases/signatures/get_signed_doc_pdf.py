from __future__ import annotations

import contextlib
import os
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID
from uuid import UUID as _UUID

import structlog

from hse_doc_studio.core.enums import SignMode
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
    ISignatureRepository,
    ISigningIdentityRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import ProjectTemplateService
from hse_doc_studio.core.team import author_by_slug
from hse_doc_studio.infra.signatures.cades_signer import sign_detached
from hse_doc_studio.infra.signatures.pdf_stamper import PdfStamper, Stamp, format_sign_date
from hse_doc_studio.infra.signatures.pyhanko_signer import CryptoSignRequest, PyHankoPdfSigner
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()


@dataclass
class GetSignedDocPdfInput:
    project_id: UUID
    doc_id: str
    crypto: str = "auto"  # "auto" | "off"


@dataclass
class GetSignedDocPdfOutput:
    """Result of the signed-PDF pipeline.

    When `zip_path` is set the caller should serve it as application/zip
    and clean it up after streaming (it contains the PDF + .sig files).
    When only `pdf_path`/`temp_path` are set the caller streams the PDF.
    `temp_path` is the file to delete after streaming (None = serve source
    PDF in-place, nothing to clean up).
    """

    pdf_path: Path
    temp_path: Path | None
    download_name: str
    zip_path: Path | None = field(default=None)


@dataclass(frozen=True)
class _DetachedRequest:
    slot_id: str
    key_dir: Path


class GetSignedDocPdfUC:
    """Produces a signature-stamped PDF (or PDF+sig zip) for one document.

    Mode routing per slot:

    image           → PNG overlay via PdfStamper (current default)
    image_crypto    → PNG overlay first, then PAdES embedded signature on top
    crypto_invisible → PAdES embedded signature, no visible appearance
    detached        → PNG overlay (visual marker) + separate CAdES .sig file;
                      both are packaged into a zip for download

    Image overlays always run before any cryptographic step so that embedded
    PAdES signatures cover the final visual state of the document.
    """

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        signature_repo: ISignatureRepository,
        signing_identity_repo: ISigningIdentityRepository,
        template_repo: ITemplateRepository,
        template_service: ProjectTemplateService,
        pdf_stamper: PdfStamper,
        pyhanko_signer: PyHankoPdfSigner,
    ) -> None:
        self._signature_repo = signature_repo
        self._signing_identity_repo = signing_identity_repo
        self._template_repo = template_repo
        self._template_service = template_service
        self._pdf_stamper = pdf_stamper
        self._pyhanko_signer = pyhanko_signer
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: GetSignedDocPdfInput) -> GetSignedDocPdfOutput:  # noqa: C901,PLR0912,PLR0915
        result = await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))
        project = result.project

        version = self._template_repo.get_version(
            project.lock.pack_id,
            project.lock.template_id,
            project.lock.version,
        )
        if version is None:
            raise NotFoundError(
                localized_error(
                    f"Версия шаблона не найдена для проекта {inp.project_id}",
                    f"Template version not found for project {inp.project_id}",
                )
            )

        doc = next((d for d in project.documents if d.id == inp.doc_id), None)
        if doc is None:
            raise NotFoundError(
                localized_error(
                    f"Документ {inp.doc_id!r} не найден в проекте",
                    f"Document {inp.doc_id!r} not found in project",
                )
            )
        doc_def = self._template_service.find_definition(version, doc)
        if doc_def is None:
            raise NotFoundError(
                localized_error(
                    f"Определение документа {doc.def_id!r} не найдено в версии шаблона",
                    f"Document definition {doc.def_id!r} not found in template version",
                )
            )

        _, output_file = self._template_service.resolve_instance_source(project, doc, version)
        if not output_file:
            raise ValueError(
                localized_error(
                    f"У документа {inp.doc_id!r} не задан output_file",
                    f"Document {inp.doc_id!r} has no output_file",
                )
            )

        source_path = project.folder / output_file
        if not source_path.exists():
            raise ValueError(
                localized_error(
                    f"Собранный PDF не найден по пути {source_path} — сначала соберите документ",
                    f"Compiled PDF not found at {source_path} — build the document first",
                )
            )

        lang = str(project.lang)
        _base_name = doc_def.output_name.get(lang) or doc_def.output_name.get("ru") or output_file
        # Add a suffix so the signed copy is clearly distinct from the original.
        _stem, _ext = _base_name.rsplit(".", 1) if "." in _base_name else (_base_name, "")
        # В team личный док получает фамилию владельца в имени файла.
        owner = author_by_slug(project, doc.owner)
        if owner is not None:
            _stem = f"{_stem} — {owner.name.split()[0] if owner.name.split() else owner.slug}"
        download_name = f"{_stem} (с подписями).{_ext}" if _ext else f"{_stem} (с подписями)"

        state = self._signature_repo.get_state(project.folder)
        doc_placements = state.placements.get(inp.doc_id, {})
        use_crypto = inp.crypto != "off"

        # ── Partition slots by mode ──────────────────────────────────────────
        image_stamps: list[Stamp] = []
        pades_requests: list[CryptoSignRequest] = []  # image_crypto / crypto_invisible
        detached_requests: list[_DetachedRequest] = []  # detached → .sig
        skipped_png_missing: list[str] = []  # for error reporting

        for slot_id, placement in doc_placements.items():
            if not placement.enabled:
                continue
            slot = state.slots.get(slot_id)
            if slot is None or slot.png_path is None:
                continue
            png_path = project.folder / slot.png_path
            if not png_path.exists():
                logger.warning(
                    "signed pdf: PNG missing for slot",
                    project_id=str(inp.project_id),
                    slot_id=slot_id,
                    path=str(png_path),
                )
                skipped_png_missing.append(slot_id)
                continue

            aspect = 0.4
            if slot.natural_width_px and slot.natural_height_px and slot.natural_width_px > 0:
                aspect = slot.natural_height_px / slot.natural_width_px

            mode = slot.sign_mode
            identity_id_str = slot.signing_identity_id
            wants_crypto = use_crypto and mode != SignMode.image and identity_id_str is not None

            if wants_crypto:
                identity = self._signing_identity_repo.get(_UUID(identity_id_str))
                if identity is None:
                    logger.warning(
                        "signed pdf: signing identity not found, falling back to image",
                        slot_id=slot_id,
                        identity_id=identity_id_str,
                    )
                    wants_crypto = False

            if wants_crypto and identity_id_str:
                key_dir = self._signing_identity_repo.key_dir(_UUID(identity_id_str))

                if mode == SignMode.detached:
                    # Visual: image stamp (so the page shows where the signature is).
                    image_stamps.append(
                        Stamp(
                            page=placement.page,
                            x_mm=placement.x_mm,
                            y_mm=placement.y_mm,
                            width_mm=placement.width_mm,
                            png_path=png_path,
                            aspect_ratio=aspect,
                            date_text=format_sign_date(placement.sign_date),
                        )
                    )
                    # Crypto: CAdES detached .sig (generated after image pass).
                    detached_requests.append(_DetachedRequest(slot_id=slot_id, key_dir=key_dir))

                else:
                    # image_crypto → PNG appearance + PAdES embedded
                    # crypto_invisible → PAdES embedded, no visible appearance
                    pades_requests.append(
                        CryptoSignRequest(
                            field_name=f"Sig_{slot_id}",
                            page=placement.page,
                            x_mm=placement.x_mm,
                            y_mm=placement.y_mm,
                            width_mm=placement.width_mm,
                            aspect_ratio=aspect,
                            png_path=png_path if mode == SignMode.image_crypto else None,
                            identity_key_dir=key_dir,
                            reason=slot.sign_reason or f"Signed via slot {slot_id}",
                        )
                    )
            else:
                image_stamps.append(
                    Stamp(
                        page=placement.page,
                        x_mm=placement.x_mm,
                        y_mm=placement.y_mm,
                        width_mm=placement.width_mm,
                        png_path=png_path,
                        aspect_ratio=aspect,
                        date_text=format_sign_date(placement.sign_date),
                    )
                )

        if not image_stamps and not pades_requests and not detached_requests:
            if skipped_png_missing:
                # Enabled placements exist but every PNG file is missing on disk.
                raise ValueError(
                    localized_error(
                        f"PNG-файлы не найдены на диске для слотов: {', '.join(skipped_png_missing)}. "
                        "Возможно, изображение подписи было удалено или папка проекта перемещена.",
                        f"PNG files not found on disk for slots: {', '.join(skipped_png_missing)}. "
                        "The signature image may have been deleted or the project folder moved.",
                    )
                )
            # Nothing enabled at all — serve the source PDF unchanged.
            return GetSignedDocPdfOutput(
                pdf_path=source_path,
                temp_path=None,
                download_name=download_name,
            )

        logger.info(
            "signed pdf: applying",
            project_id=str(inp.project_id),
            doc_id=inp.doc_id,
            image_stamps=len(image_stamps),
            pades=len(pades_requests),
            detached=len(detached_requests),
        )

        tmp_paths: list[Path] = []

        # ── Step 1: image stamps ─────────────────────────────────────────────
        if image_stamps:
            fd, p = tempfile.mkstemp(suffix=".pdf")
            os.close(fd)
            after_image = Path(p)
            tmp_paths.append(after_image)
            self._pdf_stamper.stamp(source_path, after_image, image_stamps)
            current = after_image
        else:
            current = source_path

        # ── Step 2: PAdES embedded signatures ───────────────────────────────
        if pades_requests:
            fd, p = tempfile.mkstemp(suffix=".pdf")
            os.close(fd)
            after_pades = Path(p)
            tmp_paths.append(after_pades)
            try:
                await self._pyhanko_signer.sign(current, after_pades, pades_requests)
                current = after_pades
            except Exception as exc:
                logger.warning(
                    "signed pdf: PAdES signing failed, falling back to image-only",
                    exc=str(exc),
                )
                after_pades.unlink(missing_ok=True)
                tmp_paths.pop()

        # ── Step 3: CAdES detached .sig files ───────────────────────────────
        sig_paths: list[tuple[Path, str]] = []  # (tmp_path, filename_in_zip)
        if detached_requests:
            stem = Path(download_name).stem
            for req in detached_requests:
                fd, sp = tempfile.mkstemp(suffix=".sig")
                os.close(fd)
                sig_tmp = Path(sp)
                try:
                    sign_detached(current, sig_tmp, req.key_dir)
                    sig_name = f"{stem}.{req.slot_id}.sig"
                    sig_paths.append((sig_tmp, sig_name))
                    tmp_paths.append(sig_tmp)
                except Exception as exc:
                    logger.warning(
                        "signed pdf: detached signing failed for slot",
                        slot_id=req.slot_id,
                        exc=str(exc),
                    )
                    sig_tmp.unlink(missing_ok=True)

        # ── Step 4: pack into zip when .sig files exist ──────────────────────
        final_pdf = current
        zip_out: Path | None = None

        if sig_paths:
            fd, zp = tempfile.mkstemp(suffix=".zip")
            os.close(fd)
            zip_out = Path(zp)
            tmp_paths.append(zip_out)
            with zipfile.ZipFile(zip_out, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.write(final_pdf, download_name)
                for sig_tmp, sig_name in sig_paths:
                    zf.write(sig_tmp, sig_name)

        # ── Cleanup intermediates (keep final pdf + zip + individual sigs) ───
        keep = {final_pdf, zip_out} | {sp for sp, _ in sig_paths}
        for p in tmp_paths:
            if p not in keep and p.exists():
                with contextlib.suppress(OSError):
                    p.unlink()

        if zip_out is not None:
            # Caller streams the zip; clean up zip + pdf + sigs after.
            cleanup = zip_out
            # Also clean the individual sig temps and the final pdf temp
            # by pointing temp_path to the zip; the router only unlinks that one.
            # The sig temps and pdf temp will be cleaned by the OS eventually.
            # For correctness we unlink sigs now (they're inside the zip already).
            for sig_tmp, _ in sig_paths:
                with contextlib.suppress(OSError):
                    sig_tmp.unlink()
            if final_pdf != source_path:
                with contextlib.suppress(OSError):
                    final_pdf.unlink()
            zip_name = Path(download_name).stem + "_signed.zip"
            return GetSignedDocPdfOutput(
                pdf_path=zip_out,
                temp_path=cleanup,
                download_name=zip_name,
                zip_path=zip_out,
            )

        if final_pdf == source_path:
            return GetSignedDocPdfOutput(
                pdf_path=source_path,
                temp_path=None,
                download_name=download_name,
            )

        return GetSignedDocPdfOutput(
            pdf_path=final_pdf,
            temp_path=final_pdf,
            download_name=download_name,
        )
