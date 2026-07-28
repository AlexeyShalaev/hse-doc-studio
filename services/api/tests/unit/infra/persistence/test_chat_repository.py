from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from hse_doc_studio.core.entities import (
    AgentRunRecord,
    ChatContentBlock,
    ChatMessage,
    ChatSession,
    ChatSummaryBlock,
)
from hse_doc_studio.core.enums import (
    AgentRunStatus,
    ChatContentKind,
    ChatMessageRole,
)
from hse_doc_studio.infra.persistence.chat import JsonChatRepository


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _session(folder: Path) -> ChatSession:
    now = _now()
    return ChatSession(id=uuid4(), project_folder=folder, title="t", doc_id=None, created_at=now, updated_at=now)


def _msg(session_id: object, role: ChatMessageRole, text: str) -> ChatMessage:
    return ChatMessage(
        id=uuid4(),
        session_id=session_id,  # type: ignore[arg-type]
        run_id=None,
        seq=-1,
        role=role,
        blocks=[ChatContentBlock(kind=ChatContentKind.text, text=text)],
        created_at=_now(),
    )


@pytest.mark.unit
def test__chat_repo__session_roundtrip_and_list(tmp_path: Path) -> None:
    repo = JsonChatRepository()
    session = _session(tmp_path)

    repo.save_session(session)

    loaded = repo.get_session(tmp_path, session.id)
    assert loaded is not None
    assert loaded.title == "t"
    assert loaded.project_folder == tmp_path
    assert [s.id for s in repo.list_sessions(tmp_path)] == [session.id]


@pytest.mark.unit
def test__chat_repo__append_assigns_seq_and_bumps_count(tmp_path: Path) -> None:
    repo = JsonChatRepository()
    session = _session(tmp_path)
    repo.save_session(session)

    seq0 = repo.append_message(tmp_path, _msg(session.id, ChatMessageRole.user, "hi"))
    seq1 = repo.append_message(tmp_path, _msg(session.id, ChatMessageRole.assistant, "hello"))

    assert seq0 == 0
    assert seq1 == 1
    messages = repo.list_messages(tmp_path, session.id)
    assert [m.seq for m in messages] == [0, 1]
    assert messages[0].blocks[0].text == "hi"
    reloaded = repo.get_session(tmp_path, session.id)
    assert reloaded is not None
    assert reloaded.message_count == 2


@pytest.mark.unit
def test__chat_repo__drops_torn_final_line(tmp_path: Path) -> None:
    repo = JsonChatRepository()
    session = _session(tmp_path)
    repo.save_session(session)
    repo.append_message(tmp_path, _msg(session.id, ChatMessageRole.user, "ok"))

    # Simulate a crash mid-append: a truncated final JSONL line.
    path = tmp_path / ".hse-studio" / "chats" / str(session.id) / "messages.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write('{"id": "broke')

    messages = repo.list_messages(tmp_path, session.id)
    assert len(messages) == 1  # torn line dropped, good line kept


@pytest.mark.unit
def test__chat_repo__run_roundtrip(tmp_path: Path) -> None:
    repo = JsonChatRepository()
    session = _session(tmp_path)
    repo.save_session(session)
    now = _now()
    run = AgentRunRecord(
        id=uuid4(),
        session_id=session.id,
        project_folder=tmp_path,
        status=AgentRunStatus.running,
        created_at=now,
        started_at=now,
        finished_at=None,
        trigger_seq=0,
    )

    repo.save_run(run)

    fetched = repo.get_run(tmp_path, run.id)
    assert fetched is not None
    assert fetched.status == AgentRunStatus.running
    assert repo.list_all_run_ids(tmp_path) == [run.id]


@pytest.mark.unit
def test__chat_repo__summary_roundtrip(tmp_path: Path) -> None:
    repo = JsonChatRepository()
    session = _session(tmp_path)
    repo.save_session(session)
    summary = ChatSummaryBlock(
        id=uuid4(),
        session_id=session.id,
        covers_from_seq=0,
        covers_to_seq=4,
        created_at=_now(),
        text="summary",
    )

    repo.append_summary(tmp_path, summary)

    assert [s.text for s in repo.list_summaries(tmp_path, session.id)] == ["summary"]


@pytest.mark.unit
def test__chat_repo__delete_session(tmp_path: Path) -> None:
    repo = JsonChatRepository()
    session = _session(tmp_path)
    repo.save_session(session)

    assert repo.delete_session(tmp_path, session.id) is True
    assert repo.get_session(tmp_path, session.id) is None
    assert repo.delete_session(tmp_path, session.id) is False
