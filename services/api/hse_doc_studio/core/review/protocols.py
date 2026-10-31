"""Порты ревью: хранилище тредов и канал событий для открытых сессий редактирования."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from hse_doc_studio.core.review.entities import ReviewComment, ReviewThread, ThreadStatus


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
