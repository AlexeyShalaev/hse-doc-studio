"""Keep the last few compiled PDFs per document for the visual-diff feature.

The compile pipeline overwrites `.build/<doc>/<stem>.pdf` (moved next to its
source) on every successful build, so the previous render is lost. We copy each
successful PDF into `.hse-studio/pdf-archive/<doc_id>/<compile_id>.pdf` (pruned
to the last N) so the preview can diff the current build against an earlier one.

Written with plain `pathlib`/`shutil` rather than the file repository because
`.hse-studio` is intentionally off-limits to the repo's mutating API — internal
app code (compiles, git) writes there directly, same as this does.
"""

from __future__ import annotations

import contextlib
import shutil
from pathlib import Path, PurePosixPath
from uuid import UUID

import structlog

logger = structlog.get_logger()

_ARCHIVE_DIRNAME = "pdf-archive"
_KEEP = 8


def _archive_dir(project_folder: Path, doc_id: str) -> Path:
    return project_folder / ".hse-studio" / _ARCHIVE_DIRNAME / doc_id


def archived_pdf_path(project_folder: Path, doc_id: str, compile_id: UUID | str) -> Path:
    return _archive_dir(project_folder, doc_id) / f"{compile_id}.pdf"


def _doc_dir(project_folder: Path, source_file: str) -> Path:
    src = PurePosixPath(source_file.replace("\\", "/"))
    src_parent = src.parent.as_posix() if src.parent.parts else ""
    return project_folder if src_parent in ("", ".") else project_folder / src_parent


def _final_pdf_path(project_folder: Path, source_file: str) -> Path:
    src = PurePosixPath(source_file.replace("\\", "/"))
    return _doc_dir(project_folder, source_file) / f"{src.stem}.pdf"


def _built_pdf_path(project_folder: Path, doc_id: str, source_file: str) -> Path:
    src = PurePosixPath(source_file.replace("\\", "/"))
    return _doc_dir(project_folder, source_file) / ".build" / doc_id / f"{src.stem}.pdf"


def archive_compiled_pdf(project_folder: Path, doc_id: str, compile_id: UUID, source_file: str) -> None:
    """Copy the just-built PDF into the per-doc archive, pruning to the last N.

    Normally the executor moves the built PDF next to its source and `.build`
    holds no copy. If that move was skipped because the neighbour file is
    locked (open in a desktop viewer), the FRESH pdf is still in `.build` —
    archive that one, not the stale neighbour.
    """
    built_pdf = _built_pdf_path(project_folder, doc_id, source_file)
    source_pdf = built_pdf if built_pdf.exists() else _final_pdf_path(project_folder, source_file)
    if not source_pdf.exists():
        return
    dest_dir = _archive_dir(project_folder, doc_id)
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_pdf, dest_dir / f"{compile_id}.pdf")
        _prune(dest_dir)
    except OSError as exc:
        logger.warning("pdf archive failed", doc_id=doc_id, exc=str(exc))


def _prune(dest_dir: Path) -> None:
    pdfs = sorted(
        dest_dir.glob("*.pdf"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in pdfs[_KEEP:]:
        with contextlib.suppress(OSError):
            old.unlink()
