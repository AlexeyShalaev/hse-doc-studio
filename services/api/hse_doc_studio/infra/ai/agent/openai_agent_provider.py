from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Sequence
from typing import Any

import openai
import structlog

from hse_doc_studio.core.agent.entities import (
    AgentMessage,
    NormalizedTurn,
    TokenUsage,
    ToolCall,
    ToolSpec,
)
from hse_doc_studio.core.agent.protocols import StreamSink
from hse_doc_studio.core.entities import AIProvider
from hse_doc_studio.core.enums import StopReason
from hse_doc_studio.infra.ai.agent._support import build_async_http_client
from hse_doc_studio.infra.ai.agent.tokenizer import HeuristicTokenizer
from hse_doc_studio.infra.ai.agent.trace import current_tracer, trace
from hse_doc_studio.infra.docker.siblings import outbound_url

logger = structlog.get_logger()

# OpenAI finish_reason → normalized stop reason.
_FINISH_MAP: dict[str, StopReason] = {
    "tool_calls": StopReason.tool_calls,
    "function_call": StopReason.tool_calls,
    "stop": StopReason.end_turn,
    "length": StopReason.max_tokens,
}

# Prompt-injected tool protocol for weak/local models that can't (reliably) use
# native function calling: the model emits one fenced block per tool call.
_TOOL_CALL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)


class _Accumulator:
    # Mutable streaming state, kept off run_turn so the per-chunk handler stays flat.
    def __init__(self) -> None:
        self.text: list[str] = []
        self.tool_acc: dict[int, dict[str, str]] = {}
        self.started: set[int] = set()
        self.finish: str = ""
        self.usage_in: int = 0
        self.usage_out: int = 0


class OpenAIShapedAgentProvider:
    """One normalized agent round-trip over the OpenAI-compatible chat API.

    Covers provider types ``openai``, ``openai_compat`` and ``ollama`` (built the
    same way as ``OpenAICompatClient``). Two tool-calling modes:

    * native (default): tools are passed via the ``tools`` param; the model
      returns ``tool_calls``. **Ollama gotcha:** its OpenAI-compat endpoint does
      not support ``tool_choice``, so we never send it for ollama.
    * prompt-injected (``use_prompt_tools``): for models with no/unreliable
      native tools — the tool schemas go into the system prompt and the model
      emits ``<tool_call>{...}</tool_call>`` blocks we parse back out. Unparseable
      output is simply treated as a final answer, so the loop never crashes.
    """

    def __init__(
        self,
        provider: AIProvider,
        tokenizer: HeuristicTokenizer | None = None,
        *,
        is_ollama: bool = False,
        use_prompt_tools: bool = False,
        client: openai.AsyncOpenAI | None = None,
    ) -> None:
        self._provider = provider
        self._tokenizer = tokenizer or HeuristicTokenizer()
        self._is_ollama = is_ollama
        self._use_prompt_tools = use_prompt_tools
        self._injected_client = client

    def _build_client(self) -> openai.AsyncOpenAI:
        if self._injected_client is not None:
            return self._injected_client
        return openai.AsyncOpenAI(
            api_key=self._provider.api_key or "not-needed",
            base_url=outbound_url(self._provider.base_url) or None,
            http_client=build_async_http_client(
                ssl_verify=self._provider.ssl_verify,
                connect_timeout_s=self._provider.connect_timeout_s,
                request_timeout_s=self._provider.request_timeout_s,
            ),
        )

    def _build_request(
        self,
        model: str,
        oai_messages: list[dict[str, Any]],
        tools: Sequence[ToolSpec],
        tool_choice_allowed: bool,
        max_output_tokens: int,
        temperature: float,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": oai_messages,
            "max_tokens": max_output_tokens,
            "temperature": temperature,
            "stream": True,
        }
        if tools and not self._use_prompt_tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {"name": t.name, "description": t.description, "parameters": t.parameters},
                }
                for t in tools
            ]
            # Ollama's /v1/chat/completions rejects tool_choice → never send it.
            if tool_choice_allowed and not self._is_ollama:
                kwargs["tool_choice"] = "auto"
        if not self._is_ollama:
            # Some OpenAI-compat servers (Ollama) 400 on unknown stream options.
            kwargs["stream_options"] = {"include_usage": True}
        return kwargs

    async def run_turn(
        self,
        *,
        model: str,
        messages: Sequence[AgentMessage],
        tools: Sequence[ToolSpec],
        system: str | None,
        tool_choice_allowed: bool,
        max_output_tokens: int,
        temperature: float,
        sink: StreamSink | None,
        cancel: asyncio.Event,
    ) -> NormalizedTurn:
        oai_messages = self._build_messages(messages, system, tools)
        kwargs = self._build_request(model, oai_messages, tools, tool_choice_allowed, max_output_tokens, temperature)

        trace(
            "openai_request",
            model=model,
            provider_type=self._provider.type.value,
            base_url=outbound_url(self._provider.base_url) or None,
            is_ollama=self._is_ollama,
            use_prompt_tools=self._use_prompt_tools,
            tool_choice_allowed=tool_choice_allowed,
            native_tools_sent="tools" in kwargs,
            tool_choice=kwargs.get("tool_choice"),
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            system=system,
            tool_specs=[{"name": t.name, "parameters": t.parameters} for t in tools],
            messages=oai_messages,
        )

        client = self._build_client()
        acc = _Accumulator()
        try:
            try:
                stream = await client.chat.completions.create(**kwargs)
            except openai.BadRequestError as exc:
                # Модели без tool-шаблона (например phi3.5 в Ollama) отвечают 400
                # на ЛЮБОЙ запрос с `tools` — раньше это молча роняло весь ран.
                # Переключаемся на prompt-injected инструменты (схемы в системном
                # промпте + разбор свободного текста) и повторяем тот же ход.
                if self._use_prompt_tools or not tools or "does not support tools" not in str(exc):
                    raise
                logger.info("model rejects native tools; retrying with prompt-injected tools", model=model)
                trace("prompt_tools_fallback", model=model, error=str(exc))
                self._use_prompt_tools = True
                oai_messages = self._build_messages(messages, system, tools)
                kwargs = self._build_request(
                    model, oai_messages, tools, tool_choice_allowed, max_output_tokens, temperature
                )
                stream = await client.chat.completions.create(**kwargs)
            async for chunk in stream:
                if cancel.is_set():
                    await stream.close()
                    trace("cancelled", phase="mid_stream")
                    return self._build_turn(acc, oai_messages, tools, system, cancelled=True)
                self._process_chunk(chunk, acc, sink)
        except Exception as exc:  # noqa: BLE001 — record the failure in the trace, then re-raise
            trace("openai_error", error_type=type(exc).__name__, error=str(exc))
            raise
        finally:
            await client.close()

        turn = self._build_turn(acc, oai_messages, tools, system)
        if not (acc.usage_in or acc.usage_out):
            return turn  # endpoint omitted usage → the estimate from _build_turn stands
        return NormalizedTurn(
            text=turn.text,
            tool_calls=turn.tool_calls,
            stop_reason=turn.stop_reason,
            usage=TokenUsage(input_tokens=acc.usage_in, output_tokens=acc.usage_out),
            raw_stop=turn.raw_stop,
        )

    def _process_chunk(self, chunk: Any, acc: _Accumulator, sink: StreamSink | None) -> None:
        usage = getattr(chunk, "usage", None)
        if usage is not None:
            acc.usage_in = usage.prompt_tokens or 0
            acc.usage_out = usage.completion_tokens or 0
        if not chunk.choices:
            _trace_chunk(content=None, tool_calls=None, finish=None, usage=usage)
            return
        choice = chunk.choices[0]
        delta = choice.delta
        if delta is not None and delta.content:
            acc.text.append(delta.content)
            if sink is not None:
                sink.on_text_delta(delta.content)
        if delta is not None and delta.tool_calls:
            self._consume_tool_deltas(delta.tool_calls, acc, sink)
        _trace_chunk(
            content=delta.content if delta is not None else None,
            tool_calls=delta.tool_calls if delta is not None else None,
            finish=choice.finish_reason,
            usage=usage,
        )
        if choice.finish_reason:
            acc.finish = choice.finish_reason

    def _consume_tool_deltas(self, deltas: Sequence[Any], acc: _Accumulator, sink: StreamSink | None) -> None:
        for tcd in deltas:
            slot = acc.tool_acc.setdefault(tcd.index, {"id": "", "name": "", "args": ""})
            if tcd.id:
                slot["id"] = tcd.id
            func = getattr(tcd, "function", None)
            if func is not None and func.name:
                slot["name"] = func.name
            if func is not None and func.arguments:
                slot["args"] += func.arguments
            self._emit_tool_deltas(tcd.index, slot, func, acc.started, sink)

    def _emit_tool_deltas(
        self,
        index: int,
        slot: dict[str, str],
        func: Any,
        started: set[int],
        sink: StreamSink | None,
    ) -> None:
        if sink is None:
            return
        if index not in started and slot["id"] and slot["name"]:
            started.add(index)
            sink.on_tool_call_start(index, slot["id"], slot["name"])
        if func is not None and func.arguments:
            sink.on_tool_call_args_delta(index, func.arguments)

    def _build_turn(
        self,
        acc: _Accumulator,
        oai_messages: list[dict[str, Any]],
        tools: Sequence[ToolSpec],
        system: str | None,
        *,
        cancelled: bool = False,
    ) -> NormalizedTurn:
        text = "".join(acc.text)
        if self._use_prompt_tools:
            calls, text = self._extract_prompt_tool_calls(text)
        else:
            calls = self._calls_from_acc(acc.tool_acc)
            # Salvage: weak local models (e.g. qwen2.5) often "narrate" a tool call
            # as plain text instead of using native tool calling — as a
            # <tool_call>{...}</tool_call> block, a bare {"name","arguments"} JSON
            # object, or a `;tool_name {args}` line. When nothing parsed natively,
            # recover those so the turn drives the tool instead of silently ending
            # as a final answer (the user just sees the raw call otherwise).
            if not calls:
                salvaged, cleaned = _salvage_text_calls(text, tools)
                if salvaged:
                    logger.info("agent salvaged text tool calls", count=len(salvaged))
                    trace(
                        "salvaged_text_tool_calls",
                        count=len(salvaged),
                        names=[c.name for c in salvaged],
                        original_text=text,
                    )
                    calls, text = salvaged, cleaned
        stop = self._resolve_stop(acc.finish, calls, cancelled=cancelled)
        out_tokens = self._tokenizer.count(text) + sum(
            self._tokenizer.count(c.name) + self._tokenizer.count(json.dumps(c.arguments, ensure_ascii=False))
            for c in calls
        )
        usage = TokenUsage(
            input_tokens=self._tokenizer.count_messages(
                self._messages_for_estimate(oai_messages), system=system, tools=tools
            ),
            output_tokens=out_tokens,
        )
        trace(
            "openai_turn",
            raw_finish=acc.finish,
            stop_reason=stop.value,
            cancelled=cancelled,
            native_tool_calls=len(acc.tool_acc),
            tool_calls=[{"id": c.id, "name": c.name, "arguments": c.arguments} for c in calls],
            text=text,
        )
        return NormalizedTurn(text=text, tool_calls=tuple(calls), stop_reason=stop, usage=usage, raw_stop=acc.finish)

    @staticmethod
    def _resolve_stop(finish: str, calls: list[ToolCall], *, cancelled: bool) -> StopReason:
        if cancelled:
            return StopReason.cancelled
        if calls:
            return StopReason.tool_calls
        stop = _FINISH_MAP.get(finish, StopReason.end_turn)
        # finish said tool_calls but none parsed → treat as a finished answer.
        return StopReason.end_turn if stop == StopReason.tool_calls else stop

    def _messages_for_estimate(self, oai_messages: list[dict[str, Any]]) -> list[AgentMessage]:
        # Cheap projection of the outgoing messages back to AgentMessage just for
        # token estimation when the endpoint omits usage.
        return [
            AgentMessage(role=str(m.get("role", "user")), content=str(m.get("content") or "")) for m in oai_messages
        ]

    def _calls_from_acc(self, tool_acc: dict[int, dict[str, str]]) -> list[ToolCall]:
        calls: list[ToolCall] = []
        for idx in sorted(tool_acc):
            slot = tool_acc[idx]
            if not slot["name"]:
                continue
            calls.append(
                ToolCall(
                    id=slot["id"] or f"call-{idx}",
                    name=slot["name"],
                    arguments=_parse_tool_args(slot["args"]),
                    raw_arguments=slot["args"],
                )
            )
        return calls

    def _extract_prompt_tool_calls(self, text: str) -> tuple[list[ToolCall], str]:
        return _extract_tagged_calls(text)

    def _build_messages(
        self,
        messages: Sequence[AgentMessage],
        system: str | None,
        tools: Sequence[ToolSpec],
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        system_text = system or ""
        if self._use_prompt_tools and tools:
            system_text = (system_text + "\n\n" + _prompt_tool_instructions(tools)).strip()
        if system_text:
            out.append({"role": "system", "content": system_text})
        out.extend(self._map_message(m) for m in messages)
        return out

    @staticmethod
    def _map_message(m: AgentMessage) -> dict[str, Any]:
        if m.role == "assistant" and m.tool_calls:
            return {
                "role": "assistant",
                "content": m.content or None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": json.dumps(tc.arguments, ensure_ascii=False)},
                    }
                    for tc in m.tool_calls
                ],
            }
        if m.role == "tool":
            return {"role": "tool", "tool_call_id": m.tool_call_id or "", "content": m.content}
        return {"role": m.role, "content": m.content}


def _parse_tool_args(raw: str) -> dict[str, Any]:
    raw = (raw or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        repaired = _repair_json(raw)
        try:
            parsed = json.loads(repaired)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            logger.warning("agent tool args parse failed", raw_len=len(raw))
            return {}


def _repair_json(raw: str) -> str:
    # Best-effort cleanup of the common ways weak models break JSON: markdown
    # fences and trailing commas. Not a full parser — just enough to recover.
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
    return cleaned.strip()


def _prompt_tool_instructions(tools: Sequence[ToolSpec]) -> str:
    lines = [
        "You can call tools. To call a tool, output EXACTLY one block per call:",
        '<tool_call>{"name": "<tool_name>", "arguments": { ... }}</tool_call>',
        "Output plain text to answer without calling a tool. Available tools:",
    ]
    lines.extend(f"- {t.name}: {t.description} params={json.dumps(t.parameters, ensure_ascii=False)}" for t in tools)
    return "\n".join(lines)


# Prefix the model may put before a free-text tool name (`;`, `:`, `>`, markdown
# bullets) plus the name itself and an optional opening paren — used only to
# recognise an *anchored* free-text call, never a name mentioned mid-sentence.
_LEADING_NAME_RE = re.compile(r"^[\s;:>*-]*([A-Za-z_][A-Za-z0-9_]*)\s*\(?\s*")


def _extract_tagged_calls(text: str) -> tuple[list[ToolCall], str]:
    """Pull every ``<tool_call>{...}</tool_call>`` block out of `text`.

    Returns the parsed calls and the text with the blocks removed. Accepts
    ``arguments`` or its common alias ``parameters`` for the args object.
    """
    calls: list[ToolCall] = []
    for i, match in enumerate(_TOOL_CALL_RE.finditer(text)):
        raw = match.group(1)
        call = _call_from_obj(_parse_tool_args(raw), index=i, raw=raw)
        if call is not None:
            calls.append(call)
    clean = _TOOL_CALL_RE.sub("", text).strip()
    return calls, clean


def _call_from_obj(obj: dict[str, Any], *, index: int, raw: str = "") -> ToolCall | None:
    name = obj.get("name")
    if not isinstance(name, str) or not name:
        return None
    args = obj.get("arguments", obj.get("parameters", {}))
    return ToolCall(
        id=f"local-{index}",
        name=name,
        arguments=args if isinstance(args, dict) else {},
        raw_arguments=raw or json.dumps(obj, ensure_ascii=False),
    )


def _match_brace(text: str, start: int) -> int:  # noqa: C901 — small string-aware brace scanner, flat by design
    # Index of the `}` closing the `{` at `start`, respecting strings; -1 if none.
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _match_leading_named_call(text: str, names: frozenset[str]) -> tuple[ToolCall | None, str]:
    # `;set_theme {"theme": "dark"}` / `set_theme({...})` anchored at the start.
    match = _LEADING_NAME_RE.match(text)
    if match is None or match.group(1) not in names:
        return None, text
    rest = text[match.end() :]
    stripped = rest.lstrip()
    if not stripped.startswith("{"):
        return None, text
    end = _match_brace(stripped, 0)
    if end == -1:
        return None, text
    raw = stripped[: end + 1]
    args = _parse_tool_args(raw)
    call = ToolCall(id="local-0", name=match.group(1), arguments=args, raw_arguments=raw)
    tail = stripped[end + 1 :].lstrip()
    if tail.startswith(")"):
        tail = tail[1:].lstrip()
    return call, tail


def _salvage_text_calls(text: str, tools: Sequence[ToolSpec]) -> tuple[list[ToolCall], str]:
    """Recover a tool call a weak model emitted as plain text (no native call).

    Tries, in order: explicit ``<tool_call>`` tags; a bare ``{"name","arguments"}``
    JSON object; then a ``name {json}`` / ``;name {json}`` / ``name({json})`` line
    naming a KNOWN tool. Returns the recovered calls and the text with them
    removed. The bare-JSON and named matches are anchored to the start of the
    (stripped) text so ordinary prose that merely mentions a tool isn't mistaken
    for a call. Returns ``([], text)`` when nothing recognisable is present.
    """
    tagged, cleaned = _extract_tagged_calls(text)
    if tagged:
        return tagged, cleaned

    stripped = text.strip()
    if not stripped:
        return [], text

    if stripped.startswith("{"):
        end = _match_brace(stripped, 0)
        if end != -1:
            call = _call_from_obj(_parse_tool_args(stripped[: end + 1]), index=0, raw=stripped[: end + 1])
            if call is not None:
                return [call], stripped[end + 1 :].strip()

    call, remainder = _match_leading_named_call(stripped, frozenset(t.name for t in tools))
    if call is not None:
        return [call], remainder
    return [], text


def _trace_chunk(*, content: str | None, tool_calls: Any, finish: str | None, usage: Any) -> None:
    # Per-chunk trace. Guarded so the payload is only built when tracing is on
    # (this runs for every streamed delta).
    if current_tracer() is None:
        return
    deltas: list[dict[str, Any]] | None = None
    if tool_calls:
        deltas = []
        for tcd in tool_calls:
            func = getattr(tcd, "function", None)
            deltas.append(
                {
                    "index": getattr(tcd, "index", None),
                    "id": getattr(tcd, "id", None),
                    "name": getattr(func, "name", None) if func is not None else None,
                    "arguments": getattr(func, "arguments", None) if func is not None else None,
                }
            )
    usage_payload = None
    if usage is not None:
        usage_payload = {
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
        }
    trace("openai_chunk", content=content, tool_calls=deltas, finish=finish, usage=usage_payload)
