"""Формы ревью-комментариев (docs/design/stage5-review-realtime.md)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from hse_doc_studio.api.schemas.common import StrictModel
from hse_doc_studio.core.review.entities import BODY_MAX, CONTEXT_MAX, MENTIONS_MAX, PATH_MAX, QUOTE_MAX

ThreadStatusName = Literal["open", "resolved"]


class AnchorModel(StrictModel):
    quote: str = Field(max_length=QUOTE_MAX)
    prefix: str = Field(default="", max_length=CONTEXT_MAX * 4)
    suffix: str = Field(default="", max_length=CONTEXT_MAX * 4)
    start: int = Field(default=0, ge=0)
    end: int = Field(default=0, ge=0)


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
    anchor: AnchorModel
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
