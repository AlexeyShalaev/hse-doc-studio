"""Ревью-комментарии в Postgres: треды с комментариями, правка, статус, перенос пути."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select, update

from hse_doc_studio.core.review.entities import Anchor, ReviewComment, ReviewThread, ThreadStatus
from hse_doc_studio.infra.db.orm.review import ReviewCommentRow, ReviewThreadRow
from hse_doc_studio.infra.db.session import SessionProvider


def _anchor(raw: Any) -> Anchor:
    data = raw if isinstance(raw, dict) else {}
    return Anchor(
        quote=str(data.get("quote", "")),
        prefix=str(data.get("prefix", "")),
        suffix=str(data.get("suffix", "")),
        start=int(data.get("start", 0)),
        end=int(data.get("end", 0)),
    )


def _comment(row: ReviewCommentRow) -> ReviewComment:
    mentions = row.mentions if isinstance(row.mentions, list) else []
    return ReviewComment(
        id=row.id,
        thread_id=row.thread_id,
        author_id=row.author_id,
        author_name=row.author_name,
        body=row.body,
        mentions=tuple(str(m) for m in mentions),
        created_at=row.created_at,
        edited_at=row.edited_at,
    )


def _thread(row: ReviewThreadRow, comments: list[ReviewCommentRow]) -> ReviewThread:
    return ReviewThread(
        id=row.id,
        project_id=str(row.project_id),
        path=row.path,
        anchor=_anchor(row.anchor),
        status=ThreadStatus(row.status),
        created_by=row.created_by,
        created_by_name=row.created_by_name,
        created_at=row.created_at,
        updated_at=row.updated_at,
        resolved_by=row.resolved_by,
        resolved_by_name=row.resolved_by_name,
        resolved_at=row.resolved_at,
        comments=tuple(_comment(c) for c in comments),
    )


def _comment_row(comment: ReviewComment) -> ReviewCommentRow:
    return ReviewCommentRow(
        id=comment.id,
        thread_id=comment.thread_id,
        author_id=comment.author_id,
        author_name=comment.author_name,
        body=comment.body,
        mentions=list(comment.mentions),
        created_at=comment.created_at,
        edited_at=comment.edited_at,
    )


class PostgresReviewRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def _load(self, rows: list[ReviewThreadRow]) -> list[ReviewThread]:
        if not rows:
            return []
        async with self._sessions.use() as session:
            comments = (
                await session.execute(
                    select(ReviewCommentRow)
                    .where(ReviewCommentRow.thread_id.in_([r.id for r in rows]))
                    .order_by(ReviewCommentRow.created_at, ReviewCommentRow.id)
                )
            ).scalars()
            by_thread: dict[str, list[ReviewCommentRow]] = defaultdict(list)
            for comment in comments:
                by_thread[comment.thread_id].append(comment)
        return [_thread(r, by_thread[r.id]) for r in rows]

    async def list_threads(
        self, project_id: UUID, *, path: str | None = None, status: ThreadStatus | None = None
    ) -> list[ReviewThread]:
        stmt = select(ReviewThreadRow).where(ReviewThreadRow.project_id == project_id)
        if path is not None:
            stmt = stmt.where(ReviewThreadRow.path == path)
        if status is not None:
            stmt = stmt.where(ReviewThreadRow.status == status.value)
        stmt = stmt.order_by(ReviewThreadRow.updated_at.desc(), ReviewThreadRow.id.desc())
        async with self._sessions.use() as session:
            rows = list((await session.execute(stmt)).scalars())
            return await self._load(rows)

    async def get_thread(self, project_id: UUID, thread_id: str) -> ReviewThread | None:
        stmt = select(ReviewThreadRow).where(ReviewThreadRow.project_id == project_id, ReviewThreadRow.id == thread_id)
        async with self._sessions.use() as session:
            row = (await session.execute(stmt)).scalar_one_or_none()
            return (await self._load([row]))[0] if row is not None else None

    async def find_comment(self, project_id: UUID, comment_id: str) -> tuple[ReviewThread, ReviewComment] | None:
        stmt = (
            select(ReviewCommentRow.thread_id)
            .join(ReviewThreadRow, ReviewThreadRow.id == ReviewCommentRow.thread_id)
            .where(ReviewCommentRow.id == comment_id, ReviewThreadRow.project_id == project_id)
        )
        async with self._sessions.use() as session:
            thread_id = (await session.execute(stmt)).scalar_one_or_none()
        if thread_id is None:
            return None
        thread = await self.get_thread(project_id, thread_id)
        if thread is None:
            return None
        found = next((c for c in thread.comments if c.id == comment_id), None)
        return (thread, found) if found is not None else None

    async def count_threads(self, project_id: UUID, path: str) -> int:
        stmt = (
            select(func.count())
            .select_from(ReviewThreadRow)
            .where(ReviewThreadRow.project_id == project_id, ReviewThreadRow.path == path)
        )
        async with self._sessions.use() as session:
            return int((await session.execute(stmt)).scalar_one())

    async def add_thread(self, thread: ReviewThread) -> None:
        async with self._sessions.use() as session:
            session.add(
                ReviewThreadRow(
                    id=thread.id,
                    project_id=UUID(thread.project_id),
                    path=thread.path,
                    anchor={
                        "quote": thread.anchor.quote,
                        "prefix": thread.anchor.prefix,
                        "suffix": thread.anchor.suffix,
                        "start": thread.anchor.start,
                        "end": thread.anchor.end,
                    },
                    status=thread.status.value,
                    created_by=thread.created_by,
                    created_by_name=thread.created_by_name,
                    created_at=thread.created_at,
                    updated_at=thread.updated_at,
                )
            )
            await session.flush()
            session.add_all([_comment_row(c) for c in thread.comments])

    async def add_comment(self, project_id: UUID, comment: ReviewComment) -> bool:
        async with self._sessions.use() as session:
            touched = await session.execute(
                update(ReviewThreadRow)
                .where(ReviewThreadRow.project_id == project_id, ReviewThreadRow.id == comment.thread_id)
                .values(updated_at=comment.created_at)
                .returning(ReviewThreadRow.id)
            )
            if touched.first() is None:
                return False
            session.add(_comment_row(comment))
            return True

    async def edit_comment(self, project_id: UUID, comment_id: str, body: str, edited_at: datetime) -> bool:
        owned = select(ReviewThreadRow.id).where(ReviewThreadRow.project_id == project_id)
        async with self._sessions.use() as session:
            result = await session.execute(
                update(ReviewCommentRow)
                .where(ReviewCommentRow.id == comment_id, ReviewCommentRow.thread_id.in_(owned))
                .values(body=body, edited_at=edited_at)
                .returning(ReviewCommentRow.id)
            )
            return result.first() is not None

    async def delete_comment(self, project_id: UUID, comment_id: str) -> bool:
        owned = select(ReviewThreadRow.id).where(ReviewThreadRow.project_id == project_id)
        async with self._sessions.use() as session:
            result = await session.execute(
                delete(ReviewCommentRow)
                .where(ReviewCommentRow.id == comment_id, ReviewCommentRow.thread_id.in_(owned))
                .returning(ReviewCommentRow.id)
            )
            return result.first() is not None

    async def set_status(
        self,
        project_id: UUID,
        thread_id: str,
        status: ThreadStatus,
        *,
        by_id: str | None,
        by_name: str | None,
        at: datetime,
    ) -> bool:
        resolved = status is ThreadStatus.resolved
        async with self._sessions.use() as session:
            result = await session.execute(
                update(ReviewThreadRow)
                .where(ReviewThreadRow.project_id == project_id, ReviewThreadRow.id == thread_id)
                .values(
                    status=status.value,
                    updated_at=at,
                    resolved_by=by_id if resolved else None,
                    resolved_by_name=by_name if resolved else None,
                    resolved_at=at if resolved else None,
                )
                .returning(ReviewThreadRow.id)
            )
            return result.first() is not None

    async def delete_thread(self, project_id: UUID, thread_id: str) -> bool:
        async with self._sessions.use() as session:
            result = await session.execute(
                delete(ReviewThreadRow)
                .where(ReviewThreadRow.project_id == project_id, ReviewThreadRow.id == thread_id)
                .returning(ReviewThreadRow.id)
            )
            return result.first() is not None
