from __future__ import annotations

import asyncio
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import structlog

from hse_doc_studio.api.config import AgentConfig, settings
from hse_doc_studio.core.agent.edits import select_edit_format
from hse_doc_studio.core.agent.entities import (
    AgentEvent,
    AgentMessage,
    AgentToolContext,
    NormalizedTurn,
    TokenUsage,
    ToolCall,
    ToolResult,
)
from hse_doc_studio.core.agent.protocols import IAgentProvider, IApprovalGate, StreamSink
from hse_doc_studio.core.ai import IChatSummarizer
from hse_doc_studio.core.entities import AIProvider, ChatContentBlock, ChatMessage, ChatSummaryBlock
from hse_doc_studio.core.enums import (
    AgentEventType,
    AgentRunStatus,
    AIProviderType,
    ChatContentKind,
    ChatMessageRole,
    Lang,
    StopReason,
    ToolKind,
)
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.core.repositories import IChatRepository
from hse_doc_studio.core.services import ChatContextService
from hse_doc_studio.infra.ai.agent.run_bus import AgentRunBus
from hse_doc_studio.infra.ai.agent.trace import install_tracer, open_tracer, trace
from hse_doc_studio.use_cases.chat._budget import TokenBudget, truncate_tool_result
from hse_doc_studio.use_cases.chat._prompt import chat_history_to_agent_messages
from hse_doc_studio.use_cases.chat._registry import ToolRegistry

logger = structlog.get_logger()

_STOP_STATES = (StopReason.end_turn, StopReason.max_tokens)
_MAX_DIAGNOSTICS = 200
# Placeholder id for tool context when the agent runs outside a project; only
# requires_project=False tools execute then, so it's never actually used.
_DUMMY_PROJECT_ID = UUID(int=0)


@dataclass
class LoopResult:
    status: AgentRunStatus
    iterations: int
    usage: TokenUsage
    error: str | None
    last_seq: int | None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _add_usage(a: TokenUsage, b: TokenUsage) -> TokenUsage:
    return TokenUsage(input_tokens=a.input_tokens + b.input_tokens, output_tokens=a.output_tokens + b.output_tokens)


def _usage_payload(usage: TokenUsage) -> dict[str, int]:
    return {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "total_tokens": usage.total_tokens,
    }


def _questions_of(call: ToolCall) -> list[Any]:
    questions = call.arguments.get("questions")
    return questions if isinstance(questions, list) else []


def _en() -> bool:
    """True when the request's interface language is English (independent of the
    document language). Used to localize agent-visible tool results and headings."""
    return current_interface_language() is Lang.en


def _answer_result(answers: dict[str, str]) -> ToolResult:
    # The user's structured answers, fed back to the model as the tool result.
    if not answers:
        return ToolResult.ok("the user did not select any answers" if _en() else "пользователь не выбрал ответы")
    lines = [f"- {question}: {answer}" for question, answer in answers.items()]
    header = "User's answers:" if _en() else "Ответы пользователя:"
    return ToolResult.ok(f"{header}\n" + "\n".join(lines))


class _BusSink(StreamSink):
    # Streams only assistant text deltas; the authoritative tool_call / tool_result
    # events are published by the loop once arguments are parsed / the tool ran.
    def __init__(self, bus: AgentRunBus, run_id: UUID) -> None:
        self._bus = bus
        self._run_id = run_id

    def on_text_delta(self, text: str) -> None:
        self._bus.publish(self._run_id, AgentEvent(type=AgentEventType.token, data={"text": text}))

    def on_tool_call_start(self, index: int, call_id: str, name: str) -> None:
        return

    def on_tool_call_args_delta(self, index: int, args_fragment: str) -> None:
        return


class AgentLoop:
    """The gather → act → verify → repeat driver for one turn.

    Publishes events to the run bus and persists each completed message to the
    transcript as it goes, so a reconnecting client (live or backfill) sees a
    coherent stream and the on-disk history is always current. Read tools run
    automatically; write/exec approval gating lands in a later phase.
    """

    def __init__(
        self,
        *,
        provider: IAgentProvider,
        ai_provider: AIProvider,
        model: str,
        registry: ToolRegistry,
        approval_gate: IApprovalGate,
        chat_repo: IChatRepository,
        bus: AgentRunBus,
        config: AgentConfig,
        context_service: ChatContextService | None = None,
        summarizer: IChatSummarizer | None = None,
        allowed_tools: frozenset[str] | None = None,
    ) -> None:
        self._provider = provider
        self._ai_provider = ai_provider
        self._model = model
        self._registry = registry
        self._approval_gate = approval_gate
        self._chat_repo = chat_repo
        self._bus = bus
        self._config = config
        # User's Configure-Tools selection (None = all tools available).
        self._allowed_tools = allowed_tools
        # Compaction is optional: when either piece is absent the loop simply
        # replays the full transcript (useful in tests).
        self._context_service = context_service
        self._summarizer = summarizer
        # Per-turn diagnostics for post-hoc debugging (persisted on the run).
        self._diagnostics: list[dict[str, Any]] = []
        # Whether the current run has a project in context (set in run()).
        self._has_project = True

    @property
    def diagnostics(self) -> list[dict[str, Any]]:
        return self._diagnostics

    def _diag(self, entry: dict[str, Any]) -> None:
        self._diagnostics.append(entry)
        if len(self._diagnostics) > _MAX_DIAGNOSTICS:
            del self._diagnostics[: len(self._diagnostics) - _MAX_DIAGNOSTICS]

    def _trace_base_dir(self) -> Path:
        configured = self._config.debug_trace_dir
        base = configured if configured is not None else Path(settings.data_dir).expanduser() / "agent-traces"
        return base

    async def run(
        self,
        *,
        project_id: UUID | None,
        project_folder: Path,
        session_id: UUID,
        run_id: UUID,
        system: str,
        cancel: asyncio.Event,
        approved_call_ids: tuple[str, ...] = (),
        tool_answers: dict[str, dict[str, str]] | None = None,
    ) -> LoopResult:
        # Wrap the whole turn in the (opt-in) debug tracer so both the loop's own
        # events and the provider's request/chunks land in one per-run file.
        tracer = open_tracer(
            self._trace_base_dir(),
            run_id,
            enabled=self._config.debug_trace,
            keep=self._config.debug_trace_keep,
        )
        with install_tracer(tracer):
            if tracer is not None:
                trace(
                    "loop_start",
                    project_id=str(project_id) if project_id is not None else None,
                    session_id=str(session_id),
                    model=self._model,
                    provider_id=str(self._ai_provider.id),
                    provider_type=self._ai_provider.type.value,
                    allowed_tools=sorted(self._allowed_tools) if self._allowed_tools is not None else None,
                )
            return await self._run(
                project_id=project_id,
                project_folder=project_folder,
                session_id=session_id,
                run_id=run_id,
                system=system,
                cancel=cancel,
                approved_call_ids=approved_call_ids,
                tool_answers=tool_answers,
            )

    async def _run(  # noqa: C901, PLR0912 — turn-loop state machine, flat by design
        self,
        *,
        project_id: UUID | None,
        project_folder: Path,
        session_id: UUID,
        run_id: UUID,
        system: str,
        cancel: asyncio.Event,
        approved_call_ids: tuple[str, ...] = (),
        tool_answers: dict[str, dict[str, str]] | None = None,
    ) -> LoopResult:
        answers = tool_answers or {}
        self._diagnostics = []
        self._has_project = project_id is not None
        await self._maybe_compact(project_folder, session_id, run_id, system)
        summaries = self._chat_repo.list_summaries(project_folder, session_id)
        history = [m for m in self._chat_repo.list_messages(project_folder, session_id) if not m.compacted]
        agent_messages = chat_history_to_agent_messages(history)
        system = self._system_with_summaries(system, summaries)
        weak = self._ai_provider.type == AIProviderType.ollama
        tools = self._registry.specs(weak_model=weak, allowed=self._allowed_tools, has_project=self._has_project)
        ctx = AgentToolContext(
            project_id=project_id if project_id is not None else _DUMMY_PROJECT_ID,
            model=self._model,
            edit_format=select_edit_format(self._ai_provider.type, self._model),
        )
        budget = TokenBudget(self._config.token_budget)
        total = TokenUsage()
        last_seq: int | None = None
        sink = _BusSink(self._bus, run_id)

        # Resume: execute any tool calls left pending by a previous approval pause.
        pending = self._pending_tool_calls(history)
        if pending:
            last_seq, suspended = await self._dispatch_tool_calls(
                pending, ctx, project_folder, session_id, run_id, agent_messages, approved_call_ids, answers, last_seq
            )
            if suspended:
                return LoopResult(AgentRunStatus.awaiting_approval, 0, total, None, last_seq)

        for iteration in range(1, self._config.max_iterations + 1):
            if cancel.is_set():
                return LoopResult(
                    AgentRunStatus.cancelled, iteration - 1, total, "cancelled" if _en() else "отменено", last_seq
                )
            self._bus.publish(run_id, AgentEvent(type=AgentEventType.iteration, data={"n": iteration}))

            started_at = time.monotonic()
            turn = await self._provider.run_turn(
                provider=self._ai_provider,
                model=self._model,
                messages=agent_messages,
                tools=tools,
                system=system,
                tool_choice_allowed=not weak,
                max_output_tokens=self._config.max_output_tokens,
                temperature=self._config.temperature,
                sink=sink,
                cancel=cancel,
            )
            turn_duration_ms = int((time.monotonic() - started_at) * 1000)
            tool_names = [c.name for c in turn.tool_calls]
            logger.info(
                "agent turn",
                run_id=str(run_id),
                iteration=iteration,
                stop_reason=turn.stop_reason.value,
                raw_stop=turn.raw_stop,
                n_tool_calls=len(turn.tool_calls),
                tool_names=tool_names,
                text_len=len(turn.text),
                in_tokens=turn.usage.input_tokens,
                out_tokens=turn.usage.output_tokens,
                duration_ms=turn_duration_ms,
            )
            self._diag(
                {
                    "kind": "turn",
                    "iteration": iteration,
                    "stop_reason": turn.stop_reason.value,
                    "raw_stop": turn.raw_stop,
                    "tool_names": tool_names,
                    "text_len": len(turn.text),
                    "out_tokens": turn.usage.output_tokens,
                    "duration_ms": turn_duration_ms,
                }
            )
            trace(
                "loop_turn",
                iteration=iteration,
                stop_reason=turn.stop_reason.value,
                raw_stop=turn.raw_stop,
                tool_calls=[{"id": c.id, "name": c.name, "arguments": c.arguments} for c in turn.tool_calls],
                text=turn.text,
                in_tokens=turn.usage.input_tokens,
                out_tokens=turn.usage.output_tokens,
                duration_ms=turn_duration_ms,
            )
            # The model signalled a tool call but none parsed — usually a weak
            # model emitting the call as free text the adapter couldn't decode.
            if not turn.tool_calls and turn.stop_reason not in _STOP_STATES:
                logger.warning(
                    "agent turn produced no actionable output",
                    run_id=str(run_id),
                    iteration=iteration,
                    raw_stop=turn.raw_stop,
                    text_preview=turn.text[:160],
                )
                self._diag(
                    {
                        "kind": "warning",
                        "iteration": iteration,
                        "message": "нет распознанного вызова инструмента и не финальный ответ",
                        "raw_stop": turn.raw_stop,
                        "text_preview": turn.text[:160],
                    }
                )
                trace(
                    "loop_no_actionable_output",
                    iteration=iteration,
                    raw_stop=turn.raw_stop,
                    text=turn.text,
                )
            total = _add_usage(total, turn.usage)
            budget.add(turn.usage)
            self._bus.publish(run_id, AgentEvent(type=AgentEventType.usage, data=_usage_payload(total)))

            last_seq = self._persist_assistant(project_folder, session_id, run_id, turn)
            agent_messages.append(AgentMessage(role="assistant", content=turn.text, tool_calls=turn.tool_calls))

            if not turn.tool_calls or turn.stop_reason in _STOP_STATES:
                logger.info(
                    "agent loop end",
                    run_id=str(run_id),
                    iteration=iteration,
                    reason="stop" if turn.stop_reason in _STOP_STATES else "no_tool_calls",
                )
                return LoopResult(AgentRunStatus.succeeded, iteration, total, None, last_seq)
            if budget.exhausted():
                logger.info("agent loop end", run_id=str(run_id), iteration=iteration, reason="budget_exhausted")
                return LoopResult(AgentRunStatus.succeeded, iteration, total, None, last_seq)

            last_seq, suspended = await self._dispatch_tool_calls(
                turn.tool_calls,
                ctx,
                project_folder,
                session_id,
                run_id,
                agent_messages,
                approved_call_ids,
                answers,
                last_seq,
            )
            if suspended:
                return LoopResult(AgentRunStatus.awaiting_approval, iteration, total, None, last_seq)

        logger.info(
            "agent loop end",
            run_id=str(run_id),
            iteration=self._config.max_iterations,
            reason="max_iterations",
        )
        return LoopResult(AgentRunStatus.succeeded, self._config.max_iterations, total, None, last_seq)

    @staticmethod
    def _system_with_summaries(system: str, summaries: list[ChatSummaryBlock]) -> str:
        if not summaries:
            return system
        joined = "\n\n".join(s.text for s in summaries)
        heading = "Summary of earlier messages" if _en() else "Краткое содержание ранних сообщений"
        return f"{system}\n\n## {heading}\n{joined}"

    async def _maybe_compact(self, project_folder: Path, session_id: UUID, run_id: UUID, system: str) -> None:
        if self._context_service is None or self._summarizer is None:
            return
        messages = [m for m in self._chat_repo.list_messages(project_folder, session_id) if not m.compacted]
        summaries = self._chat_repo.list_summaries(project_folder, session_id)
        if not self._context_service.needs_compaction(
            system=system,
            messages=messages,
            summaries=summaries,
            token_budget=self._config.token_budget,
            trigger_ratio=self._config.compaction_trigger_ratio,
        ):
            return
        cutoff = self._context_service.plan_cutoff(
            messages,
            keep_recent_tokens=self._config.keep_recent_tokens,
            keep_recent_messages_min=self._config.keep_recent_messages_min,
        )
        if cutoff is None:
            return
        to_summarize = [m for m in messages if m.seq <= cutoff]
        if not to_summarize:
            return
        prior = summaries[-1] if summaries else None
        text = await self._summarizer.summarize(to_summarize, prior, self._model, self._ai_provider)
        summary = ChatSummaryBlock(
            id=uuid4(),
            session_id=session_id,
            covers_from_seq=to_summarize[0].seq,
            covers_to_seq=cutoff,
            created_at=_now(),
            text=text,
            model=self._model,
        )
        self._chat_repo.append_summary(project_folder, summary)
        self._chat_repo.mark_compacted(project_folder, session_id, cutoff)
        self._bus.publish(
            run_id,
            AgentEvent(
                type=AgentEventType.compaction,
                data={"covers_from_seq": to_summarize[0].seq, "covers_to_seq": cutoff, "summary_id": str(summary.id)},
            ),
        )

    def _pending_tool_calls(self, history: list[ChatMessage]) -> list[ToolCall]:
        # Tool calls from the most recent tool-calling assistant message that have
        # no result yet = the calls a prior turn suspended awaiting approval.
        last_assistant: ChatMessage | None = None
        for message in history:
            if message.role == ChatMessageRole.assistant and any(
                b.kind == ChatContentKind.tool_call for b in message.blocks
            ):
                last_assistant = message
        if last_assistant is None:
            return []
        answered = {
            b.call_id
            for m in history
            if m.role == ChatMessageRole.tool
            for b in m.blocks
            if b.kind == ChatContentKind.tool_result and b.call_id
        }
        return [
            ToolCall(id=b.call_id or "", name=b.tool_name or "", arguments=b.args)
            for b in last_assistant.blocks
            if b.kind == ChatContentKind.tool_call and (b.call_id or "") not in answered
        ]

    def _requires_gate(self, call: ToolCall) -> bool:
        tool = self._registry.get(call.name)
        return tool is not None and self._approval_gate.requires_approval(tool.kind)

    def _persist_assistant(self, project_folder: Path, session_id: UUID, run_id: UUID, turn: NormalizedTurn) -> int:
        blocks: list[ChatContentBlock] = []
        if turn.text:
            blocks.append(ChatContentBlock(kind=ChatContentKind.text, text=turn.text))
        blocks.extend(
            ChatContentBlock(kind=ChatContentKind.tool_call, call_id=c.id, tool_name=c.name, args=c.arguments)
            for c in turn.tool_calls
        )
        message = ChatMessage(
            id=uuid4(),
            session_id=session_id,
            run_id=run_id,
            seq=-1,
            role=ChatMessageRole.assistant,
            blocks=blocks,
            created_at=_now(),
            model=self._model,
            provider_id=self._ai_provider.id,
            usage=turn.usage,
        )
        seq = self._chat_repo.append_message(project_folder, message)
        self._bus.publish(
            run_id,
            AgentEvent(type=AgentEventType.message, data={"id": str(message.id), "seq": seq, "role": "assistant"}),
        )
        return seq

    async def _dispatch_tool_calls(  # noqa: C901, PLR0913 — ask/approval/exec dispatch, flat by design
        self,
        calls: Sequence[ToolCall],
        ctx: AgentToolContext,
        project_folder: Path,
        session_id: UUID,
        run_id: UUID,
        agent_messages: list[AgentMessage],
        approved_call_ids: tuple[str, ...],
        tool_answers: dict[str, dict[str, str]],
        last_seq: int | None,
    ) -> tuple[int | None, bool]:
        # 1) Questions: an ask-kind call pauses the run for structured user input
        # unless its answers are already supplied (on resume). Resolve answered
        # ask calls into tool results FIRST so they aren't re-pending if a later
        # approval pause re-enters the dispatch.
        ask_calls = [c for c in calls if self._is_ask(c)]
        unanswered = [c for c in ask_calls if c.id not in tool_answers]
        if unanswered:
            trace("loop_suspend", reason="question_required", call_ids=[c.id for c in unanswered])
            for call in unanswered:
                self._bus.publish(
                    run_id,
                    AgentEvent(
                        type=AgentEventType.question_required,
                        data={"call_id": call.id, "questions": _questions_of(call), "run_id": str(run_id)},
                    ),
                )
            return last_seq, True
        for call in ask_calls:
            last_seq = self._emit_tool_result(
                call,
                _answer_result(tool_answers.get(call.id, {})),
                project_folder,
                session_id,
                run_id,
                agent_messages,
                last_seq,
            )

        remaining = [c for c in calls if not self._is_ask(c)]
        # 2) Approval: if any remaining call needs approval and wasn't approved,
        # suspend the whole batch so the user reviews before any side effect.
        unapproved = [c for c in remaining if self._requires_gate(c) and c.id not in approved_call_ids]
        if unapproved:
            trace(
                "loop_suspend",
                reason="approval_required",
                calls=[{"call_id": c.id, "name": c.name} for c in unapproved],
            )
            for call in unapproved:
                tool = self._registry.get(call.name)
                self._bus.publish(
                    run_id,
                    AgentEvent(
                        type=AgentEventType.approval_required,
                        data={
                            "call_id": call.id,
                            "name": call.name,
                            "args": call.arguments,
                            "kind": tool.kind.value if tool else "",
                            "run_id": str(run_id),
                        },
                    ),
                )
            return last_seq, True

        # 3) Execute the remaining (read/write/exec) calls.
        for call in remaining:
            result = truncate_tool_result(await self._execute_tool(ctx, call), self._config.max_tool_result_tokens)
            last_seq = self._emit_tool_result(
                call, result, project_folder, session_id, run_id, agent_messages, last_seq
            )
        return last_seq, False

    def _emit_tool_result(  # noqa: PLR0913 — small event/persist fan-out
        self,
        call: ToolCall,
        result: ToolResult,
        project_folder: Path,
        session_id: UUID,
        run_id: UUID,
        agent_messages: list[AgentMessage],
        last_seq: int | None,
    ) -> int:
        self._bus.publish(
            run_id,
            AgentEvent(
                type=AgentEventType.tool_call, data={"call_id": call.id, "name": call.name, "args": call.arguments}
            ),
        )
        block = ChatContentBlock(
            kind=ChatContentKind.tool_result,
            call_id=call.id,
            tool_name=call.name,
            result=result.text,
            is_error=result.is_error,
        )
        message = ChatMessage(
            id=uuid4(),
            session_id=session_id,
            run_id=run_id,
            seq=-1,
            role=ChatMessageRole.tool,
            blocks=[block],
            created_at=_now(),
        )
        seq = self._chat_repo.append_message(project_folder, message)
        self._bus.publish(
            run_id,
            AgentEvent(
                type=AgentEventType.tool_result,
                data={"call_id": call.id, "name": call.name, "is_error": result.is_error, "result": result.text},
            ),
        )
        agent_messages.append(AgentMessage(role="tool", content=result.text, tool_call_id=call.id, name=call.name))
        return seq

    def _is_ask(self, call: ToolCall) -> bool:
        tool = self._registry.get(call.name)
        return tool is not None and tool.kind == ToolKind.ask

    async def _execute_tool(self, ctx: AgentToolContext, call: ToolCall) -> ToolResult:
        tool = self._registry.get(call.name)
        if tool is None:
            logger.warning("agent tool unknown", tool=call.name, args_keys=list(call.arguments.keys()))
            self._diag({"kind": "tool", "name": call.name, "result": "unknown"})
            return ToolResult.error(f"unknown tool: {call.name}" if _en() else f"неизвестный инструмент: {call.name}")
        if tool.requires_project and not self._has_project:
            self._diag({"kind": "tool", "name": call.name, "result": "no_project"})
            return ToolResult.error(
                f"tool {call.name} is only available inside a project"
                if _en()
                else f"инструмент {call.name} доступен только внутри проекта"
            )
        if self._allowed_tools is not None and call.name not in self._allowed_tools:
            self._diag({"kind": "tool", "name": call.name, "result": "disabled"})
            return ToolResult.error(
                f"tool {call.name} is disabled in settings"
                if _en()
                else f"инструмент {call.name} отключён в настройках"
            )
        # Approval gating already happened in _dispatch_tool_calls before we reach here.
        trace("tool_exec", name=call.name, arguments=call.arguments)
        started_at = time.monotonic()
        try:
            result = await tool.handler.handle(ctx, call.arguments)
        except Exception as exc:  # noqa: BLE001 — a tool failure must never crash the run
            duration_ms = int((time.monotonic() - started_at) * 1000)
            logger.warning(
                "agent tool failed",
                tool=call.name,
                error_type=type(exc).__name__,
                duration_ms=duration_ms,
            )
            trace("tool_error", name=call.name, error_type=type(exc).__name__, duration_ms=duration_ms)
            self._diag(
                {
                    "kind": "tool",
                    "name": call.name,
                    "result": "exception",
                    "error_type": type(exc).__name__,
                    "duration_ms": duration_ms,
                }
            )
            return ToolResult.error(
                f"tool error {call.name}: {type(exc).__name__}"
                if _en()
                else f"ошибка инструмента {call.name}: {type(exc).__name__}"
            )
        duration_ms = int((time.monotonic() - started_at) * 1000)
        logger.info(
            "agent tool done",
            tool=call.name,
            is_error=result.is_error,
            duration_ms=duration_ms,
        )
        trace(
            "tool_done",
            name=call.name,
            is_error=result.is_error,
            duration_ms=duration_ms,
            result=result.text,
        )
        self._diag(
            {
                "kind": "tool",
                "name": call.name,
                "result": "error" if result.is_error else "ok",
                "duration_ms": duration_ms,
            }
        )
        return result
