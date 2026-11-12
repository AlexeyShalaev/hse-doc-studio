"""Формы ревью-комментариев (docs/design/stage5-review-realtime.md)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field

from hse_doc_studio.api.schemas.common import StrictModel
from hse_doc_studio.core.review.entities import (
    BODY_MAX,
    CONTEXT_MAX,
    MENTIONS_MAX,
    PATH_MAX,
    PDF_RECTS_MAX,
    QUOTE_MAX,
)

ThreadStatusName = Literal["open", "resolved"]


class AnchorModel(StrictModel):
    """Цитата из исходника; `kind` в запросе можно не передавать."""

    kind: Literal["text"] = "text"
    quote: str = Field(max_length=QUOTE_MAX)
    prefix: str = Field(default="", max_length=CONTEXT_MAX * 4)
    suffix: str = Field(default="", max_length=CONTEXT_MAX * 4)
    start: int = Field(default=0, ge=0)
    end: int = Field(default=0, ge=0)


class PdfRectModel(StrictModel):
    """Прямоугольник на странице в пунктах PDF от левого верхнего угла."""

    x: float
    y: float
    width: float = Field(ge=0)
    height: float = Field(ge=0)


class PdfAnchorModel(StrictModel):
    """Место в PDF документа (раздел 2.4 stage5-review-realtime.md)."""

    kind: Literal["pdf"]
    doc_id: str
    page: int = Field(ge=1)
    rects: list[PdfRectModel]
    text: str
    build_sha: str


ThreadAnchorModel = Annotated[AnchorModel | PdfAnchorModel, Field(discriminator="kind")]


class CreateThreadRequest(StrictModel):
    path: str = Field(min_length=1, max_length=PATH_MAX)
    anchor: AnchorModel
    body: str = Field(max_length=BODY_MAX * 2)
    mentions: list[str] = Field(default_factory=list, max_length=MENTIONS_MAX * 2)


class ReplyRequest(StrictModel):
    body: str = Field(max_length=BODY_MAX * 2)
    mentions: list[str] = Field(default_factory=list, max_length=MENTIONS_MAX * 2)


class EditCommentRequest(StrictModel):
    body: str = Field(max_length=BODY_MAX * 2)


class SetStatusRequest(StrictModel):
    status: ThreadStatusName


class CommentModel(StrictModel):
    id: str
    author_id: str | None
    author_name: str
    body: str
    mentions: list[str]
    created_at: datetime
    edited_at: datetime | None


class ThreadModel(StrictModel):
    id: str
    path: str
    anchor: ThreadAnchorModel
    status: ThreadStatusName
    created_by: str | None
    created_by_name: str
    created_at: datetime
    updated_at: datetime
    resolved_by_name: str | None
    resolved_at: datetime | None
    comments: list[CommentModel]


class ThreadList(StrictModel):
    items: list[ThreadModel]


class MentionCandidateModel(StrictModel):
    user_id: str
    name: str
    detail: str | None


class MentionCandidateList(StrictModel):
    items: list[MentionCandidateModel]


class CreatePdfThreadRequest(StrictModel):
    """Тред из превью PDF: выделение на странице (пункты от левого верхнего угла) и его текст."""

    doc_id: str = Field(min_length=1, max_length=128)
    page: int = Field(ge=1, le=100_000)
    rects: list[PdfRectModel] = Field(max_length=PDF_RECTS_MAX * 4)
    text: str = Field(max_length=QUOTE_MAX * 2)
    body: str = Field(max_length=BODY_MAX * 2)
    mentions: list[str] = Field(default_factory=list, max_length=MENTIONS_MAX * 2)


class PdfPlaceModel(StrictModel):
    """Где тред на текущем PDF. `exact`: прямоугольники точные; иначе клиент уточняет место поиском `text`."""

    page: int
    rects: list[PdfRectModel]
    text: str
    exact: bool


class PlacedThreadModel(StrictModel):
    thread: ThreadModel
    place: PdfPlaceModel | None


class DocumentReviewModel(StrictModel):
    build_sha: str | None
    items: list[PlacedThreadModel]
