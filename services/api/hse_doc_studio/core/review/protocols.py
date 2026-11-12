"""Порты ревью: хранилище тредов, канал событий для открытых сессий редактирования и PDF документа."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from hse_doc_studio.core.review.entities import PdfRect, ReviewComment, ReviewThread, ThreadStatus


class IReviewRepository(Protocol):
    async def list_threads(
        self, project_id: UUID, *, path: str | None = None, status: ThreadStatus | None = None
    ) -> list[ReviewThread]:
        """Треды проекта с комментариями; свежие по активности первыми."""
        ...

    async def get_thread(self, project_id: UUID, thread_id: str) -> ReviewThread | None: ...

    async def find_comment(self, project_id: UUID, comment_id: str) -> tuple[ReviewThread, ReviewComment] | None: ...

    async def count_threads(self, project_id: UUID, path: str) -> int: ...

    async def add_thread(self, thread: ReviewThread) -> None:
        """Тред вместе с его комментариями (первый это корневой)."""
        ...

    async def add_comment(self, project_id: UUID, comment: ReviewComment) -> bool:
        """False, если треда уже нет."""
        ...

    async def edit_comment(self, project_id: UUID, comment_id: str, body: str, edited_at: datetime) -> bool: ...

    async def delete_comment(self, project_id: UUID, comment_id: str) -> bool: ...

    async def set_status(
        self,
        project_id: UUID,
        thread_id: str,
        status: ThreadStatus,
        *,
        by_id: str | None,
        by_name: str | None,
        at: datetime,
    ) -> bool: ...

    async def delete_thread(self, project_id: UUID, thread_id: str) -> bool: ...


class IReviewEvents(Protocol):
    """Сообщение открытым сессиям файла, что ревью изменилось (панель обновляется без опроса)."""

    async def review_changed(self, project_id: UUID, path: str) -> None: ...


@dataclass(frozen=True)
class DocumentPdf:
    """PDF, который показывает превью документа: путь от корня проекта и sha256 содержимого."""

    doc_id: str
    path: str
    sha: str


@dataclass(frozen=True)
class SourcePoint:
    """Файл проекта и строка (с единицы), откуда пришёл текст на странице PDF."""

    path: str
    line: int


@dataclass(frozen=True)
class LinePlace:
    """Где на PDF строка исходника: страница и прямоугольники строк набора."""

    page: int
    rects: tuple[PdfRect, ...]


class IDocumentPdfs(Protocol):
    """PDF документа и SyncTeX его последней сборки (раздел 2.4). Документа нет: NotFoundError."""

    async def pdf(self, project_id: UUID, doc_id: str) -> DocumentPdf | None:
        """None, если PDF ещё не собран (или у документа нет PDF-предпросмотра)."""
        ...

    async def source_at(self, project_id: UUID, doc_id: str, page: int, x: float, y: float) -> SourcePoint | None:
        """Обратный SyncTeX: файл проекта и строка под точкой; None без SyncTeX или вне текста."""
        ...

    async def place_line(self, project_id: UUID, doc_id: str, path: str, line: int) -> LinePlace | None:
        """Прямой SyncTeX: где на PDF строка файла проекта (или ближайшая к ней строка, давшая вывод)."""
        ...

    async def source_files(self, project_id: UUID, doc_id: str) -> frozenset[str]:
        """Файлы проекта, из которых собран документ (входные файлы SyncTeX)."""
        ...
