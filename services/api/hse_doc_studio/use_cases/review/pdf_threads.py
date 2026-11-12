"""Комментарии из превью PDF (docs/design/stage5-review-realtime.md, 2.4).

Тред из превью по возможности привязывается к исходнику: обратный SyncTeX даёт файл и строку, рядом с ней
ищется выделенный текст (`core.review.pdf_match`). Не нашлось или исходника нет: тред привязан к месту в PDF.
Права те же, что у тредов в редакторе: писать с `COMMENT`, читать с `SOURCES_READ`.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from hse_doc_studio.core.access.actions import Action
from hse_doc_studio.core.access.checker import IProjectAccessChecker
from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.access.repositories import IProjectAccessDirectory, IProjectAclRepository
from hse_doc_studio.core.collab.ports import ITextStore
from hse_doc_studio.core.identity.session_policy import utc_now
from hse_doc_studio.core.invitations.protocols import INotifier, IProjectCards
from hse_doc_studio.core.review.anchor import make_anchor, resolve_anchor
from hse_doc_studio.core.review.entities import (
    PDF_RECTS_MAX,
    QUOTE_MAX,
    Anchor,
    PdfAnchor,
    PdfPlace,
    PdfRect,
    ReviewConflictError,
    ReviewInputError,
    ReviewThread,
)
from hse_doc_studio.core.review.pdf_match import locate_in_source, visible_text
from hse_doc_studio.core.review.protocols import IDocumentPdfs, IReviewEvents, IReviewRepository, SourcePoint
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.review.threads import _clean_body, _ReviewBase

_COORD_MAX = 100_000.0


@dataclass(frozen=True)
class NewPdfThread:
    doc_id: str
    page: int
    rects: tuple[PdfRect, ...]
    text: str
    body: str
    mentions: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlacedThread:
    thread: ReviewThread
    # None: место на текущем PDF не найдено (цитата исчезла из файла или строка ничего не набрала).
    place: PdfPlace | None


@dataclass(frozen=True)
class DocumentReview:
    # sha256 PDF, который сейчас показывает превью; None, если PDF ещё не собран.
    build_sha: str | None
    items: tuple[PlacedThread, ...]


def _clean_selection(new: NewPdfThread) -> tuple[str, tuple[PdfRect, ...]]:
    text = new.text.strip()
    if not text:
        raise ReviewInputError("empty_quote", "Select a fragment to comment on")
    if len(text) > QUOTE_MAX:
        raise ReviewInputError("quote_too_long", f"The fragment is longer than {QUOTE_MAX} characters")
    rects = new.rects
    if new.page < 1 or not rects or len(rects) > PDF_RECTS_MAX:
        raise ReviewInputError("bad_rects", "Select the text again")
    for r in rects:
        values = (r.x, r.y, r.width, r.height)
        if not all(math.isfinite(v) and abs(v) <= _COORD_MAX for v in values) or r.width < 0 or r.height < 0:
            raise ReviewInputError("bad_rects", "Select the text again")
    return text, rects


def _center(rect: PdfRect) -> tuple[float, float]:
    return rect.x + rect.width / 2, rect.y + rect.height / 2


class _PdfReviewBase(_ReviewBase):
    def __init__(
        self,
        reviews: IReviewRepository,
        access: IProjectAccessChecker,
        acls: IProjectAclRepository,
        cards: IProjectCards,
        directory: IProjectAccessDirectory,
        notifier: INotifier,
        events: IReviewEvents,
        store: ITextStore,
        uow: IUnitOfWork,
        pdfs: IDocumentPdfs,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        super().__init__(reviews, access, acls, cards, directory, notifier, events, store, uow, clock)
        self._pdfs = pdfs


class CreatePdfReviewThreadUC(_PdfReviewBase):
    async def execute(self, project_id: UUID, new: NewPdfThread) -> ReviewThread:
        await self._access.require(project_id, Action.COMMENT)
        actor = require_actor()
        body = _clean_body(new.body)
        text, rects = _clean_selection(new)
        pdf = await self._pdfs.pdf(project_id, new.doc_id)
        if pdf is None:
            raise ReviewConflictError("pdf_missing", "The document has no built PDF yet")
        await self._access.require(project_id, Action.FILES_READ, pdf.path)
        found = await self._in_source(project_id, new.doc_id, new.page, rects, text)
        if found is not None:
            path, anchor = found
            return await self._open_thread(project_id, path, anchor, body, new.mentions, actor)
        pdf_anchor = PdfAnchor(doc_id=new.doc_id, page=new.page, rects=rects, text=text, build_sha=pdf.sha)
        return await self._open_thread(project_id, pdf.path, pdf_anchor, body, new.mentions, actor)

    async def _in_source(
        self, project_id: UUID, doc_id: str, page: int, rects: tuple[PdfRect, ...], text: str
    ) -> tuple[str, Anchor] | None:
        """Файл и цитата из исходника для выделения или None, если надёжной находки нет."""
        points: list[SourcePoint] = []
        for rect in dict.fromkeys((rects[0], rects[-1])):
            point = await self._pdfs.source_at(project_id, doc_id, page, *_center(rect))
            if point is not None:
                points.append(point)
        for path in dict.fromkeys(p.path for p in points):
            if not await self._may(project_id, Action.FILES_READ, path):
                continue
            snapshot = await self._store.read(project_id, path)
            if snapshot is None:
                continue
            span = locate_in_source(snapshot.text, [p.line for p in points if p.path == path], text)
            if span is not None:
                return path, make_anchor(snapshot.text, span.start, span.end)
        return None


class ListDocumentReviewUC(_PdfReviewBase):
    """Треды документа для превью и их места на текущем PDF."""

    async def execute(self, project_id: UUID, doc_id: str) -> DocumentReview:
        await self._access.require(project_id, Action.SOURCES_READ)
        pdf = await self._pdfs.pdf(project_id, doc_id)
        files = await self._pdfs.source_files(project_id, doc_id)
        texts: dict[str, str | None] = {}
        items: list[PlacedThread] = []
        for thread in await self._reviews.list_threads(project_id):
            anchor = thread.anchor
            if isinstance(anchor, PdfAnchor):
                if anchor.doc_id != doc_id:
                    continue
                exact = pdf is not None and pdf.sha == anchor.build_sha
                items.append(PlacedThread(thread, PdfPlace(anchor.page, anchor.rects, anchor.text, exact)))
            elif thread.path in files:
                if thread.path not in texts:
                    snapshot = await self._store.read(project_id, thread.path)
                    texts[thread.path] = snapshot.text if snapshot is not None else None
                items.append(PlacedThread(thread, await self._place(project_id, doc_id, thread, texts[thread.path])))
        return DocumentReview(build_sha=pdf.sha if pdf is not None else None, items=tuple(items))

    async def _place(self, project_id: UUID, doc_id: str, thread: ReviewThread, text: str | None) -> PdfPlace | None:
        anchor = thread.anchor
        if text is None or not isinstance(anchor, Anchor):
            return None
        resolved = resolve_anchor(text, anchor)
        if resolved is None:
            return None
        line = text.count("\n", 0, resolved.start) + 1
        place = await self._pdfs.place_line(project_id, doc_id, thread.path, line)
        if place is None:
            return None
        return PdfPlace(place.page, place.rects, visible_text(text[resolved.start : resolved.end]), exact=False)
