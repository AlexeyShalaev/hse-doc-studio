from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from hse_doc_studio.core.entities import ChatContentBlock, ChatMessage
from hse_doc_studio.core.enums import ChatContentKind, ChatMessageRole
from hse_doc_studio.core.services import ChatContextService


def _msg(seq: int, role: ChatMessageRole, text: str) -> ChatMessage:
    return ChatMessage(
        id=uuid4(),
        session_id=uuid4(),
        run_id=None,
        seq=seq,
        role=role,
        blocks=[ChatContentBlock(kind=ChatContentKind.text, text=text)],
        created_at=datetime.now(timezone.utc),
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("messages", "expected"),
    [
        pytest.param([_msg(i, ChatMessageRole.user, "x" * 4000) for i in range(10)], True, id="over_budget"),
        pytest.param([_msg(0, ChatMessageRole.user, "hi")], False, id="under_budget"),
    ],
)
def test__needs_compaction__token_budget__matches_expected(messages: list[ChatMessage], expected: bool) -> None:
    service = ChatContextService()

    result = service.needs_compaction(system="", messages=messages, summaries=[], token_budget=1000, trigger_ratio=0.75)

    assert result is expected


@pytest.mark.unit
def test__plan_cutoff__keeps_recent_tail() -> None:
    service = ChatContextService()
    messages = [_msg(i, ChatMessageRole.user, "x" * 400) for i in range(10)]  # ~100 tok each

    cutoff = service.plan_cutoff(messages, keep_recent_tokens=250, keep_recent_messages_min=2)

    assert cutoff is not None
    # keeping ~3 recent messages (>=250 tok), so cutoff is around seq 6
    assert 0 <= cutoff <= 7


@pytest.mark.unit
def test__plan_cutoff__none_when_short() -> None:
    service = ChatContextService()
    messages = [_msg(0, ChatMessageRole.user, "a"), _msg(1, ChatMessageRole.assistant, "b")]

    cutoff = service.plan_cutoff(messages, keep_recent_tokens=100, keep_recent_messages_min=6)

    assert cutoff is None


@pytest.mark.unit
def test__plan_cutoff__never_starts_kept_region_with_tool_result() -> None:
    service = ChatContextService()
    # assistant(tool_call) then tool(result) at the boundary; cutoff must not split them
    messages = [
        _msg(0, ChatMessageRole.user, "x" * 4000),
        _msg(1, ChatMessageRole.assistant, "x" * 4000),
        _msg(2, ChatMessageRole.tool, "x" * 40),
        _msg(3, ChatMessageRole.assistant, "x" * 40),
    ]

    cutoff = service.plan_cutoff(messages, keep_recent_tokens=50, keep_recent_messages_min=1)

    # the kept region must not begin at the tool message (seq 2); cutoff <= 1
    assert cutoff is None or cutoff <= 1
