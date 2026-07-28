from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import httpx
import openai
import pytest
from hse_doc_studio.core.agent.entities import AgentMessage, NormalizedTurn, TokenUsage, ToolCall, ToolSpec
from hse_doc_studio.core.entities import AIProvider
from hse_doc_studio.core.enums import AIProviderType, StopReason
from hse_doc_studio.infra.ai.agent import sdk_agent_provider as sdk_mod
from hse_doc_studio.infra.ai.agent.anthropic_agent_provider import AnthropicShapedAgentProvider
from hse_doc_studio.infra.ai.agent.openai_agent_provider import (
    OpenAIShapedAgentProvider,
    _parse_tool_args,
    _salvage_text_calls,
)
from hse_doc_studio.infra.ai.agent.sdk_agent_provider import SdkAgentProvider


def _provider(ptype: AIProviderType) -> AIProvider:
    return AIProvider(
        id=uuid4(),
        name="p",
        type=ptype,
        api_key="k",
        base_url="",
        models=[],
        created_at=datetime.now(timezone.utc),
    )


class RecordingSink:
    def __init__(self) -> None:
        self.text: list[str] = []
        self.starts: list[tuple[int, str, str]] = []
        self.args: list[tuple[int, str]] = []

    def on_text_delta(self, text: str) -> None:
        self.text.append(text)

    def on_tool_call_start(self, index: int, call_id: str, name: str) -> None:
        self.starts.append((index, call_id, name))

    def on_tool_call_args_delta(self, index: int, args_fragment: str) -> None:
        self.args.append((index, args_fragment))


# ── OpenAI-shaped fakes ──────────────────────────────────────────────────────


def _chunk(*, content: str | None = None, tool_calls: list[Any] | None = None, finish: str | None = None) -> Any:
    delta = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(delta=delta, finish_reason=finish)
    return SimpleNamespace(choices=[choice], usage=None)


def _usage_chunk(prompt: int, completion: int) -> Any:
    return SimpleNamespace(choices=[], usage=SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion))


def _tcd(index: int, *, call_id: str | None = None, name: str | None = None, args: str | None = None) -> Any:
    return SimpleNamespace(index=index, id=call_id, function=SimpleNamespace(name=name, arguments=args))


class _FakeStream:
    def __init__(self, chunks: list[Any]) -> None:
        self._chunks = chunks
        self.closed = False

    async def _gen(self) -> Any:
        for c in self._chunks:
            yield c

    def __aiter__(self) -> Any:
        return self._gen()

    async def close(self) -> None:
        self.closed = True


class _FakeOpenAIClient:
    def __init__(self, chunks: list[Any], record: dict[str, Any]) -> None:
        self._chunks = chunks
        self._record = record
        self.closed = False
        completions = SimpleNamespace(create=self._create)
        self.chat = SimpleNamespace(completions=completions)

    async def _create(self, **kwargs: Any) -> _FakeStream:
        self._record.clear()
        self._record.update(kwargs)
        return _FakeStream(self._chunks)

    async def close(self) -> None:
        self.closed = True


@pytest.mark.unit
async def test__openai__streams_text_and_real_usage() -> None:
    record: dict[str, Any] = {}
    client = _FakeOpenAIClient(
        [_chunk(content="Hello "), _chunk(content="world", finish="stop"), _usage_chunk(10, 5)], record
    )
    adapter = OpenAIShapedAgentProvider(_provider(AIProviderType.openai), client=client)  # type: ignore[arg-type]
    sink = RecordingSink()

    turn = await adapter.run_turn(
        model="gpt-4o",
        messages=[AgentMessage(role="user", content="hi")],
        tools=[],
        system="sys",
        tool_choice_allowed=True,
        max_output_tokens=100,
        temperature=0.0,
        sink=sink,
        cancel=asyncio.Event(),
    )

    assert turn.text == "Hello world"
    assert turn.tool_calls == ()
    assert turn.stop_reason == StopReason.end_turn
    assert turn.usage.input_tokens == 10
    assert turn.usage.output_tokens == 5
    assert "".join(sink.text) == "Hello world"
    assert client.closed


@pytest.mark.unit
async def test__openai__parses_streamed_tool_call_and_sends_tool_choice() -> None:
    record: dict[str, Any] = {}
    chunks = [
        _chunk(tool_calls=[_tcd(0, call_id="call_1", name="read_tex", args='{"path":')]),
        _chunk(tool_calls=[_tcd(0, args='"a.tex"}')], finish="tool_calls"),
        _usage_chunk(20, 8),
    ]
    client = _FakeOpenAIClient(chunks, record)
    adapter = OpenAIShapedAgentProvider(_provider(AIProviderType.openai), client=client)  # type: ignore[arg-type]
    sink = RecordingSink()

    turn = await adapter.run_turn(
        model="gpt-4o",
        messages=[AgentMessage(role="user", content="read it")],
        tools=[ToolSpec(name="read_tex", description="read", parameters={"type": "object"})],
        system=None,
        tool_choice_allowed=True,
        max_output_tokens=100,
        temperature=0.0,
        sink=sink,
        cancel=asyncio.Event(),
    )

    assert turn.stop_reason == StopReason.tool_calls
    assert len(turn.tool_calls) == 1
    call = turn.tool_calls[0]
    assert call.name == "read_tex"
    assert call.arguments == {"path": "a.tex"}
    assert call.id == "call_1"
    assert sink.starts == [(0, "call_1", "read_tex")]
    assert "tools" in record
    assert record.get("tool_choice") == "auto"
    assert record.get("stream_options") == {"include_usage": True}


@pytest.mark.unit
async def test__ollama__omits_tool_choice_and_stream_options() -> None:
    record: dict[str, Any] = {}
    client = _FakeOpenAIClient([_chunk(content="ok", finish="stop")], record)
    adapter = OpenAIShapedAgentProvider(_provider(AIProviderType.ollama), is_ollama=True, client=client)  # type: ignore[arg-type]

    await adapter.run_turn(
        model="qwen2.5",
        messages=[AgentMessage(role="user", content="hi")],
        tools=[ToolSpec(name="t", description="d", parameters={"type": "object"})],
        system=None,
        tool_choice_allowed=True,
        max_output_tokens=50,
        temperature=0.0,
        sink=None,
        cancel=asyncio.Event(),
    )

    assert "tools" in record  # native tools still advertised
    assert "tool_choice" not in record  # ... but Ollama rejects tool_choice
    assert "stream_options" not in record


class _NativeToolsRejectingClient(_FakeOpenAIClient):
    """Как Ollama с моделью без tool-шаблона (phi3.5): любой запрос с `tools`
    отклоняется 400, повтор без них обслуживается как обычно."""

    def __init__(self, chunks: list[Any], record: dict[str, Any]) -> None:
        super().__init__(chunks, record)
        self.calls: list[dict[str, Any]] = []

    async def _create(self, **kwargs: Any) -> _FakeStream:
        self.calls.append(dict(kwargs))
        if "tools" in kwargs:
            raise openai.BadRequestError(
                "registry.ollama.ai/library/phi3.5:latest does not support tools",
                response=httpx.Response(400, request=httpx.Request("POST", "http://ollama/v1/chat/completions")),
                body=None,
            )
        return await super()._create(**kwargs)


@pytest.mark.unit
async def test__ollama__model_without_tools__retries_with_prompt_injected_tools() -> None:
    record: dict[str, Any] = {}
    client = _NativeToolsRejectingClient([_chunk(content="привет", finish="stop")], record)
    adapter = OpenAIShapedAgentProvider(_provider(AIProviderType.ollama), is_ollama=True, client=client)  # type: ignore[arg-type]

    turn = await adapter.run_turn(
        model="phi3.5:latest",
        messages=[AgentMessage(role="user", content="hi")],
        tools=[ToolSpec(name="read_tex", description="read a tex file", parameters={"type": "object"})],
        system="base",
        tool_choice_allowed=True,
        max_output_tokens=100,
        temperature=0.0,
        sink=None,
        cancel=asyncio.Event(),
    )

    assert turn.text == "привет"
    assert len(client.calls) == 2
    assert "tools" in client.calls[0]  # первая попытка — нативные инструменты
    assert "tools" not in client.calls[1]  # повтор — без них...
    retry_system = client.calls[1]["messages"][0]
    assert retry_system["role"] == "system"
    assert "read_tex" in retry_system["content"]  # ...схемы уехали в промпт


@pytest.mark.unit
async def test__prompt_tools__extracts_tool_call_from_text() -> None:
    record: dict[str, Any] = {}
    text = 'Let me read it. <tool_call>{"name": "read_tex", "arguments": {"path": "a.tex"}}</tool_call>'
    client = _FakeOpenAIClient([_chunk(content=text, finish="stop")], record)
    adapter = OpenAIShapedAgentProvider(
        _provider(AIProviderType.ollama),
        is_ollama=True,
        use_prompt_tools=True,
        client=client,  # type: ignore[arg-type]
    )

    turn = await adapter.run_turn(
        model="llama3.2",
        messages=[AgentMessage(role="user", content="hi")],
        tools=[ToolSpec(name="read_tex", description="read a tex file", parameters={"type": "object"})],
        system="base",
        tool_choice_allowed=False,
        max_output_tokens=100,
        temperature=0.0,
        sink=None,
        cancel=asyncio.Event(),
    )

    assert "tools" not in record  # native tools NOT sent in prompt mode
    sys_msg = record["messages"][0]
    assert sys_msg["role"] == "system"
    assert "<tool_call>" in sys_msg["content"]
    assert len(turn.tool_calls) == 1
    assert turn.tool_calls[0].name == "read_tex"
    assert turn.tool_calls[0].arguments == {"path": "a.tex"}
    assert "<tool_call>" not in turn.text
    assert turn.stop_reason == StopReason.tool_calls


@pytest.mark.unit
async def test__openai__cancel_mid_stream_returns_cancelled() -> None:
    record: dict[str, Any] = {}
    client = _FakeOpenAIClient([_chunk(content="partial")], record)
    adapter = OpenAIShapedAgentProvider(_provider(AIProviderType.openai), client=client)  # type: ignore[arg-type]
    cancel = asyncio.Event()
    cancel.set()

    turn = await adapter.run_turn(
        model="gpt-4o",
        messages=[AgentMessage(role="user", content="hi")],
        tools=[],
        system=None,
        tool_choice_allowed=True,
        max_output_tokens=50,
        temperature=0.0,
        sink=None,
        cancel=cancel,
    )

    assert turn.stop_reason == StopReason.cancelled


def _spec(name: str) -> ToolSpec:
    return ToolSpec(name=name, description="d", parameters={"type": "object"})


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "tool_name", "expected_args", "expected_cleaned"),
    [
        pytest.param(
            '  ;set_theme {"theme": "dark"}',  # the exact qwen2.5 free-text format from the bug report
            "set_theme",
            {"theme": "dark"},
            "",
            id="semicolon_prefixed",
        ),
        pytest.param(
            'set_engine({"engine": "xelatex"}) готово',
            "set_engine",
            {"engine": "xelatex"},
            "готово",
            id="paren_wrapped",
        ),
    ],
)
def test__salvage__recovers_call_and_cleans_remainder(
    text: str, tool_name: str, expected_args: dict[str, Any], expected_cleaned: str
) -> None:
    calls, cleaned = _salvage_text_calls(text, [_spec(tool_name)])

    assert len(calls) == 1
    assert calls[0].name == tool_name
    assert calls[0].arguments == expected_args
    assert cleaned == expected_cleaned


@pytest.mark.unit
def test__salvage__recovers_bare_name_arguments_json() -> None:
    calls, _ = _salvage_text_calls('{"name": "read_tex", "arguments": {"path": "a.tex"}}', [_spec("read_tex")])
    assert len(calls) == 1
    assert calls[0].name == "read_tex"
    assert calls[0].arguments == {"path": "a.tex"}


@pytest.mark.unit
def test__salvage__recovers_tool_call_tag_even_in_native_mode() -> None:
    calls, cleaned = _salvage_text_calls(
        'ок <tool_call>{"name": "set_theme", "arguments": {"theme": "light"}}</tool_call>', [_spec("set_theme")]
    )
    assert len(calls) == 1
    assert calls[0].name == "set_theme"
    assert cleaned == "ок"


@pytest.mark.unit
def test__salvage__ignores_tool_name_mentioned_in_prose() -> None:
    # A name mentioned mid-sentence (not anchored, no JSON) must not become a call.
    calls, cleaned = _salvage_text_calls("Я могу вызвать set_theme, если нужно.", [_spec("set_theme")])
    assert calls == []
    assert cleaned == "Я могу вызвать set_theme, если нужно."


@pytest.mark.unit
@pytest.mark.parametrize(
    "text",
    [
        pytest.param(';do_something {"x": 1}', id="unknown_tool_name"),
        pytest.param('{"answer": 42}', id="plain_json_without_name"),
    ],
)
def test__salvage__ignores_text_without_a_known_call(text: str) -> None:
    calls, _ = _salvage_text_calls(text, [_spec("set_theme")])

    assert calls == []


@pytest.mark.unit
async def test__ollama__salvages_free_text_tool_call_into_turn() -> None:
    # End-to-end through run_turn: native parse finds nothing, salvage recovers it.
    record: dict[str, Any] = {}
    client = _FakeOpenAIClient([_chunk(content='set_theme {"theme": "dark"}', finish="stop")], record)
    adapter = OpenAIShapedAgentProvider(_provider(AIProviderType.ollama), is_ollama=True, client=client)  # type: ignore[arg-type]

    turn = await adapter.run_turn(
        model="qwen2.5",
        messages=[AgentMessage(role="user", content="тёмная тема")],
        tools=[_spec("set_theme")],
        system=None,
        tool_choice_allowed=False,
        max_output_tokens=50,
        temperature=0.0,
        sink=None,
        cancel=asyncio.Event(),
    )

    assert turn.stop_reason == StopReason.tool_calls
    assert len(turn.tool_calls) == 1
    assert turn.tool_calls[0].name == "set_theme"
    assert turn.tool_calls[0].arguments == {"theme": "dark"}
    assert turn.text == ""


@pytest.mark.unit
def test__parse_tool_args__repairs_fences_and_trailing_commas() -> None:
    assert _parse_tool_args('```json\n{"a": 1}\n```') == {"a": 1}
    assert _parse_tool_args('{"a": "b",}') == {"a": "b"}
    assert _parse_tool_args("not json") == {}
    assert _parse_tool_args("") == {}


@pytest.mark.unit
def test__openai_build_messages__maps_tool_calls_and_results() -> None:
    adapter = OpenAIShapedAgentProvider(_provider(AIProviderType.openai))
    msgs = [
        AgentMessage(role="user", content="hi"),
        AgentMessage(
            role="assistant", content="", tool_calls=(ToolCall(id="c1", name="read_tex", arguments={"path": "a.tex"}),)
        ),
        AgentMessage(role="tool", content="file body", tool_call_id="c1", name="read_tex"),
    ]

    out = adapter._build_messages(msgs, "system text", [])

    assert out[0] == {"role": "system", "content": "system text"}
    assert out[1] == {"role": "user", "content": "hi"}
    assert out[2]["role"] == "assistant"
    assert out[2]["tool_calls"][0]["id"] == "c1"
    assert json.loads(out[2]["tool_calls"][0]["function"]["arguments"]) == {"path": "a.tex"}
    assert out[3] == {"role": "tool", "tool_call_id": "c1", "content": "file body"}


# ── Anthropic-shaped fakes ───────────────────────────────────────────────────


class _FakeAnthropicStream:
    def __init__(self, events: list[Any], final: Any) -> None:
        self._events = events
        self._final = final

    async def __aenter__(self) -> _FakeAnthropicStream:
        return self

    async def __aexit__(self, *_: Any) -> bool:
        return False

    async def _gen(self) -> Any:
        for e in self._events:
            yield e

    def __aiter__(self) -> Any:
        return self._gen()

    async def get_final_message(self) -> Any:
        return self._final


class _FakeAnthropicClient:
    def __init__(self, events: list[Any], final: Any, record: dict[str, Any]) -> None:
        self._events = events
        self._final = final
        self._record = record
        self.closed = False
        self.messages = SimpleNamespace(stream=self._stream)

    def _stream(self, **kwargs: Any) -> _FakeAnthropicStream:
        self._record.clear()
        self._record.update(kwargs)
        return _FakeAnthropicStream(self._events, self._final)

    async def close(self) -> None:
        self.closed = True


@pytest.mark.unit
def test__anthropic_build_messages__groups_consecutive_tool_results() -> None:
    adapter = AnthropicShapedAgentProvider(_provider(AIProviderType.claude))
    msgs = [
        AgentMessage(
            role="assistant",
            content="",
            tool_calls=(ToolCall(id="t1", name="a", arguments={}), ToolCall(id="t2", name="b", arguments={})),
        ),
        AgentMessage(role="tool", content="r1", tool_call_id="t1"),
        AgentMessage(role="tool", content="r2", tool_call_id="t2"),
    ]

    out = adapter._build_messages(msgs)

    assert out[0]["role"] == "assistant"
    assert [b["type"] for b in out[0]["content"]] == ["tool_use", "tool_use"]
    assert out[1]["role"] == "user"
    assert [b["tool_use_id"] for b in out[1]["content"]] == ["t1", "t2"]


@pytest.mark.unit
async def test__anthropic__streams_tool_use_via_final_message() -> None:
    record: dict[str, Any] = {}
    events = [
        SimpleNamespace(
            type="content_block_start",
            index=0,
            content_block=SimpleNamespace(type="tool_use", id="t1", name="read_tex"),
        ),
        SimpleNamespace(
            type="content_block_delta",
            index=0,
            delta=SimpleNamespace(type="input_json_delta", partial_json='{"path":"a.tex"}'),
        ),
    ]
    final = SimpleNamespace(
        content=[SimpleNamespace(type="tool_use", id="t1", name="read_tex", input={"path": "a.tex"})],
        stop_reason="tool_use",
        usage=SimpleNamespace(input_tokens=12, output_tokens=3),
    )
    client = _FakeAnthropicClient(events, final, record)
    adapter = AnthropicShapedAgentProvider(_provider(AIProviderType.claude), client=client)  # type: ignore[arg-type]
    sink = RecordingSink()

    turn = await adapter.run_turn(
        model="claude-x",
        messages=[AgentMessage(role="user", content="hi")],
        tools=[ToolSpec(name="read_tex", description="d", parameters={"type": "object"})],
        system="sys",
        tool_choice_allowed=True,
        max_output_tokens=100,
        temperature=0.0,
        sink=sink,
        cancel=asyncio.Event(),
    )

    assert turn.stop_reason == StopReason.tool_calls
    assert turn.tool_calls[0].arguments == {"path": "a.tex"}
    assert turn.usage.input_tokens == 12
    assert turn.usage.output_tokens == 3
    assert record["system"] == "sys"
    assert record["tool_choice"] == {"type": "auto"}
    assert sink.starts == [(0, "t1", "read_tex")]
    assert client.closed


# ── SdkAgentProvider dispatch ────────────────────────────────────────────────


def _sentinel_turn() -> NormalizedTurn:
    return NormalizedTurn(text="x", tool_calls=(), stop_reason=StopReason.end_turn, usage=TokenUsage())


@pytest.mark.unit
async def test__sdk_dispatch__claude_uses_anthropic_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    used: dict[str, Any] = {}

    class FakeAnthropic:
        def __init__(self, provider: Any, **_: Any) -> None:
            used["adapter"] = "anthropic"

        async def run_turn(self, **_: Any) -> NormalizedTurn:
            return _sentinel_turn()

    monkeypatch.setattr(sdk_mod, "AnthropicShapedAgentProvider", FakeAnthropic)

    turn = await SdkAgentProvider().run_turn(
        provider=_provider(AIProviderType.claude),
        model="claude-x",
        messages=[],
        tools=[],
        system=None,
        tool_choice_allowed=True,
        max_output_tokens=10,
        temperature=0.0,
        sink=None,
        cancel=asyncio.Event(),
    )

    assert used["adapter"] == "anthropic"
    assert turn.text == "x"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("ptype", "expect_ollama"),
    [(AIProviderType.openai, False), (AIProviderType.openai_compat, False), (AIProviderType.ollama, True)],
)
async def test__sdk_dispatch__openai_family_sets_ollama_flag(
    monkeypatch: pytest.MonkeyPatch, ptype: AIProviderType, expect_ollama: bool
) -> None:
    captured: dict[str, Any] = {}

    class FakeOpenAI:
        def __init__(self, provider: Any, tokenizer: Any = None, *, is_ollama: bool = False) -> None:
            captured["is_ollama"] = is_ollama

        async def run_turn(self, **_: Any) -> NormalizedTurn:
            return _sentinel_turn()

    monkeypatch.setattr(sdk_mod, "OpenAIShapedAgentProvider", FakeOpenAI)

    await SdkAgentProvider().run_turn(
        provider=_provider(ptype),
        model="m",
        messages=[],
        tools=[],
        system=None,
        tool_choice_allowed=True,
        max_output_tokens=10,
        temperature=0.0,
        sink=None,
        cancel=asyncio.Event(),
    )

    assert captured["is_ollama"] is expect_ollama
