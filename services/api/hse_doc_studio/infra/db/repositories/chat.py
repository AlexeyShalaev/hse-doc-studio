"""Личные чаты ИИ-агента в Postgres: чат видит и меняет только его автор, проект берётся из папки на томе."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from hse_doc_studio.core.access.context import ActorRequired, current_actor, require_actor
from hse_doc_studio.core.access.entities import ActorKind
from hse_doc_studio.core.entities import AgentRunRecord, ChatMessage, ChatSession, ChatSummaryBlock
from hse_doc_studio.core.projects.volume import IProjectVolume
from hse_doc_studio.infra.db.orm.chat import AgentRunRow, ChatMessageRow, ChatSessionRow, ChatSummaryRow
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.persistence.serializers import (
    deserialize_agent_run,
    deserialize_chat_message,
    deserialize_chat_session,
    deserialize_chat_summary,
    serialize_agent_run,
    serialize_chat_message,
    serialize_chat_session,
    serialize_chat_summary,
)

_SESSION_FIELDS = (
    "title",
    "doc_id",
    "updated_at",
    "archived",
    "default_provider_id",
    "default_model",
    "persona",
    "persona_instructions",
    "last_run_id",
    "compacted_through_seq",
    "summary_count",
    "estimated_context_tokens",
)


class PostgresChatRepository:
    """IChatRepository сервера.

    Чат принадлежит пользователю, который его создал, и виден только ему: все запросы по сессии, реплике или
    сводке отбираются по владельцу, чужой чат неотличим от несуществующего. Номер реплики выдаёт один
    ``UPDATE ... RETURNING`` счётчика сессии, поэтому параллельные записи сериализуются на строке и дыр не дают.
    Чаты без проекта (системный агент) хранятся под папкой ``system_folder`` и от чатов проектов отделены флагом.
    Записи ходов читает и закрывает ещё и восстановление при старте: оно идёт без актора и видит все ходы.
    """

    def __init__(self, sessions: SessionProvider, volume: IProjectVolume, system_folder: Path) -> None:
        self._sessions = sessions
        self._volume = volume
        self._system_folder = system_folder

    # ── sessions ─────────────────────────────────────────────────────────────

    async def list_sessions(self, project_folder: Path) -> list[ChatSession]:
        stmt = (
            select(ChatSessionRow)
            .where(self._in_scope(project_folder), ChatSessionRow.owner_id == _owner_id())
            .order_by(ChatSessionRow.created_at, ChatSessionRow.id)
        )
        async with self._sessions.use() as session:
            rows = (await session.execute(stmt)).scalars().all()
        return [_session_from_row(row, project_folder) for row in rows]

    async def get_session(self, project_folder: Path, session_id: UUID) -> ChatSession | None:
        async with self._sessions.use() as session:
            row = (
                await session.execute(
                    select(ChatSessionRow).where(
                        ChatSessionRow.id == session_id,
                        self._in_scope(project_folder),
                        ChatSessionRow.owner_id == _owner_id(),
                    )
                )
            ).scalar_one_or_none()
        return None if row is None else _session_from_row(row, project_folder)

    async def save_session(self, session: ChatSession) -> None:
        """Счётчик реплик принадлежит append_message: сохранение сессии его не перезаписывает."""
        system = self._is_system(session.project_folder)
        project_id = session.project_id if system else self._volume.id_of(session.project_folder)
        owner_id = _owner_id()
        data = serialize_chat_session(session)
        values = {
            "title": session.title,
            "doc_id": session.doc_id,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "archived": session.archived,
            "default_provider_id": session.default_provider_id,
            "default_model": session.default_model,
            "persona": session.persona,
            "persona_instructions": session.persona_instructions,
            "last_run_id": session.last_run_id,
            "compacted_through_seq": data["compacted_through_seq"],
            "summary_count": data["summary_count"],
            "estimated_context_tokens": data["estimated_context_tokens"],
        }
        async with self._sessions.use() as db:
            stmt = pg_insert(ChatSessionRow).values(
                id=session.id,
                project_id=project_id,
                is_system=system,
                owner_id=owner_id,
                message_count=session.message_count,
                **values,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[ChatSessionRow.id],
                set_={name: stmt.excluded[name] for name in _SESSION_FIELDS},
                where=(ChatSessionRow.owner_id == owner_id) & self._in_scope(session.project_folder),
            ).returning(ChatSessionRow.id)
            if (await db.execute(stmt)).first() is None:
                raise ValueError(f"chat session {session.id} not found")

    async def delete_session(self, project_folder: Path, session_id: UUID) -> bool:
        async with self._sessions.use() as session:
            deleted = (
                await session.execute(
                    delete(ChatSessionRow)
                    .where(
                        ChatSessionRow.id == session_id,
                        self._in_scope(project_folder),
                        ChatSessionRow.owner_id == _owner_id(),
                    )
                    .returning(ChatSessionRow.id)
                )
            ).first()
        return deleted is not None

    # ── messages ─────────────────────────────────────────────────────────────

    async def append_message(self, project_folder: Path, message: ChatMessage) -> int:
        data = serialize_chat_message(message)
        async with self._sessions.use() as session:
            # Блокировка строки сессии держится до конца транзакции: следующий append ждёт и видит новый счётчик.
            counter = (
                await session.execute(
                    update(ChatSessionRow)
                    .where(
                        ChatSessionRow.id == message.session_id,
                        self._in_scope(project_folder),
                        ChatSessionRow.owner_id == _owner_id(),
                    )
                    .values(message_count=ChatSessionRow.message_count + 1, updated_at=message.created_at)
                    .returning(ChatSessionRow.message_count)
                )
            ).scalar_one_or_none()
            if counter is None:
                raise ValueError(f"chat session {message.session_id} not found")
            seq = counter - 1
            await session.execute(
                pg_insert(ChatMessageRow).values(
                    id=message.id,
                    session_id=message.session_id,
                    seq=seq,
                    run_id=message.run_id,
                    role=data["role"],
                    blocks=data["blocks"],
                    created_at=message.created_at,
                    model=message.model,
                    provider_id=message.provider_id,
                    usage=data["usage"],
                    approval=data["approval"],
                    compacted=message.compacted,
                )
            )
        return seq

    async def list_messages(self, project_folder: Path, session_id: UUID) -> list[ChatMessage]:
        stmt = (
            select(ChatMessageRow)
            .where(
                ChatMessageRow.session_id == session_id,
                ChatMessageRow.session_id.in_(self._own_sessions(project_folder)),
            )
            .order_by(ChatMessageRow.seq)
        )
        async with self._sessions.use() as session:
            rows = (await session.execute(stmt)).scalars().all()
        return [_message_from_row(row) for row in rows]

    async def update_message(self, project_folder: Path, message: ChatMessage) -> None:
        data = serialize_chat_message(message)
        async with self._sessions.use() as session:
            await session.execute(
                update(ChatMessageRow)
                .where(
                    ChatMessageRow.id == message.id,
                    ChatMessageRow.session_id == message.session_id,
                    ChatMessageRow.session_id.in_(self._own_sessions(project_folder)),
                )
                .values(
                    run_id=message.run_id,
                    role=data["role"],
                    blocks=data["blocks"],
                    model=message.model,
                    provider_id=message.provider_id,
                    usage=data["usage"],
                    approval=data["approval"],
                    compacted=message.compacted,
                )
            )

    async def mark_compacted(self, project_folder: Path, session_id: UUID, through_seq: int) -> int:
        async with self._sessions.use() as session:
            marked = (
                await session.execute(
                    update(ChatMessageRow)
                    .where(
                        ChatMessageRow.session_id == session_id,
                        ChatMessageRow.session_id.in_(self._own_sessions(project_folder)),
                        ChatMessageRow.seq <= through_seq,
                        ChatMessageRow.compacted.is_(False),
                    )
                    .values(compacted=True)
                    .returning(ChatMessageRow.id)
                )
            ).all()
        return len(marked)

    # ── rolling compaction summaries ─────────────────────────────────────────

    async def list_summaries(self, project_folder: Path, session_id: UUID) -> list[ChatSummaryBlock]:
        stmt = (
            select(ChatSummaryRow)
            .where(
                ChatSummaryRow.session_id == session_id,
                ChatSummaryRow.session_id.in_(self._own_sessions(project_folder)),
            )
            .order_by(ChatSummaryRow.created_at, ChatSummaryRow.covers_from_seq)
        )
        async with self._sessions.use() as session:
            rows = (await session.execute(stmt)).scalars().all()
        return [_summary_from_row(row) for row in rows]

    async def append_summary(self, project_folder: Path, summary: ChatSummaryBlock) -> None:
        data = serialize_chat_summary(summary)
        async with self._sessions.use() as session:
            if (
                await session.execute(
                    select(ChatSessionRow.id)
                    .where(ChatSessionRow.id == summary.session_id)
                    .where(ChatSessionRow.id.in_(self._own_sessions(project_folder)))
                )
            ).first() is None:
                raise ValueError(f"chat session {summary.session_id} not found")
            await session.execute(
                pg_insert(ChatSummaryRow).values(
                    id=summary.id,
                    session_id=summary.session_id,
                    covers_from_seq=summary.covers_from_seq,
                    covers_to_seq=summary.covers_to_seq,
                    created_at=summary.created_at,
                    text=data["text"],
                    model=summary.model,
                    token_estimate=summary.token_estimate,
                )
            )

    # ── background-turn run records ──────────────────────────────────────────

    async def get_run(self, project_folder: Path, run_id: UUID) -> AgentRunRecord | None:
        stmt = select(AgentRunRow).where(
            AgentRunRow.id == run_id, AgentRunRow.session_id.in_(self._run_sessions(project_folder))
        )
        async with self._sessions.use() as session:
            row = (await session.execute(stmt)).scalar_one_or_none()
        return None if row is None else _run_from_row(row, project_folder)

    async def list_runs(self, project_folder: Path, session_id: UUID) -> list[AgentRunRecord]:
        stmt = (
            select(AgentRunRow)
            .where(AgentRunRow.session_id == session_id, AgentRunRow.session_id.in_(self._run_sessions(project_folder)))
            .order_by(AgentRunRow.created_at, AgentRunRow.id)
        )
        async with self._sessions.use() as session:
            rows = (await session.execute(stmt)).scalars().all()
        return [_run_from_row(row, project_folder) for row in rows]

    async def save_run(self, record: AgentRunRecord) -> None:
        data = serialize_agent_run(record)
        values = {
            "status": data["status"],
            "created_at": record.created_at,
            "started_at": record.started_at,
            "finished_at": record.finished_at,
            "trigger_seq": record.trigger_seq,
            "first_emitted_seq": record.first_emitted_seq,
            "last_emitted_seq": record.last_emitted_seq,
            "model": record.model,
            "provider_id": record.provider_id,
            "iterations": record.iterations,
            "usage": data["usage"],
            "error": record.error,
            "diagnostics": data["diagnostics"],
        }
        async with self._sessions.use() as session:
            if (
                await session.execute(
                    select(ChatSessionRow.id).where(
                        ChatSessionRow.id == record.session_id,
                        ChatSessionRow.id.in_(self._run_sessions(record.project_folder)),
                    )
                )
            ).first() is None:
                raise ValueError(f"chat session {record.session_id} not found")
            stmt = pg_insert(AgentRunRow).values(id=record.id, session_id=record.session_id, **values)
            await session.execute(stmt.on_conflict_do_update(index_elements=[AgentRunRow.id], set_=values))

    async def list_all_run_ids(self, project_folder: Path) -> list[UUID]:
        stmt = select(AgentRunRow.id).where(AgentRunRow.session_id.in_(self._run_sessions(project_folder)))
        async with self._sessions.use() as session:
            return list((await session.execute(stmt)).scalars())

    # ── отбор по владельцу ───────────────────────────────────────────────────

    def _is_system(self, folder: Path) -> bool:
        return folder == self._system_folder

    def _in_scope(self, folder: Path) -> ColumnElement[bool]:
        """Чаты одной папки: системные по флагу, чаты проекта по id из папки на томе."""
        if self._is_system(folder):
            return ChatSessionRow.is_system.is_(True)
        return ChatSessionRow.is_system.is_(False) & (ChatSessionRow.project_id == self._volume.id_of(folder))

    def _own_sessions(self, project_folder: Path) -> Any:
        return select(ChatSessionRow.id).where(self._in_scope(project_folder), ChatSessionRow.owner_id == _owner_id())

    def _run_sessions(self, project_folder: Path) -> Any:
        """Ходы пользователя ограничены его чатами; восстановление при старте идёт без актора и видит все."""
        conditions: list[ColumnElement[bool]] = [self._in_scope(project_folder)]
        if current_actor() is not None:
            conditions.append(ChatSessionRow.owner_id == _owner_id())
        return select(ChatSessionRow.id).where(*conditions)


def _owner_id() -> str:
    actor = require_actor()
    if actor.kind is not ActorKind.user or actor.id is None:
        raise ActorRequired("чаты доступны только пользователю")
    return actor.id


def _session_from_row(row: ChatSessionRow, project_folder: Path) -> ChatSession:
    return deserialize_chat_session(
        {
            "id": str(row.id),
            "title": row.title,
            "doc_id": row.doc_id,
            "project_id": str(row.project_id) if row.project_id else None,
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
            "archived": row.archived,
            "default_provider_id": str(row.default_provider_id) if row.default_provider_id else None,
            "default_model": row.default_model,
            "persona": row.persona,
            "persona_instructions": row.persona_instructions,
            "message_count": row.message_count,
            "last_run_id": str(row.last_run_id) if row.last_run_id else None,
            "compacted_through_seq": row.compacted_through_seq,
            "summary_count": row.summary_count,
            "estimated_context_tokens": row.estimated_context_tokens,
        },
        project_folder,
    )


def _message_from_row(row: ChatMessageRow) -> ChatMessage:
    return deserialize_chat_message(
        {
            "id": str(row.id),
            "session_id": str(row.session_id),
            "run_id": str(row.run_id) if row.run_id else None,
            "seq": row.seq,
            "role": row.role,
            "blocks": row.blocks,
            "created_at": row.created_at.isoformat(),
            "model": row.model,
            "provider_id": str(row.provider_id) if row.provider_id else None,
            "usage": row.usage,
            "approval": row.approval,
            "compacted": row.compacted,
        }
    )


def _summary_from_row(row: ChatSummaryRow) -> ChatSummaryBlock:
    return deserialize_chat_summary(
        {
            "id": str(row.id),
            "session_id": str(row.session_id),
            "covers_from_seq": row.covers_from_seq,
            "covers_to_seq": row.covers_to_seq,
            "created_at": row.created_at.isoformat(),
            "text": row.text,
            "model": row.model,
            "token_estimate": row.token_estimate,
        }
    )


def _run_from_row(row: AgentRunRow, project_folder: Path) -> AgentRunRecord:
    return deserialize_agent_run(
        {
            "id": str(row.id),
            "session_id": str(row.session_id),
            "status": row.status,
            "created_at": row.created_at.isoformat(),
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "finished_at": row.finished_at.isoformat() if row.finished_at else None,
            "trigger_seq": row.trigger_seq,
            "first_emitted_seq": row.first_emitted_seq,
            "last_emitted_seq": row.last_emitted_seq,
            "model": row.model,
            "provider_id": str(row.provider_id) if row.provider_id else None,
            "iterations": row.iterations,
            "usage": row.usage,
            "error": row.error,
            "diagnostics": row.diagnostics,
        },
        project_folder,
    )
