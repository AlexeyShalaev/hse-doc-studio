"""Ревью-комментарии: треды, ответы, правка, статус, упоминания и уведомления во «Входящие».

Права: читать треды вправе тот, кто читает исходники; писать, отвечать и править своё — роль с COMMENT
(рецензент и выше, гость по ссылке с такой ролью); закрыть и открыть тред может его автор и тот, кто вправе
править файл; чужой комментарий удаляет только владелец проекта. Уведомления получают только люди с аккаунтом.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from hse_doc_studio.core.access.actions import Action
from hse_doc_studio.core.access.checker import IProjectAccessChecker, ProjectForbiddenError
from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.access.links import GUEST_SESSION_PREFIX
from hse_doc_studio.core.access.policy import can
from hse_doc_studio.core.access.repositories import AccessQuery, IProjectAccessDirectory, IProjectAclRepository
from hse_doc_studio.core.collab.ports import ITextStore
from hse_doc_studio.core.identity.session_policy import utc_now
from hse_doc_studio.core.invitations.entities import NotificationKind, NotificationPayload
from hse_doc_studio.core.invitations.protocols import INotifier, IProjectCards
from hse_doc_studio.core.listing import Window
from hse_doc_studio.core.review.entities import (
    BODY_MAX,
    CONTEXT_MAX,
    MENTIONS_MAX,
    PATH_MAX,
    QUOTE_MAX,
    THREADS_PER_FILE_MAX,
    Anchor,
    MentionCandidate,
    ReviewComment,
    ReviewConflictError,
    ReviewInputError,
    ReviewNotFoundError,
    ReviewThread,
    ThreadStatus,
    excerpt_of,
)
from hse_doc_studio.core.review.protocols import IReviewEvents, IReviewRepository
from hse_doc_studio.core.uow import IUnitOfWork

_log = logging.getLogger(__name__)
_EDITORS_NOTIFIED_MAX = 50


def _thread_id() -> str:
    return f"rvt_{uuid.uuid4().hex}"


def _comment_id() -> str:
    return f"rvc_{uuid.uuid4().hex}"


def _author_name(actor: Actor) -> str:
    return (actor.name or actor.email or "").strip() or "?"


def _clean_body(body: str) -> str:
    text = body.strip()
    if not text:
        raise ReviewInputError("empty_body", "Comment text is empty")
    if len(text) > BODY_MAX:
        raise ReviewInputError("body_too_long", f"Comment text is longer than {BODY_MAX} characters")
    return text


def _clean_anchor(anchor: Anchor) -> Anchor:
    if not anchor.quote.strip():
        raise ReviewInputError("empty_quote", "Select a fragment to comment on")
    if len(anchor.quote) > QUOTE_MAX:
        raise ReviewInputError("quote_too_long", f"The fragment is longer than {QUOTE_MAX} characters")
    start = max(0, anchor.start)
    return Anchor(
        quote=anchor.quote,
        prefix=anchor.prefix[-CONTEXT_MAX:],
        suffix=anchor.suffix[:CONTEXT_MAX],
        start=start,
        end=max(start, anchor.end),
    )


def _real_user(user_id: str | None) -> bool:
    return bool(user_id) and not str(user_id).startswith(GUEST_SESSION_PREFIX)


@dataclass(frozen=True)
class NewThread:
    path: str
    anchor: Anchor
    body: str
    mentions: tuple[str, ...] = ()


class _ReviewBase:
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
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._reviews = reviews
        self._access = access
        self._acls = acls
        self._cards = cards
        self._directory = directory
        self._notifier = notifier
        self._events = events
        self._store = store
        self._uow = uow
        self._clock = clock

    async def _may(self, project_id: UUID, action: Action, path: str | None = None) -> bool:
        try:
            await self._access.require(project_id, action, path)
        except ProjectForbiddenError:
            return False
        return True

    async def _thread(self, project_id: UUID, thread_id: str) -> ReviewThread:
        thread = await self._reviews.get_thread(project_id, thread_id)
        if thread is None:
            raise ReviewNotFoundError("Thread not found")
        return thread

    async def _valid_mentions(self, project_id: UUID, mentions: tuple[str, ...], actor: Actor) -> tuple[str, ...]:
        """Упоминания людей с аккаунтом, которые видят исходники проекта; остальные молча отбрасываются.

        Так упоминание не подтверждает постороннему, что человек состоит в проекте."""
        if len(mentions) > MENTIONS_MAX:
            raise ReviewInputError("too_many_mentions", f"At most {MENTIONS_MAX} mentions")
        kept: list[str] = []
        for user_id in dict.fromkeys(mentions):
            if user_id == actor.id or not _real_user(user_id):
                continue
            acl = await self._acls.load_for(Actor.user(user_id), project_id)
            if acl is not None and can(Actor.user(user_id), Action.SOURCES_READ, acl):
                kept.append(user_id)
        return tuple(kept)

    async def _notify(
        self,
        recipients: set[str],
        actor: Actor,
        kind: NotificationKind,
        payload: NotificationPayload,
        dedupe: str,
    ) -> None:
        for user_id in sorted(recipients):
            if user_id != actor.id and _real_user(user_id):
                await self._notifier.notify(user_id, kind, payload, dedupe_key=dedupe)

    async def _payload(
        self, project_id: UUID, thread: ReviewThread, actor: Actor, body: str, outcome: str | None = None
    ) -> NotificationPayload:
        card = await self._cards.card(project_id)
        return NotificationPayload(
            project_id=str(project_id),
            project_name=card.name if card else None,
            actor_name=_author_name(actor),
            ref_id=thread.id,
            path=thread.path,
            excerpt=excerpt_of(body),
            outcome=outcome,
        )

    async def _editors(self, project_id: UUID) -> set[str]:
        """Владельцы и редакторы-люди: те, кому адресован новый тред."""
        ids = set(await self._cards.managers(project_id))
        found = await self._directory.page_access(
            project_id,
            AccessQuery(kinds=("user",), window=Window(limit=_EDITORS_NOTIFIED_MAX)),
        )
        if found is not None:
            ids |= {row.subject_id for row in found.items if row.role.value in ("editor", "owner")}
        return ids


class ListReviewThreadsUC(_ReviewBase):
    async def execute(
        self, project_id: UUID, *, path: str | None = None, status: ThreadStatus | None = None
    ) -> list[ReviewThread]:
        if path is None:
            await self._access.require(project_id, Action.SOURCES_READ)
        else:
            await self._access.require(project_id, Action.FILES_READ, path)
        return await self._reviews.list_threads(project_id, path=path, status=status)


class CreateReviewThreadUC(_ReviewBase):
    async def execute(self, project_id: UUID, new: NewThread) -> ReviewThread:
        path = new.path.strip().lstrip("/")
        if not path or len(path) > PATH_MAX:
            raise ReviewInputError("bad_path", "Invalid file path")
        await self._access.require(project_id, Action.COMMENT)
        await self._access.require(project_id, Action.FILES_READ, path)
        actor = require_actor()
        body = _clean_body(new.body)
        anchor = _clean_anchor(new.anchor)
        snapshot = await self._store.read(project_id, path)
        if snapshot is None:
            raise ReviewNotFoundError("File not found")
        if anchor.quote not in snapshot.text:
            # Фрагмент успели изменить, пока писали комментарий: привязать его уже не к чему.
            raise ReviewConflictError("anchor_stale", "The fragment changed, select it again")
        if await self._reviews.count_threads(project_id, path) >= THREADS_PER_FILE_MAX:
            raise ReviewConflictError("too_many_threads", "Too many comment threads in this file")
        mentions = await self._valid_mentions(project_id, new.mentions, actor)
        now = self._clock()
        thread_id = _thread_id()
        comment = ReviewComment(
            id=_comment_id(),
            thread_id=thread_id,
            author_id=actor.id,
            author_name=_author_name(actor),
            body=body,
            mentions=mentions,
            created_at=now,
        )
        thread = ReviewThread(
            id=thread_id,
            project_id=str(project_id),
            path=path,
            anchor=anchor,
            status=ThreadStatus.open,
            created_by=actor.id,
            created_by_name=_author_name(actor),
            created_at=now,
            updated_at=now,
            comments=(comment,),
        )
        async with self._uow.begin():
            await self._reviews.add_thread(thread)
            payload = await self._payload(project_id, thread, actor, body)
            await self._notify(set(mentions), actor, NotificationKind.review_mention, payload, f"rvm:{comment.id}")
            await self._notify(
                await self._editors(project_id) - set(mentions),
                actor,
                NotificationKind.review_thread,
                payload,
                f"rvt:{thread.id}",
            )
        await self._events.review_changed(project_id, path)
        return thread


class ReplyReviewThreadUC(_ReviewBase):
    async def execute(
        self, project_id: UUID, thread_id: str, body: str, mentions: tuple[str, ...] = ()
    ) -> ReviewThread:
        thread = await self._thread(project_id, thread_id)
        await self._access.require(project_id, Action.COMMENT)
        await self._access.require(project_id, Action.FILES_READ, thread.path)
        actor = require_actor()
        text = _clean_body(body)
        valid = await self._valid_mentions(project_id, mentions, actor)
        comment = ReviewComment(
            id=_comment_id(),
            thread_id=thread.id,
            author_id=actor.id,
            author_name=_author_name(actor),
            body=text,
            mentions=valid,
            created_at=self._clock(),
        )
        async with self._uow.begin():
            if not await self._reviews.add_comment(project_id, comment):
                raise ReviewNotFoundError("Thread not found")
            payload = await self._payload(project_id, thread, actor, text)
            await self._notify(set(valid), actor, NotificationKind.review_mention, payload, f"rvm:{comment.id}")
            audience = set(thread.participants)
            if thread.created_by:
                audience.add(thread.created_by)
            await self._notify(audience - set(valid), actor, NotificationKind.review_reply, payload, f"rvr:{thread.id}")
        await self._events.review_changed(project_id, thread.path)
        return await self._thread(project_id, thread_id)


class EditReviewCommentUC(_ReviewBase):
    async def execute(self, project_id: UUID, comment_id: str, body: str) -> ReviewThread:
        found = await self._reviews.find_comment(project_id, comment_id)
        if found is None:
            raise ReviewNotFoundError("Comment not found")
        thread, comment = found
        await self._access.require(project_id, Action.COMMENT)
        actor = require_actor()
        if comment.author_id is None or comment.author_id != actor.id:
            raise ProjectForbiddenError("Only the author can edit a comment")
        text = _clean_body(body)
        if text != comment.body:
            await self._reviews.edit_comment(project_id, comment_id, text, self._clock())
            await self._events.review_changed(project_id, thread.path)
        return await self._thread(project_id, thread.id)


class DeleteReviewCommentUC(_ReviewBase):
    async def execute(self, project_id: UUID, comment_id: str) -> None:
        found = await self._reviews.find_comment(project_id, comment_id)
        if found is None:
            raise ReviewNotFoundError("Comment not found")
        thread, comment = found
        await self._access.require(project_id, Action.COMMENT)
        actor = require_actor()
        manager = await self._may(project_id, Action.PROJECT_SETTINGS)
        own = comment.author_id is not None and comment.author_id == actor.id
        if not (own or manager):
            raise ProjectForbiddenError("Only the author or the owner can delete a comment")
        if thread.comments[0].id == comment.id:
            # Корневой комментарий держит тред: он уходит вместе с ним. Чужие ответы автор не уносит.
            if not manager and any(c.author_id != actor.id for c in thread.comments[1:]):
                raise ReviewConflictError("thread_has_replies", "The thread has replies from other people")
            await self._reviews.delete_thread(project_id, thread.id)
        else:
            await self._reviews.delete_comment(project_id, comment_id)
        await self._events.review_changed(project_id, thread.path)


class SetReviewThreadStatusUC(_ReviewBase):
    async def execute(self, project_id: UUID, thread_id: str, status: ThreadStatus) -> ReviewThread:
        thread = await self._thread(project_id, thread_id)
        await self._access.require(project_id, Action.COMMENT)
        actor = require_actor()
        own = thread.created_by is not None and thread.created_by == actor.id
        if not own and not await self._may(project_id, Action.FILES_WRITE, thread.path):
            raise ProjectForbiddenError("Only the thread author or an editor can change its status")
        if thread.status is status:
            return thread
        now = self._clock()
        async with self._uow.begin():
            await self._reviews.set_status(
                project_id, thread.id, status, by_id=actor.id, by_name=_author_name(actor), at=now
            )
            if thread.created_by and thread.created_by != actor.id:
                note = thread.comments[0].body if thread.comments else ""
                payload = await self._payload(
                    project_id, thread, actor, note, "resolved" if status is ThreadStatus.resolved else "reopened"
                )
                await self._notify(
                    {thread.created_by}, actor, NotificationKind.review_resolved, payload, f"rvs:{thread.id}"
                )
        await self._events.review_changed(project_id, thread.path)
        return await self._thread(project_id, thread.id)


class ListMentionCandidatesUC(_ReviewBase):
    async def execute(self, project_id: UUID, query: str, limit: int = 8) -> list[MentionCandidate]:
        """Люди проекта для автодополнения `@`: прямые участники и владелец. Группы не раскрываются."""
        await self._access.require(project_id, Action.COMMENT)
        actor = require_actor()
        found = await self._directory.page_access(
            project_id, AccessQuery(q=query.strip() or None, kinds=("user",), window=Window(limit=limit + 1))
        )
        if found is None:
            return []
        rows = [r for r in found.items if _real_user(r.subject_id) and r.subject_id != actor.id]
        return [MentionCandidate(user_id=r.subject_id, name=r.name, detail=r.detail) for r in rows[:limit]]
