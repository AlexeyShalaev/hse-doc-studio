from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from uuid import UUID

import structlog

from hse_doc_studio.core.entities import (
    AgentRunRecord,
    ChatMessage,
    ChatSession,
    ChatSummaryBlock,
)
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

logger = structlog.get_logger()

_HSE_STUDIO = ".hse-studio"


class JsonChatRepository:
    """Per-project chat persistence under <folder>/.hse-studio/chats/<session_id>/.

    Layout per session::

        session.json     — manifest (atomic temp+os.replace; mutated rarely)
        messages.jsonl   — append-only transcript, one JSON object per line
        summaries.json   — rolling compaction summaries (atomic rewrite)
        runs/<id>.json   — one terminal record per turn (atomic rewrite)

    The transcript is JSONL because it grows unboundedly and tool results can be
    large: appending one line is O(1) and a torn *final* line is trivially
    recovered (dropped on read), unlike a corrupt whole-document JSON array.
    Everything else is small and uses the whole-file atomic-write pattern shared
    with the other JSON repositories.
    """

    def _chats_dir(self, project_folder: Path) -> Path:
        return project_folder / _HSE_STUDIO / "chats"

    def _session_dir(self, project_folder: Path, session_id: UUID) -> Path:
        return self._chats_dir(project_folder) / str(session_id)

    @staticmethod
    def _write_atomic(path: Path, data: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    # ── sessions ─────────────────────────────────────────────────────────────

    def list_sessions(self, project_folder: Path) -> list[ChatSession]:
        chats_dir = self._chats_dir(project_folder)
        if not chats_dir.exists():
            return []
        out: list[ChatSession] = []
        for session_json in chats_dir.glob("*/session.json"):
            try:
                data = json.loads(session_json.read_text(encoding="utf-8"))
                out.append(deserialize_chat_session(data, project_folder))
            except Exception as exc:
                logger.warning("chat session read error", path=str(session_json), exc=str(exc))
        return out

    def get_session(self, project_folder: Path, session_id: UUID) -> ChatSession | None:
        path = self._session_dir(project_folder, session_id) / "session.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return deserialize_chat_session(data, project_folder)
        except Exception as exc:
            logger.warning("chat session read error", path=str(path), exc=str(exc))
            return None

    def save_session(self, session: ChatSession) -> None:
        path = self._session_dir(session.project_folder, session.id) / "session.json"
        self._write_atomic(path, serialize_chat_session(session))

    def delete_session(self, project_folder: Path, session_id: UUID) -> bool:
        session_dir = self._session_dir(project_folder, session_id)
        if not session_dir.exists():
            return False
        shutil.rmtree(session_dir, ignore_errors=True)
        return True

    # ── messages (append-only transcript) ────────────────────────────────────

    def append_message(self, project_folder: Path, message: ChatMessage) -> int:
        session = self.get_session(project_folder, message.session_id)
        if session is None:
            raise ValueError(f"chat session {message.session_id} not found")
        seq = session.message_count
        stamped = ChatMessage(
            id=message.id,
            session_id=message.session_id,
            run_id=message.run_id,
            seq=seq,
            role=message.role,
            blocks=message.blocks,
            created_at=message.created_at,
            model=message.model,
            provider_id=message.provider_id,
            usage=message.usage,
            approval=message.approval,
            compacted=message.compacted,
        )
        path = self._session_dir(project_folder, message.session_id) / "messages.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(serialize_chat_message(stamped), ensure_ascii=False)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        session.message_count = seq + 1
        session.updated_at = message.created_at
        self.save_session(session)
        return seq

    def list_messages(self, project_folder: Path, session_id: UUID) -> list[ChatMessage]:
        path = self._session_dir(project_folder, session_id) / "messages.jsonl"
        if not path.exists():
            return []
        out: list[ChatMessage] = []
        lines = path.read_text(encoding="utf-8").splitlines()
        for idx, raw in enumerate(lines):
            stripped = raw.strip()
            if not stripped:
                continue
            try:
                out.append(deserialize_chat_message(json.loads(stripped)))
            except Exception as exc:
                # A torn final line (crash mid-append) is expected; drop it. A
                # broken line elsewhere is logged and skipped, never fatal.
                if idx == len(lines) - 1:
                    logger.warning("chat transcript: dropping torn final line", session_id=str(session_id))
                else:
                    logger.warning("chat transcript: skipping bad line", session_id=str(session_id), exc=str(exc))
        return out

    def update_message(self, project_folder: Path, message: ChatMessage) -> None:
        # Rare path (compaction flag only): rewrite the whole transcript atomically.
        messages = self.list_messages(project_folder, message.session_id)
        replaced = [message if m.id == message.id else m for m in messages]
        self._rewrite_transcript(project_folder, message.session_id, replaced)

    def mark_compacted(self, project_folder: Path, session_id: UUID, through_seq: int) -> int:
        messages = self.list_messages(project_folder, session_id)
        count = 0
        for message in messages:
            if message.seq <= through_seq and not message.compacted:
                message.compacted = True
                count += 1
        if count:
            self._rewrite_transcript(project_folder, session_id, messages)
        return count

    def _rewrite_transcript(self, project_folder: Path, session_id: UUID, messages: list[ChatMessage]) -> None:
        path = self._session_dir(project_folder, session_id) / "messages.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".jsonl.tmp")
        tmp.write_text(
            "".join(json.dumps(serialize_chat_message(m), ensure_ascii=False) + "\n" for m in messages),
            encoding="utf-8",
        )
        os.replace(tmp, path)

    # ── rolling compaction summaries ─────────────────────────────────────────

    def list_summaries(self, project_folder: Path, session_id: UUID) -> list[ChatSummaryBlock]:
        path = self._session_dir(project_folder, session_id) / "summaries.json"
        if not path.exists():
            return []
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("chat summaries read error", path=str(path), exc=str(exc))
            return []
        items = raw if isinstance(raw, list) else []
        return [deserialize_chat_summary(item) for item in items]

    def append_summary(self, project_folder: Path, summary: ChatSummaryBlock) -> None:
        existing = self.list_summaries(project_folder, summary.session_id)
        existing.append(summary)
        path = self._session_dir(project_folder, summary.session_id) / "summaries.json"
        self._write_atomic(path, [serialize_chat_summary(s) for s in existing])

    # ── background-turn run records ──────────────────────────────────────────

    def _runs_dir(self, project_folder: Path, session_id: UUID) -> Path:
        return self._session_dir(project_folder, session_id) / "runs"

    def get_run(self, project_folder: Path, run_id: UUID) -> AgentRunRecord | None:
        for run_json in self._chats_dir(project_folder).glob(f"*/runs/{run_id}.json"):
            try:
                data = json.loads(run_json.read_text(encoding="utf-8"))
                return deserialize_agent_run(data, project_folder)
            except Exception as exc:
                logger.warning("agent run read error", path=str(run_json), exc=str(exc))
                return None
        return None

    def list_runs(self, project_folder: Path, session_id: UUID) -> list[AgentRunRecord]:
        runs_dir = self._runs_dir(project_folder, session_id)
        if not runs_dir.exists():
            return []
        out: list[AgentRunRecord] = []
        for run_json in runs_dir.glob("*.json"):
            try:
                data = json.loads(run_json.read_text(encoding="utf-8"))
                out.append(deserialize_agent_run(data, project_folder))
            except Exception as exc:
                logger.warning("agent run read error", path=str(run_json), exc=str(exc))
        out.sort(key=lambda r: r.created_at)
        return out

    def save_run(self, record: AgentRunRecord) -> None:
        path = self._runs_dir(record.project_folder, record.session_id) / f"{record.id}.json"
        self._write_atomic(path, serialize_agent_run(record))

    def list_all_run_ids(self, project_folder: Path) -> list[UUID]:
        chats_dir = self._chats_dir(project_folder)
        if not chats_dir.exists():
            return []
        ids: list[UUID] = []
        for run_json in chats_dir.glob("*/runs/*.json"):
            try:
                ids.append(UUID(run_json.stem))
            except ValueError:
                continue
        return ids
