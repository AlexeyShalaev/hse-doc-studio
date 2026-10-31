"""Сущности ревью: тред на фрагмент файла и комментарии в нём (docs/design/stage5-review-realtime.md)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from hse_doc_studio.core.errors import NotFoundError

BODY_MAX = 4000
QUOTE_MAX = 2000
CONTEXT_MAX = 80
MENTIONS_MAX = 20
PATH_MAX = 512
# Предел открытых и закрытых тредов на файл: страница не должна превращаться в свалку.
THREADS_PER_FILE_MAX = 500
EXCERPT_MAX = 140


class ThreadStatus(StrEnum):
    open = "open"
    resolved = "resolved"


class ReviewInputError(ValueError):
    """Запрос ревью не прошёл проверку: пустой или слишком длинный текст, пустая цитата, чужое упоминание."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ReviewNotFoundError(NotFoundError):
    """Нет треда, комментария или файла, к которому он привязан."""


class ReviewConflictError(Exception):
    """Действие несовместимо с состоянием: лимит тредов на файл, удаление треда с чужими ответами."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Anchor:
    """Привязка к фрагменту по цитате (как TextQuoteSelector).

    Смещения `start` и `end` (кодовые точки) только подсказка, где искать первым; настоящая привязка это цитата
    с контекстом до и после: она переживает любые правки, в том числе пришедшие из git. Разрешает привязку клиент
    по живому тексту (`web-app/.../anchor.ts`), сервер её не интерпретирует.
    """

    quote: str
    prefix: str = ""
    suffix: str = ""
    start: int = 0
    end: int = 0


@dataclass(frozen=True)
class ReviewComment:
    id: str
    thread_id: str
    author_id: str | None
    author_name: str
    body: str
    mentions: tuple[str, ...]
    created_at: datetime
    edited_at: datetime | None = None


@dataclass(frozen=True)
class ReviewThread:
    id: str
    project_id: str
    path: str
    anchor: Anchor
    status: ThreadStatus
    created_by: str | None
    created_by_name: str
    created_at: datetime
    updated_at: datetime
    resolved_by: str | None = None
    resolved_by_name: str | None = None
    resolved_at: datetime | None = None
    comments: tuple[ReviewComment, ...] = field(default_factory=tuple)

    @property
    def participants(self) -> frozenset[str]:
        """Те, кто писал в треде (без гостей без id и пустых авторов)."""
        return frozenset(c.author_id for c in self.comments if c.author_id)


@dataclass(frozen=True)
class MentionCandidate:
    user_id: str
    name: str
    detail: str | None


_WS = re.compile(r"\s+")


def excerpt_of(text: str, limit: int = EXCERPT_MAX) -> str:
    """Короткая выдержка для уведомления: пробелы схлопнуты, длинное обрезано."""
    flat = _WS.sub(" ", text).strip()
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"
