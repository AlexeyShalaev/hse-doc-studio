"""Optional cryptographic PDF signing via pyHanko.

This module is the ONLY place in the codebase that imports pyHanko.  All
imports are deferred to method bodies so that the rest of the application
works normally when the `signing` extra is not installed.  If a method that
needs pyHanko is called without it installed a clear `SigningUnavailableError`
is raised — never an ImportError propagating up the stack.

Signatures are appended as invisible incremental updates on top of the frozen
PDF: the visible layer is already stamped when the PDF is frozen
(docs/design/signature-plan.md, section 4).
"""

from __future__ import annotations

from pathlib import Path

import structlog

from hse_doc_studio.core.signatures.ports import PadesCheck

logger = structlog.get_logger()

__all__ = ["PyHankoPades", "SigningUnavailableError"]


class SigningUnavailableError(RuntimeError):
    """Raised when pyHanko is not installed and crypto signing is requested."""


# ---------------------------------------------------------------------------
# Internals — everything below this line imports pyHanko.
# ---------------------------------------------------------------------------


def _ensure_pyhanko() -> None:
    try:
        import pyhanko  # noqa: F401,PLC0415
    except ImportError as exc:
        raise SigningUnavailableError("pyHanko is not installed. Add it to the project dependencies.") from exc


class PyHankoPades:
    """IPadesSigner: подпись дописыванием и проверка всех подписей файла без сети."""

    async def sign_incremental(self, source: Path, output: Path, field_name: str, key_dir: Path, reason: str) -> None:
        _ensure_pyhanko()
        await _sign_invisible(source, output, field_name, key_dir, reason)

    async def validate(self, pdf: Path) -> list[PadesCheck]:
        _ensure_pyhanko()
        return await _validate_all(pdf)


async def _sign_invisible(source: Path, output: Path, field_name: str, key_dir: Path, reason: str) -> None:
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter  # noqa: PLC0415
    from pyhanko.sign import fields, signers  # noqa: PLC0415
    from pyhanko.sign.fields import SigSeedSubFilter  # noqa: PLC0415

    cms_signer = signers.SimpleSigner.load(str(key_dir / "key.pem"), str(key_dir / "cert.pem"))
    meta = signers.PdfSignatureMetadata(field_name=field_name, subfilter=SigSeedSubFilter.PADES, reason=reason or None)
    with source.open("rb") as inf:
        writer = IncrementalPdfFileWriter(inf, strict=False)
        # Невидимое поле: картинка подписанта уже стоит в зафиксированном PDF (docs/design/signature-plan.md, раздел 4).
        fields.append_signature_field(writer, fields.SigFieldSpec(sig_field_name=field_name))
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("wb") as outf:
            await signers.PdfSigner(meta, signer=cms_signer).async_sign_pdf(writer, output=outf)
    logger.debug("pyhanko_signer: incremental signature", field=field_name)


async def _validate_all(pdf: Path) -> list[PadesCheck]:
    import hashlib  # noqa: PLC0415

    from pyhanko.pdf_utils.reader import PdfFileReader  # noqa: PLC0415
    from pyhanko.sign.diff_analysis import ModificationLevel  # noqa: PLC0415
    from pyhanko.sign.validation import async_validate_pdf_signature  # noqa: PLC0415
    from pyhanko.sign.validation.status import SignatureCoverageLevel  # noqa: PLC0415
    from pyhanko_certvalidator import ValidationContext  # noqa: PLC0415

    checks: list[PadesCheck] = []
    with pdf.open("rb") as fh:
        reader = PdfFileReader(fh, strict=False)
        for sig in reader.embedded_regular_signatures:
            cert = sig.signer_cert
            # Доверие цепочке здесь не решается (это делает проверка корней Студии): сертификат подписанта
            # объявлен корнем, чтобы проверка целостности не шумела ошибками построения пути и не ходила в сеть.
            context = ValidationContext(trust_roots=[cert] if cert is not None else [], allow_fetching=False)
            status = await async_validate_pdf_signature(sig, context)
            byte_range = [int(x) for x in sig.byte_range]
            level = status.modification_level
            checks.append(
                PadesCheck(
                    field_name=sig.field_name,
                    intact=bool(status.intact and status.valid),
                    covers=status.coverage is not None and status.coverage >= SignatureCoverageLevel.ENTIRE_REVISION,
                    modifications_ok=status.docmdp_ok is not False
                    and (level is None or level <= ModificationLevel.FORM_FILLING),
                    revision_size=byte_range[2] + byte_range[3],
                    signer=cert.subject.native.get("common_name", "") if cert is not None else "",
                    signer_id=hashlib.sha256(cert.dump()).hexdigest() if cert is not None else "",
                    signed_at=status.signer_reported_dt.isoformat() if status.signer_reported_dt else None,
                )
            )
    return checks
