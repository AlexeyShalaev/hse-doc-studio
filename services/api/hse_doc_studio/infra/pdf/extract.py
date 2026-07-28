from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader

from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.i18n import current_interface_language

# The truncation marker appended below is also recognised by read_pdf; both the
# RU and EN forms are kept in sync there (TRUNCATION_MARKERS).
_TRUNCATED = {Lang.ru: "[... обрезано]", Lang.en: "[... truncated]"}


def extract_pdf_text(data: bytes, *, pages: list[int] | None = None, max_chars: int = 8000) -> tuple[str, int]:
    """Extract text from a PDF, page by page, capped at `max_chars`.

    `pages` is an optional list of 1-based page numbers (out-of-range ignored);
    None reads from page 1. Each page is prefixed with a `--- Page N ---` marker
    (in the interface language) so the model can cite locations. Returns
    (text, total_page_count). Raises on a corrupt / non-PDF input (the caller
    turns that into a clean tool error).
    """
    en = current_interface_language() is Lang.en
    page_label = "Page" if en else "Стр."
    reader = PdfReader(BytesIO(data))
    total = len(reader.pages)
    indices = [p - 1 for p in pages] if pages else list(range(total))

    chunks: list[str] = []
    used = 0
    for idx in indices:
        if idx < 0 or idx >= total:
            continue
        text = (reader.pages[idx].extract_text() or "").strip()
        chunk = f"--- {page_label} {idx + 1} ---\n{text}"
        chunks.append(chunk)
        used += len(chunk)
        if used >= max_chars:
            break

    joined = "\n\n".join(chunks)
    if len(joined) > max_chars:
        joined = f"{joined[:max_chars]}\n{_TRUNCATED[Lang.en] if en else _TRUNCATED[Lang.ru]}"
    return joined, total
