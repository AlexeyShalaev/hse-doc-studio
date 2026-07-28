from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from uuid import uuid4

from hse_doc_studio.api.config import AgentConfig, settings
from hse_doc_studio.core.agent.entities import (
    AgentToolContext,
    NormalizedTurn,
    TokenUsage,
    ToolCall,
    ToolResult,
    ToolSpec,
)
from hse_doc_studio.core.agent.tools import ToolDefinition
from hse_doc_studio.core.entities import AIProvider, ChatContentBlock, ChatMessage, ChatSession
from hse_doc_studio.core.enums import (
    AgentEventType,
    AgentRunStatus,
    AIProviderType,
    ChatContentKind,
    ChatMessageRole,
    StopReason,
    ToolKind,
)
from hse_doc_studio.core.services import ChatContextService
from hse_doc_studio.infra.ai.agent.approval import ConfigApprovalGate
from hse_doc_studio.infra.ai.agent.run_bus import AgentRunBus
from hse_doc_studio.infra.persistence.chat import JsonChatRepository
from hse_doc_studio.use_cases.chat._agent_loop import AgentLoop
from hse_doc_studio.use_cases.chat._registry import ToolRegistry
from tests.unit.use_cases.chat.conftest import _now


def _ai_provider() -> AIProvider:
    return AIProvider(
        id=uuid4(), name="p", type=AIProviderType.openai, api_key="k", base_url="", models=[], created_at=_now()
    )


def _seed_session(repo: JsonChatRepository, folder: Path, text: str = "привет") -> ChatSession:
    session = ChatSession(
        id=uuid4(), project_folder=folder, title="t", doc_id=None, created_at=_now(), updated_at=_now()
    )
    repo.save_session(session)
    repo.append_message(
        folder,
        ChatMessage(
            id=uuid4(),
            session_id=session.id,
            run_id=None,
            seq=-1,
            role=ChatMessageRole.user,
            blocks=[ChatContentBlock(kind=ChatContentKind.text, text=text)],
            created_at=_now(),
        ),
    )
    return session


class _FakeProvider:
    def __init__(self, turns: list[NormalizedTurn]) -> None:
        self._turns = turns
        self._i = 0

    async def run_turn(self, *, sink: Any = None, **_: Any) -> NormalizedTurn:
        turn = self._turns[self._i]
        self._i += 1
        if sink is not None and turn.text:
            sink.on_text_delta(turn.text)
        return turn


class _FakeSummarizer:
    def __init__(self) -> None:
        self.called = False

    async def summarize(self, messages: Any, prior: Any, model: str, provider: AIProvider) -> str:
        self.called = True
        return "КРАТКОЕ СОДЕРЖАНИЕ"


class _EchoTool:
    def definition(self) -> ToolDefinition:
        spec = ToolSpec(
            name="echo",
            description="echo back its msg",
            parameters={"type": "object", "properties": {"msg": {"type": "string"}}},
        )
        return ToolDefinition(spec=spec, kind=ToolKind.read, handler=self, weak_model_safe=True)

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        return ToolResult.ok(f"echoed: {args.get('msg')}")


class _FakeWriteTool:
    def __init__(self) -> None:
        self.calls = 0

    def definition(self) -> ToolDefinition:
        spec = ToolSpec(name="do_write", description="write something", parameters={"type": "object"})
        return ToolDefinition(spec=spec, kind=ToolKind.write, handler=self, weak_model_safe=True)

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        self.calls += 1
        return ToolResult.ok("written")


def _make_loop(
    repo: JsonChatRepository,
    provider: Any,
    registry: ToolRegistry,
    *,
    bus: AgentRunBus | None = None,
    auto_approve_writes: bool = False,
    config: AgentConfig | None = None,
    context_service: ChatContextService | None = None,
    summarizer: Any = None,
) -> AgentLoop:
    return AgentLoop(
        provider=provider,
        ai_provider=_ai_provider(),
        model="m",
        registry=registry,
        approval_gate=ConfigApprovalGate(auto_approve_writes=auto_approve_writes),
        chat_repo=repo,
        bus=bus or AgentRunBus(),
        config=config or settings.agent,
        context_service=context_service,
        summarizer=summarizer,
    )


async def test__run__read_tool_call_then_finish__persists_transcript_and_emits_events(tmp_path: Path) -> None:
    repo = JsonChatRepository()
    session = _seed_session(repo, tmp_path)
    bus = AgentRunBus()
    provider = _FakeProvider(
        [
            NormalizedTurn(
                text="сейчас вызову echo",
                tool_calls=(ToolCall(id="c1", name="echo", arguments={"msg": "hi"}),),
                stop_reason=StopReason.tool_calls,
                usage=TokenUsage(input_tokens=5, output_tokens=3),
            ),
            NormalizedTurn(
                text="готово",
                tool_calls=(),
                stop_reason=StopReason.end_turn,
                usage=TokenUsage(input_tokens=8, output_tokens=2),
            ),
        ]
    )
    loop = _make_loop(repo, provider, ToolRegistry([_EchoTool().definition()]), bus=bus)
    run_id = uuid4()

    result = await loop.run(
        project_id=uuid4(),
        project_folder=tmp_path,
        session_id=session.id,
        run_id=run_id,
        system="sys",
        cancel=asyncio.Event(),
    )

    assert result.status == AgentRunStatus.succeeded
    assert result.iterations == 2
    assert result.usage.total_tokens == 18

    messages = repo.list_messages(tmp_path, session.id)
    assert [m.role.value for m in messages] == ["user", "assistant", "tool", "assistant"]
    assert messages[2].blocks[0].result == "echoed: hi"
    assert messages[3].blocks[0].text == "готово"

    bus.close(run_id)
    kinds = [event.type async for event in bus.subscribe(run_id)]
    assert AgentEventType.token in kinds
    assert AgentEventType.tool_call in kinds
    assert AgentEventType.tool_result in kinds
    assert AgentEventType.message in kinds


async def test__run__unknown_tool_requested__reported_as_tool_error_not_fatal(tmp_path: Path) -> None:
    repo = JsonChatRepository()
    session = _seed_session(repo, tmp_path, "go")
    provider = _FakeProvider(
        [
            NormalizedTurn(
                text="",
                tool_calls=(ToolCall(id="c1", name="does_not_exist", arguments={}),),
                stop_reason=StopReason.tool_calls,
                usage=TokenUsage(),
            ),
            NormalizedTurn(text="ок", tool_calls=(), stop_reason=StopReason.end_turn, usage=TokenUsage()),
        ]
    )
    loop = _make_loop(repo, provider, ToolRegistry([]))

    result = await loop.run(
        project_id=uuid4(),
        project_folder=tmp_path,
        session_id=session.id,
        run_id=uuid4(),
        system="sys",
        cancel=asyncio.Event(),
    )

    assert result.status == AgentRunStatus.succeeded
    tool_msg = repo.list_messages(tmp_path, session.id)[2]
    assert tool_msg.blocks[0].is_error is True
    assert "неизвестный инструмент" in (tool_msg.blocks[0].result or "")


async def test__run__write_tool_call_without_approval__suspends_without_running_tool(tmp_path: Path) -> None:
    repo = JsonChatRepository()
    session = _seed_session(repo, tmp_path, "сделай правку")
    bus = AgentRunBus()
    write_tool = _FakeWriteTool()
    registry = ToolRegistry([write_tool.definition()])
    run_id = uuid4()
    provider = _FakeProvider(
        [
            NormalizedTurn(
                text="сейчас отредактирую",
                tool_calls=(ToolCall(id="w1", name="do_write", arguments={"x": 1}),),
                stop_reason=StopReason.tool_calls,
                usage=TokenUsage(),
            )
        ]
    )

    result = await _make_loop(repo, provider, registry, bus=bus).run(
        project_id=uuid4(),
        project_folder=tmp_path,
        session_id=session.id,
        run_id=run_id,
        system="s",
        cancel=asyncio.Event(),
    )

    assert result.status == AgentRunStatus.awaiting_approval
    assert write_tool.calls == 0
    assert [m.role.value for m in repo.list_messages(tmp_path, session.id)] == ["user", "assistant"]
    bus.close(run_id)
    kinds = [e.type async for e in bus.subscribe(run_id)]
    assert AgentEventType.approval_required in kinds


async def test__run__resumed_with_approved_call_id__runs_pending_write_tool_and_finishes(tmp_path: Path) -> None:
    repo = JsonChatRepository()
    session = _seed_session(repo, tmp_path, "сделай правку")
    bus = AgentRunBus()
    write_tool = _FakeWriteTool()
    registry = ToolRegistry([write_tool.definition()])
    run_id = uuid4()
    call_id = "w1"
    suspend_provider = _FakeProvider(
        [
            NormalizedTurn(
                text="сейчас отредактирую",
                tool_calls=(ToolCall(id=call_id, name="do_write", arguments={"x": 1}),),
                stop_reason=StopReason.tool_calls,
                usage=TokenUsage(),
            )
        ]
    )
    await _make_loop(repo, suspend_provider, registry, bus=bus).run(
        project_id=uuid4(),
        project_folder=tmp_path,
        session_id=session.id,
        run_id=run_id,
        system="s",
        cancel=asyncio.Event(),
    )
    bus.close(run_id)
    bus.discard(run_id)
    resume_provider = _FakeProvider(
        [NormalizedTurn(text="готово", tool_calls=(), stop_reason=StopReason.end_turn, usage=TokenUsage())]
    )

    result = await _make_loop(repo, resume_provider, registry, bus=bus).run(
        project_id=uuid4(),
        project_folder=tmp_path,
        session_id=session.id,
        run_id=run_id,
        system="s",
        cancel=asyncio.Event(),
        approved_call_ids=(call_id,),
    )

    assert result.status == AgentRunStatus.succeeded
    assert write_tool.calls == 1
    messages = repo.list_messages(tmp_path, session.id)
    assert [m.role.value for m in messages] == ["user", "assistant", "tool", "assistant"]
    assert messages[2].blocks[0].result == "written"


async def test__run__auto_approve_writes_enabled__write_tool_runs_immediately(tmp_path: Path) -> None:
    repo = JsonChatRepository()
    session = _seed_session(repo, tmp_path, "сделай правку")
    write_tool = _FakeWriteTool()
    registry = ToolRegistry([write_tool.definition()])
    provider = _FakeProvider(
        [
            NormalizedTurn(
                text="пишу",
                tool_calls=(ToolCall(id="w1", name="do_write", arguments={}),),
                stop_reason=StopReason.tool_calls,
                usage=TokenUsage(),
            ),
            NormalizedTurn(text="готово", tool_calls=(), stop_reason=StopReason.end_turn, usage=TokenUsage()),
        ]
    )
    loop = _make_loop(repo, provider, registry, auto_approve_writes=True)

    result = await loop.run(
        project_id=uuid4(),
        project_folder=tmp_path,
        session_id=session.id,
        run_id=uuid4(),
        system="s",
        cancel=asyncio.Event(),
    )

    assert result.status == AgentRunStatus.succeeded
    assert write_tool.calls == 1


async def test__run__transcript_over_token_budget__compacts_older_messages(tmp_path: Path) -> None:
    # Six alternating messages, each padded to push the transcript over budget.
    repo = JsonChatRepository()
    session = ChatSession(
        id=uuid4(), project_folder=tmp_path, title="t", doc_id=None, created_at=_now(), updated_at=_now()
    )
    repo.save_session(session)
    for i in range(6):
        role = ChatMessageRole.user if i % 2 == 0 else ChatMessageRole.assistant
        repo.append_message(
            tmp_path,
            ChatMessage(
                id=uuid4(),
                session_id=session.id,
                run_id=None,
                seq=-1,
                role=role,
                blocks=[ChatContentBlock(kind=ChatContentKind.text, text="x" * 200)],
                created_at=_now(),
            ),
        )
    summarizer = _FakeSummarizer()
    config = AgentConfig(
        token_budget=40,
        compaction_trigger_ratio=0.5,
        keep_recent_tokens=20,
        keep_recent_messages_min=1,
        max_iterations=3,
        max_output_tokens=100,
    )
    provider = _FakeProvider(
        [NormalizedTurn(text="ответ", tool_calls=(), stop_reason=StopReason.end_turn, usage=TokenUsage())]
    )
    loop = _make_loop(
        repo,
        provider,
        ToolRegistry([]),
        config=config,
        context_service=ChatContextService(),
        summarizer=summarizer,
    )

    await loop.run(
        project_id=uuid4(),
        project_folder=tmp_path,
        session_id=session.id,
        run_id=uuid4(),
        system="база",
        cancel=asyncio.Event(),
    )

    assert summarizer.called is True
    summaries = repo.list_summaries(tmp_path, session.id)
    assert len(summaries) == 1
    assert summaries[0].text == "КРАТКОЕ СОДЕРЖАНИЕ"
    # the older messages are now flagged compacted (kept on disk, excluded from replay)
    messages = repo.list_messages(tmp_path, session.id)
    assert any(m.compacted for m in messages)
    assert not all(m.compacted for m in messages)  # recent tail kept verbatim
    assert len(messages) >= 6  # raw transcript is never lost


async def test__run__transcript_under_token_budget__no_compaction(tmp_path: Path) -> None:
    repo = JsonChatRepository()
    session = _seed_session(repo, tmp_path)
    summarizer = _FakeSummarizer()
    provider = _FakeProvider(
        [NormalizedTurn(text="ок", tool_calls=(), stop_reason=StopReason.end_turn, usage=TokenUsage())]
    )
    loop = _make_loop(
        repo,
        provider,
        ToolRegistry([]),
        config=AgentConfig(token_budget=100000),
        context_service=ChatContextService(),
        summarizer=summarizer,
    )

    await loop.run(
        project_id=uuid4(),
        project_folder=tmp_path,
        session_id=session.id,
        run_id=uuid4(),
        system="база",
        cancel=asyncio.Event(),
    )

    assert summarizer.called is False
    assert repo.list_summaries(tmp_path, session.id) == []
