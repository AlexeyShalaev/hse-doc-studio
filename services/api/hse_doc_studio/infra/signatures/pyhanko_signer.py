"""Optional cryptographic PDF signing via pyHanko.

This module is the ONLY place in the codebase that imports pyHanko.  All
imports are deferred to method bodies so that the rest of the application
works normally when the `signing` extra is not installed.  If a method that
needs pyHanko is called without it installed a clear `SigningUnavailableError`
is raised — never an ImportError propagating up the stack.

Coordinate convention: all inputs use millimetres from the TOP-LEFT of the
page, identical to the `Stamp` dataclass in `pdf_stamper.py`.  The internal
coordinate flip to PDF user-space (points, bottom-left origin) follows the
same formula as `PdfStamper._build_overlay_page`.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import structlog

# 1 PDF point = 1/72 inch; 1 inch = 25.4 mm — same constants as coords.ts.
PT_PER_MM = 72.0 / 25.4
MM_PER_PT = 25.4 / 72.0

logger = structlog.get_logger()

__all__ = ["CryptoSignRequest", "PyHankoPdfSigner", "SigningUnavailableError"]


class SigningUnavailableError(RuntimeError):
    """Raised when pyHanko is not installed and crypto signing is requested."""


@dataclass(frozen=True)
class CryptoSignRequest:
    """One crypto-signature slot to embed in the PDF.

    `field_name` must be unique within the document.  `png_path` is optional:
    when provided the PNG is rendered as the visible appearance (image_crypto
    mode); when None the signature field is invisible (crypto_invisible mode).
    """

    field_name: str
    page: int  # 1-indexed
    x_mm: float  # mm from top-left
    y_mm: float
    width_mm: float
    aspect_ratio: float  # height / width; used only when png_path is set
    png_path: Path | None  # None → invisible signature
    identity_key_dir: Path  # directory with key.pem + cert.pem
    reason: str = ""


class PyHankoPdfSigner:
    """Signs a PDF with one or more PAdES signatures, one per `CryptoSignRequest`.

    Each request produces one incremental update appended to the file, so
    multiple signers never invalidate each other's signatures.

    Must be called with `await signer.sign(...)` — uses pyHanko's async API
    to avoid the `asyncio.run() cannot be called from a running event loop`
    error that occurs when `sign_pdf` (which calls asyncio.run internally) is
    invoked from within FastAPI's event loop.
    """

    async def sign(  # noqa: C901
        self,
        source_pdf: Path,
        output_pdf: Path,
        requests: list[CryptoSignRequest],
    ) -> None:
        if not requests:
            output_pdf.parent.mkdir(parents=True, exist_ok=True)
            output_pdf.write_bytes(source_pdf.read_bytes())
            return

        _ensure_pyhanko()

        current = source_pdf
        tmp_paths: list[Path] = []

        for i, req in enumerate(requests):
            is_last = i == len(requests) - 1
            if is_last:
                out = output_pdf
                out.parent.mkdir(parents=True, exist_ok=True)
            else:
                fd, tmp = tempfile.mkstemp(suffix=".pdf", prefix=".pyhanko_tmp_")
                os.close(fd)
                out = Path(tmp)
                tmp_paths.append(out)

            try:
                await _sign_one(current, out, req)
            except Exception as exc:
                logger.warning("pyhanko_signer: failed for field", field=req.field_name, exc=str(exc))
                raise
            finally:
                if tmp_paths and current != source_pdf:
                    prev = tmp_paths[-2] if len(tmp_paths) >= 2 else None
                    if prev and prev != source_pdf and prev.exists():
                        with contextlib.suppress(OSError):
                            prev.unlink()

            current = out

        for p in tmp_paths:
            if p != output_pdf and p.exists():
                with contextlib.suppress(OSError):
                    p.unlink()


# ---------------------------------------------------------------------------
# Internals — everything below this line imports pyHanko.
# ---------------------------------------------------------------------------


def _ensure_pyhanko() -> None:
    try:
        import pyhanko  # noqa: F401,PLC0415
    except ImportError as exc:
        raise SigningUnavailableError("pyHanko is not installed. Add it to the project dependencies.") from exc


def _page_dimensions(pdf_path: Path, page_index: int) -> tuple[float, float]:
    """Return (width_pt, height_pt) for page_index (0-based).

    Uses pypdf (already a base dep) rather than pyHanko's reader so that
    MediaBox inheritance from parent /Pages nodes is resolved correctly.
    """
    from pypdf import PdfReader  # noqa: PLC0415

    with pdf_path.open("rb") as f:
        r = PdfReader(f)
        mb = r.pages[page_index].mediabox
        return float(mb.width), float(mb.height)


def _placement_to_box(
    x_mm: float, y_mm: float, width_mm: float, aspect: float, page_h_pt: float
) -> tuple[float, float, float, float]:
    """mm/top-left → PDF user-space box (x1,y1,x2,y2) in points."""
    width_pt = width_mm * PT_PER_MM
    height_pt = width_pt * aspect
    x1 = x_mm * PT_PER_MM
    y_top_pt = y_mm * PT_PER_MM
    y1 = page_h_pt - y_top_pt - height_pt
    return (x1, y1, x1 + width_pt, y1 + height_pt)


async def _sign_one(source: Path, output: Path, req: CryptoSignRequest) -> None:  # noqa: PLC0415
    from pyhanko import stamp  # noqa: PLC0415
    from pyhanko.pdf_utils import images  # noqa: PLC0415
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter  # noqa: PLC0415
    from pyhanko.sign import fields, signers  # noqa: PLC0415
    from pyhanko.sign.fields import SigSeedSubFilter  # noqa: PLC0415

    key_path = req.identity_key_dir / "key.pem"
    cert_path = req.identity_key_dir / "cert.pem"
    if not key_path.exists() or not cert_path.exists():
        raise FileNotFoundError(f"Key material missing in {req.identity_key_dir}")

    cms_signer = signers.SimpleSigner.load(str(key_path), str(cert_path))

    page_index = req.page - 1
    _, page_h_pt = _page_dimensions(source, page_index)
    x1, y1, x2, y2 = _placement_to_box(req.x_mm, req.y_mm, req.width_mm, req.aspect_ratio, page_h_pt)
    # `SigFieldSpec.box` is declared as integral PDF user-space units, so round
    # to whole points here rather than handing it fractions: 1 pt = 1/72 in, so
    # the worst-case shift of the widget rectangle is 0.5 pt ≈ 0.18 mm — well
    # under the placement precision the mm-based UI can express anyway.
    box = (round(x1), round(y1), round(x2), round(y2))

    meta = signers.PdfSignatureMetadata(
        field_name=req.field_name,
        subfilter=SigSeedSubFilter.PADES,
        reason=req.reason or None,
    )

    with source.open("rb") as inf:
        w = IncrementalPdfFileWriter(inf)

        fields.append_signature_field(
            w,
            fields.SigFieldSpec(
                sig_field_name=req.field_name,
                on_page=page_index,
                box=box,
            ),
        )

        if req.png_path is not None and req.png_path.exists():
            pdf_signer = signers.PdfSigner(
                meta,
                signer=cms_signer,
                stamp_style=stamp.TextStampStyle(
                    stamp_text="",
                    background=images.PdfImage(str(req.png_path)),
                ),
            )
        else:
            pdf_signer = signers.PdfSigner(meta, signer=cms_signer)

        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("wb") as outf:
            # Use async_sign_pdf to avoid asyncio.run() conflicts when called
            # from within FastAPI's already-running event loop.
            await pdf_signer.async_sign_pdf(w, output=outf)

    logger.debug(
        "pyhanko_signer: signed",
        field=req.field_name,
        page=req.page,
        visible=req.png_path is not None,
    )
