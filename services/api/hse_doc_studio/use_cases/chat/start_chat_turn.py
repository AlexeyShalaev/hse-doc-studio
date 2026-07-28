from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import structlog

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.agent.edits import select_edit_format
from hse_doc_studio.core.agent.entities import AgentMessage
from hse_doc_studio.core.agent.protocols import IAgentProvider, IApprovalGate
from hse_doc_studio.core.ai import IChatSummarizer
from hse_doc_studio.core.entities import (
    AgentRunRecord,
    AIProvider,
    ChatContentBlock,
    ChatMessage,
    ChatSession,
    Project,
)
from hse_doc_studio.core.enums import AgentRunStatus, ChatContentKind, ChatMessageRole, Lang
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import current_interface_language, localized_error, set_interface_language
from hse_doc_studio.core.repositories import (
    IAgentPersonaRepository,
    IAIProviderRepository,
    IChatRepository,
    IProjectIndexRepository,
    IProjectRepository,
    ISettingsRepository,
)
from hse_doc_studio.core.services import ChatContextService
from hse_doc_studio.infra.ai.agent.run_bus import AgentRunBus
from hse_doc_studio.infra.ai.agent.run_manager import AgentRunManager
from hse_doc_studio.use_cases.chat._agent_loop import AgentLoop, LoopResult
from hse_doc_studio.use_cases.chat._prompt import build_system_prompt
from hse_doc_studio.use_cases.chat._registry import ToolRegistry
from hse_doc_studio.use_cases.chat._support import find_project_folder

logger = structlog.get_logger()

_DEFAULT_PROVIDER_KEY = "default_ai_provider_id"
_DEFAULT_MODEL_KEY = "default_ai_model"
_ENABLED_TOOLS_KEY = "agent_enabled_tools"
_INTERFACE_LANGUAGE_KEY = "interface_language"
_MAX_RUN_DIAGNOSTICS = 400
_RULES_REL_PATH = (".hse-studio", "agent", "rules.md")
_DEFAULT_CHAT_TITLES = {"Новый чат", "New chat", "Untitled", ""}
_TITLE_SYSTEM_PROMPT: dict[Lang, str] = {
    Lang.ru: (
        "Ты создаёшь короткие названия для чатов IDE-ассистента по LaTeX-документам. "
        "Ответь только названием: 2-6 слов, без кавычек, без точки, по-русски. "
        "Название должно отражать задачу пользователя."
    ),
    Lang.en: (
        "You write short titles for chats of an IDE assistant for LaTeX documents. "
        "Reply with the title only: 2-6 words, no quotes, no period, in English. "
        "The title must reflect the user's task."
    ),
}
_TITLE_INPUT_MAX_CHARS = 2_000
_TITLE_MAX_CHARS = 64
_TITLE_TIMEOUT_S = 12.0


def _read_rules(folder: Path) -> str | None:
    # Optional per-project agent rules (ГОСТ/citation/style/language constraints),
    # injected into the system prompt. Mirrors Cursor's project-rules file.
    path = folder.joinpath(*_RULES_REL_PATH)
    try:
        if path.exists():
            text = path.read_text(encoding="utf-8").strip()
            return text or None
    except OSError:
        return None
    return None


@dataclass
class StartChatTurnInput:
    project_id: UUID
    session_id: UUID
    text: str = ""
    provider_id: UUID | None = None
    model: str | None = None
    # Resume an approval-paused run: run_id set + the approved tool call ids.
    run_id: UUID | None = None
    approved_call_ids: tuple[str, ...] = ()
    # Resume a question-paused run: answers keyed by ask_user call id, each a
    # map of question (header/text) → chosen answer text.
    tool_answers: dict[str, dict[str, str]] = field(default_factory=dict)


@dataclass
class StartChatTurnOutput:
    run_id: UUID
    user_message_seq: int


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_default_title(title: str) -> bool:
    return title.strip() in _DEFAULT_CHAT_TITLES


def _fallback_title(text: str) -> str:
    clean = " ".join(text.strip().split())
    if not clean:
        return "Новый чат"
    if len(clean) <= _TITLE_MAX_CHARS:
        return clean.rstrip(" .!?;:")
    return clean[: _TITLE_MAX_CHARS - 1].rstrip(" .,;:-") + "…"


def _clean_generated_title(text: str, fallback: str) -> str:
    title = text.strip().splitlines()[0].strip()
    for prefix in ("Название:", "Title:", "Chat title:", "Заголовок:"):
        if title.lower().startswith(prefix.lower()):
            title = title[len(prefix) :].strip()
            break
    title = title.strip("\"'`“”«» ").rstrip(" .")
    if not title:
        title = fallback
    if len(title) > _TITLE_MAX_CHARS:
        title = title[: _TITLE_MAX_CHARS - 1].rstrip(" .,;:-") + "…"
    return title


def _title_input(text: str, language: Lang = Lang.ru) -> str:
    clean = text.strip()
    if len(clean) <= _TITLE_INPUT_MAX_CHARS:
        return clean
    marker = "[text truncated]" if language == Lang.en else "[текст обрезан]"
    return clean[:_TITLE_INPUT_MAX_CHARS].rstrip() + f"\n\n{marker}"


class StartChatTurnUC:
    """Append the user message and run one agent turn as a background task.

    The turn outlives this request (the client streams it via the run-stream
    endpoint), mirroring TriggerCompileUC. One in-flight turn per session is
    enforced; the terminal run record is written before the bus closes so the
    stream's backfill reports the correct status.
    """

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        chat_repo: IChatRepository,
        ai_provider_repo: IAIProviderRepository,
        settings_repo: ISettingsRepository,
        agent_provider: IAgentProvider,
        registry: ToolRegistry,
        approval_gate: IApprovalGate,
        bus: AgentRunBus,
        run_manager: AgentRunManager,
        context_service: ChatContextService,
        summarizer: IChatSummarizer,
        agent_persona_repo: IAgentPersonaRepository,
    ) -> None:
        self._project_repo = project_repo
        self._project_index_repo = project_index_repo
        self._chat_repo = chat_repo
        self._ai_provider_repo = ai_provider_repo
        self._settings_repo = settings_repo
        self._agent_persona_repo = agent_persona_repo
        self._agent_provider = agent_provider
        self._registry = registry
        self._approval_gate = approval_gate
        self._bus = bus
        self._run_manager = run_manager
        self._context_service = context_service
        self._summarizer = summarizer
        # Hold references to fire-and-forget title-generation tasks so they are
        # not garbage-collected mid-flight (RUF006); discard on completion.
        self._title_tasks: set[asyncio.Task[None]] = set()

    async def execute(self, inp: StartChatTurnInput) -> StartChatTurnOutput:
        folder = find_project_folder(inp.project_id, self._project_repo, self._project_index_repo)
        if folder is None:
            raise NotFoundError(
                localized_error(f"Проект {inp.project_id!r} не найден", f"Project {inp.project_id!r} not found")
            )
        project = self._project_repo.get(folder)
        if project is None:
            raise NotFoundError(
                localized_error(f"Проект {inp.project_id!r} не найден", f"Project {inp.project_id!r} not found")
            )
        session = self._chat_repo.get_session(folder, inp.session_id)
        if session is None:
            raise NotFoundError(
                localized_error(
                    f"Сессия чата {inp.session_id!r} не найдена", f"Chat session {inp.session_id!r} not found"
                )
            )
        if self._run_manager.active_run_for_session(inp.session_id) is not None:
            raise PermissionError("a turn is already running in this chat")
        if inp.run_id is not None:
            return self._resume(inp, folder, project)
        return self._start_new(inp, folder, project, session)

    def _start_new(
        self,
        inp: StartChatTurnInput,
        folder: Path,
        project: Project,
        session: ChatSession,
    ) -> StartChatTurnOutput:
        provider, model = self._resolve_provider(inp, session.default_provider_id, session.default_model)
        should_generate_title = session.message_count == 0 and _is_default_title(session.title)
        now = _now()
        user_message = ChatMessage(
            id=uuid4(),
            session_id=inp.session_id,
            run_id=None,
            seq=-1,
            role=ChatMessageRole.user,
            blocks=[ChatContentBlock(kind=ChatContentKind.text, text=inp.text)],
            created_at=now,
        )
        user_seq = self._chat_repo.append_message(folder, user_message)
        run = AgentRunRecord(
            id=uuid4(),
            session_id=inp.session_id,
            project_folder=folder,
            status=AgentRunStatus.pending,
            created_at=now,
            started_at=None,
            finished_at=None,
            trigger_seq=user_seq,
            model=model,
            provider_id=provider.id,
        )
        self._chat_repo.save_run(run)
        self._spawn(run, project, provider, model, ())
        if should_generate_title and inp.text.strip():
            self._spawn_title_generation(folder, inp.session_id, inp.text, provider, model)
        return StartChatTurnOutput(run_id=run.id, user_message_seq=user_seq)

    def _resume(self, inp: StartChatTurnInput, folder: Path, project: Project) -> StartChatTurnOutput:
        run = self._chat_repo.get_run(folder, inp.run_id) if inp.run_id else None
        if run is None:
            raise NotFoundError(localized_error(f"Запуск {inp.run_id!r} не найден", f"Run {inp.run_id!r} not found"))
        if run.status != AgentRunStatus.awaiting_approval:
            raise ValueError(localized_error("Запуск не ожидает подтверждения", "Run is not awaiting approval"))
        provider = self._ai_provider_repo.get(run.provider_id) if run.provider_id else None
        if provider is None:
            raise ValueError(
                localized_error(
                    "AI-провайдер для этого запуска больше не существует",
                    "AI provider for this run no longer exists",
                )
            )
        # The bus channel was closed when the run paused; reset it for the resume.
        self._bus.discard(run.id)
        self._spawn(run, project, provider, run.model or "", inp.approved_call_ids, inp.tool_answers)
        return StartChatTurnOutput(run_id=run.id, user_message_seq=run.trigger_seq)

    def _spawn(
        self,
        run: AgentRunRecord,
        project: Project,
        provider: AIProvider,
        model: str,
        approved_call_ids: tuple[str, ...],
        tool_answers: dict[str, dict[str, str]] | None = None,
    ) -> None:
        cancel = asyncio.Event()
        task = asyncio.create_task(
            self._run_turn_task(run, project, provider, model, cancel, approved_call_ids, tool_answers or {})
        )
        self._run_manager.register(run.id, task, run.session_id, run.project_folder)

    def _spawn_title_generation(
        self,
        folder: Path,
        session_id: UUID,
        user_text: str,
        provider: AIProvider,
        model: str,
    ) -> None:
        task = asyncio.create_task(self._generate_title_task(folder, session_id, user_text, provider, model))
        self._title_tasks.add(task)
        task.add_done_callback(self._title_tasks.discard)

    async def _generate_title_task(
        self,
        folder: Path,
        session_id: UUID,
        user_text: str,
        provider: AIProvider,
        model: str,
    ) -> None:
        fallback = _fallback_title(user_text)
        language = current_interface_language(self._settings_repo.get().get(_INTERFACE_LANGUAGE_KEY))
        try:
            turn = await asyncio.wait_for(
                self._agent_provider.run_turn(
                    provider=provider,
                    model=model,
                    messages=[AgentMessage(role="user", content=_title_input(user_text, language))],
                    tools=[],
                    system=_TITLE_SYSTEM_PROMPT[language],
                    tool_choice_allowed=False,
                    max_output_tokens=48,
                    temperature=0.1,
                    sink=None,
                    cancel=asyncio.Event(),
                ),
                timeout=_TITLE_TIMEOUT_S,
            )
            title = _clean_generated_title(turn.text, fallback)
        except Exception as exc:  # noqa: BLE001 - title generation must never break the chat turn
            logger.info(
                "chat title generation fallback",
                session_id=str(session_id),
                error_type=type(exc).__name__,
            )
            title = fallback

        session = self._chat_repo.get_session(folder, session_id)
        if session is None or not _is_default_title(session.title):
            return
        session.title = title
        session.updated_at = _now()
        self._chat_repo.save_session(session)

    def _resolve_provider(
        self, inp: StartChatTurnInput, session_provider_id: UUID | None, session_model: str | None
    ) -> tuple[AIProvider, str]:
        provider_id = inp.provider_id or session_provider_id
        model = inp.model or session_model
        if provider_id is None or not model:
            stored = self._settings_repo.get()
            if provider_id is None and stored.get(_DEFAULT_PROVIDER_KEY):
                provider_id = UUID(str(stored[_DEFAULT_PROVIDER_KEY]))
            if not model:
                model = stored.get(_DEFAULT_MODEL_KEY)
        if provider_id is None:
            raise ValueError(
                localized_error(
                    "AI-провайдер не выбран: настройте провайдера по умолчанию или передайте provider_id",
                    "No AI provider selected: configure a default provider or pass provider_id",
                )
            )
        provider = self._ai_provider_repo.get(provider_id)
        if provider is None:
            raise NotFoundError(
                localized_error(f"AI-провайдер {provider_id!r} не найден", f"AI provider {provider_id!r} not found")
            )
        if not model:
            raise ValueError(
                localized_error(
                    "модель не выбрана: выберите модель по умолчанию или передайте model",
                    "No model selected: choose a default model or pass model",
                )
            )
        return provider, model

    def _enabled_tools(self) -> frozenset[str] | None:
        # null/missing → all tools; a stored list restricts the agent's catalog.
        stored = self._settings_repo.get().get(_ENABLED_TOOLS_KEY)
        if isinstance(stored, list):
            return frozenset(str(name) for name in stored)
        return None

    async def _run_turn_task(
        self,
        run: AgentRunRecord,
        project: Project,
        provider: AIProvider,
        model: str,
        cancel: asyncio.Event,
        approved_call_ids: tuple[str, ...],
        tool_answers: dict[str, dict[str, str]],
    ) -> None:
        folder = run.project_folder
        cancelled = False
        loop = AgentLoop(
            provider=self._agent_provider,
            ai_provider=provider,
            model=model,
            registry=self._registry,
            approval_gate=self._approval_gate,
            chat_repo=self._chat_repo,
            bus=self._bus,
            config=settings.agent,
            context_service=self._context_service,
            summarizer=self._summarizer,
            allowed_tools=self._enabled_tools(),
        )
        # Interface (conversation) language: request header (inherited by this
        # background task) → persisted settings → ru. Re-set so deeper code (chat
        # summarizer) reads the resolved value.
        language = current_interface_language(self._settings_repo.get().get(_INTERFACE_LANGUAGE_KEY))
        set_interface_language(language.value)
        session = self._chat_repo.get_session(folder, run.session_id)
        custom_personas = {str(p.id): p.instruction for p in self._agent_persona_repo.list_all()}
        system = build_system_prompt(
            project,
            select_edit_format(provider.type, model),
            rules=_read_rules(folder),
            persona_id=session.persona if session else None,
            persona_instructions=session.persona_instructions if session else None,
            custom_personas=custom_personas,
            language=language,
        )
        try:
            run.status = AgentRunStatus.running
            run.started_at = _now()
            self._chat_repo.save_run(run)
            result = await loop.run(
                project_id=project.id,
                project_folder=folder,
                session_id=run.session_id,
                run_id=run.id,
                system=system,
                cancel=cancel,
                approved_call_ids=approved_call_ids,
                tool_answers=tool_answers,
            )
            self._apply_result(run, result)
        except asyncio.CancelledError:
            cancelled = True
            run.status = AgentRunStatus.cancelled
            run.error = "cancelled by user" if language == Lang.en else "отменено пользователем"
        except Exception as exc:  # noqa: BLE001 — background task must finalize, never crash the loop
            logger.warning("agent run failed", run_id=str(run.id), error_type=type(exc).__name__)
            run.status = AgentRunStatus.failed
            run.error = type(exc).__name__
        finally:
            # awaiting_approval is a pause, not a finish — keep finished_at unset
            # so the run can be resumed.
            if run.status != AgentRunStatus.awaiting_approval:
                run.finished_at = _now()
            # Accumulate per-task diagnostics onto the run (survives pause/resume).
            run.diagnostics = [*run.diagnostics, *loop.diagnostics][-_MAX_RUN_DIAGNOSTICS:]
            self._chat_repo.save_run(run)  # terminal/paused record BEFORE closing the bus
            self._link_session(folder, run)
            self._bus.close(run.id)
            self._run_manager.unregister(run.id)
        if cancelled:
            raise asyncio.CancelledError

    @staticmethod
    def _apply_result(run: AgentRunRecord, result: LoopResult) -> None:
        run.status = result.status
        run.iterations = result.iterations
        run.usage = result.usage
        run.error = result.error
        run.last_emitted_seq = result.last_seq

    def _link_session(self, folder: Path, run: AgentRunRecord) -> None:
        # Reload: the session manifest was mutated (message_count) by the appends
        # during the run, so our captured copy is stale.
        session = self._chat_repo.get_session(folder, run.session_id)
        if session is None:
            return
        session.last_run_id = run.id
        session.updated_at = _now()
        self._chat_repo.save_session(session)
