"""PDF документа и его SyncTeX для комментариев из превью (docs/design/stage5-review-realtime.md, 2.4)."""

from __future__ import annotations

import hashlib
import posixpath
from collections import OrderedDict
from pathlib import Path
from uuid import UUID

from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.projects.locator import IProjectLocator
from hse_doc_studio.core.review.entities import PdfRect
from hse_doc_studio.core.review.protocols import DocumentPdf, LinePlace, SourcePoint
from hse_doc_studio.infra.synctex.parser import SyncBox, SyncTexDocument
from hse_doc_studio.use_cases.documents.get_document import GetDocumentInput, GetDocumentUC
from hse_doc_studio.use_cases.synctex.query_synctex import LoadedSyncTex, SyncTexUC

# Файлы, в которых имеет смысл искать текст выделения.
_TEXT_SUFFIXES = (".tex", ".ltx", ".md", ".txt", ".bib")
# Строка набора выше этого (пт) это рисунок или целый абзац, а не строка текста.
_LINE_HEIGHT_MAX = 40.0
_RECTS_MAX = 8
_SHA_CACHE: OrderedDict[tuple[str, int, int], str] = OrderedDict()
_SHA_CACHE_MAX = 64


def _sha256(path: Path) -> str:
    stat = path.stat()
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    cached = _SHA_CACHE.get(key)
    if cached is not None:
        _SHA_CACHE.move_to_end(key)
        return cached
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    value = digest.hexdigest()
    _SHA_CACHE[key] = value
    while len(_SHA_CACHE) > _SHA_CACHE_MAX:
        _SHA_CACHE.popitem(last=False)
    return value


def project_path(raw: str, source_file: str, folder: Path) -> str | None:
    """Входной файл SyncTeX как путь от корня проекта; None, если такого файла в проекте нет.

    Сборка в контейнере видит проект в `/work` и идёт из каталога главного файла (`/work/a/./b.tex`,
    `/work/a/../common/meta.tex`); на раннере или у локального TeX префикс другой, поэтому чужой абсолютный путь
    укорачивается слева, пока не найдётся файл проекта.
    """
    path = raw.strip().replace("\\", "/")
    if path.startswith("/work/"):
        candidates = [path[len("/work/") :]]
    elif path.startswith("/") or (len(path) > 1 and path[1] == ":"):
        parts = [p for p in path.split("/") if p]
        candidates = ["/".join(parts[k:]) for k in range(1, len(parts))]
    else:
        base = posixpath.dirname(source_file)
        candidates = [posixpath.join(base, path), path]
    root = folder.resolve()
    for candidate in candidates:
        rel = posixpath.normpath(candidate)
        if rel.startswith("../") or rel in (".", "..") or rel.startswith("/"):
            continue
        target = (folder / rel).resolve()
        if target.is_relative_to(root) and target.is_file():
            return rel
    return None


def _tags_by_path(loaded: LoadedSyncTex) -> dict[int, str]:
    out: dict[int, str] = {}
    for tag, raw in loaded.document.input_files.items():
        if not raw.lower().endswith(_TEXT_SUFFIXES):
            continue
        rel = project_path(raw, loaded.source_file, loaded.folder)
        if rel is not None:
            out[tag] = rel
    return out


def _line_rects(boxes: list[SyncBox]) -> tuple[PdfRect, ...]:
    """Строки набора из записей SyncTeX одной страницы: записи с общей базовой линией сливаются в прямоугольник."""
    rows: dict[float, list[SyncBox]] = {}
    for box in boxes:
        tall = box.height + box.depth
        if box.width <= 0 or tall <= 0 or tall > _LINE_HEIGHT_MAX:
            continue
        rows.setdefault(round(box.v, 0), []).append(box)
    rects = []
    for baseline, row in sorted(rows.items()):
        left = min(b.h for b in row)
        right = max(b.h + b.width for b in row)
        height = max(b.height for b in row)
        depth = max(b.depth for b in row)
        rects.append(PdfRect(x=left, y=baseline - height, width=right - left, height=height + depth))
    if not rects and boxes:
        first = min(boxes, key=lambda b: (b.v, b.h))
        rects.append(PdfRect(x=first.h, y=max(0.0, first.v - 10), width=12, height=12))
    return tuple(rects[:_RECTS_MAX])


class DocumentPdfs:
    """`IDocumentPdfs` поверх документа (пути выхода и PDF-предпросмотра) и SyncTeX его последней сборки."""

    def __init__(self, documents: GetDocumentUC, synctex: SyncTexUC, locator: IProjectLocator) -> None:
        self._documents = documents
        self._synctex = synctex
        self._locator = locator

    async def pdf(self, project_id: UUID, doc_id: str) -> DocumentPdf | None:
        found = await self._documents.execute(GetDocumentInput(project_id=project_id, doc_id=doc_id))
        output = found.output_file or ""
        rel = output if output.lower().endswith(".pdf") else found.preview_file
        if not rel:
            return None
        located = await self._locator.locate(project_id)
        if located is None:
            raise NotFoundError("Project not found")
        target = located[0] / rel
        if not target.is_file():
            return None
        return DocumentPdf(doc_id=doc_id, path=rel, sha=_sha256(target))

    async def _loaded(self, project_id: UUID, doc_id: str) -> LoadedSyncTex | None:
        try:
            return await self._synctex.load(project_id, doc_id)
        except ValueError:
            return None

    async def source_at(self, project_id: UUID, doc_id: str, page: int, x: float, y: float) -> SourcePoint | None:
        loaded = await self._loaded(project_id, doc_id)
        if loaded is None:
            return None
        hit = loaded.document.inverse(page, x, y)
        if hit is None:
            return None
        raw, line, _column = hit
        if not raw.lower().endswith(_TEXT_SUFFIXES):
            return None
        rel = project_path(raw, loaded.source_file, loaded.folder)
        return SourcePoint(path=rel, line=line) if rel is not None else None

    async def place_line(self, project_id: UUID, doc_id: str, path: str, line: int) -> LinePlace | None:
        loaded = await self._loaded(project_id, doc_id)
        if loaded is None:
            return None
        tags = {tag for tag, rel in _tags_by_path(loaded).items() if rel == path}
        if not tags:
            return None
        boxes = _boxes_near(loaded.document, tags, line)
        if not boxes:
            return None
        page = min(b.page for b in boxes)
        on_page = [b for b in boxes if b.page == page]
        return LinePlace(page=page, rects=_line_rects(on_page))

    async def source_files(self, project_id: UUID, doc_id: str) -> frozenset[str]:
        loaded = await self._loaded(project_id, doc_id)
        if loaded is None:
            return frozenset()
        return frozenset(_tags_by_path(loaded).values())


def _boxes_near(doc: SyncTexDocument, tags: set[int], line: int) -> list[SyncBox]:
    """Записи строки файла; если строка ничего не набрала (пустая, комментарий), то ближайшей набравшей."""
    exact = [b for b in doc.by_line.get(line, ()) if b.tag in tags]
    if exact:
        return exact
    best: int | None = None
    for candidate, boxes in doc.by_line.items():
        if any(b.tag in tags for b in boxes) and (best is None or abs(candidate - line) < abs(best - line)):
            best = candidate
    return [b for b in doc.by_line.get(best, ()) if b.tag in tags] if best is not None else []
