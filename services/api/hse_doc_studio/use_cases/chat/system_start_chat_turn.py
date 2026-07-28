from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import structlog

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.agent.edits import select_edit_format
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
from hse_doc_studio.use_cases.chat.personas import apply_persona

logger = structlog.get_logger()

_DEFAULT_TITLES = {"Новый чат", "New chat", "Untitled", ""}
_TITLE_MAX_CHARS = 64
_MAX_RUN_DIAGNOSTICS = 400
_ENABLED_TOOLS_KEY = "agent_enabled_tools"
_INTERFACE_LANGUAGE_KEY = "interface_language"

# Ни вуз, ни образовательная программа в промпте не называются намеренно — см. комментарий
# у _BASE_PROMPT в use_cases/chat/_prompt.py: и то и другое задаёт пак шаблонов проекта.
_SYSTEM_PROMPT: dict[Lang, str] = {
    Lang.ru: (
        "Ты — ИИ-ассистент локального инструмента подготовки учебных документов. "
        "Сейчас ты работаешь вне конкретного проекта — как общий "
        "ассистент приложения. Чем помогаешь: создавать проекты (create_project) из шаблонов "
        "(сначала посмотри list_templates), показывать существующие проекты (list_projects), менять "
        "настройки приложения — тему оформления (set_theme) и движок сборки (set_engine).\n"
        "Правила: отвечай по-русски, кратко и точно; опирайся на инструменты, а не на догадки; если не "
        "хватает данных для действия (название/папка проекта, какой шаблон) — не угадывай, спроси у "
        "пользователя через ask_user с вариантами."
    ),
    Lang.en: (
        "You are the AI assistant of a local tool for preparing academic documents. "
        "Right now you are working OUTSIDE a specific "
        "project — as a general application assistant. What you help with: create projects "
        "(create_project) from templates (look at list_templates first), show existing projects "
        "(list_projects), change app settings — the colour theme (set_theme) and the build engine "
        "(set_engine).\n"
        "Rules: reply in English, briefly and precisely; rely on tools rather than guesswork; if "
        "you lack the data to act (project name/folder, which template) — don't guess, ask the "
        "user via ask_user with options."
    ),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fallback_title(text: str) -> str:
    clean = " ".join(text.strip().split())
    if not clean:
        return "Новый чат"
    if len(clean) <= _TITLE_MAX_CHARS:
        return clean.rstrip(" .!?;:")
    return clean[: _TITLE_MAX_CHARS - 1].rstrip(" .,;:-") + "…"


@dataclass
class SystemStartChatTurnInput:
    session_id: UUID
    text: str = ""
    provider_id: UUID | None = None
    model: str | None = None
    run_id: UUID | None = None
    approved_call_ids: tuple[str, ...] = ()
    tool_answers: dict[str, dict[str, str]] = field(default_factory=dict)


@dataclass
class SystemStartChatTurnOutput:
    run_id: UUID
    user_message_seq: int


class SystemStartChatTurnUC:
    """System-scope twin of StartChatTurnUC: runs one agent turn against the fixed
    app-level folder with the system tool registry and a project-less prompt."""

    def __init__(
        self,
        folder: Path,
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
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        agent_persona_repo: IAgentPersonaRepository,
    ) -> None:
        self._folder = folder
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
        self._project_repo = project_repo
        self._project_index_repo = project_index_repo

    def _resolve_project(self, project_id: UUID | None) -> Project | None:
        if project_id is None:
            return None
        folder = find_project_folder(project_id, self._project_repo, self._project_index_repo)
        return self._project_repo.get(folder) if folder is not None else None

    def _enabled_tools(self) -> frozenset[str] | None:
        # null/missing → all tools; a stored list restricts the agent's catalog
        # (shared with the project turn via the same settings key).
        stored = self._settings_repo.get().get(_ENABLED_TOOLS_KEY)
        if isinstance(stored, list):
            return frozenset(str(name) for name in stored)
        return None

    async def execute(self, inp: SystemStartChatTurnInput) -> SystemStartChatTurnOutput:
        session = self._chat_repo.get_session(self._folder, inp.session_id)
        if session is None:
            raise NotFoundError(
                localized_error(
                    f"Сессия чата {inp.session_id!r} не найдена", f"Chat session {inp.session_id!r} not found"
                )
            )
        if self._run_manager.active_run_for_session(inp.session_id) is not None:
            raise PermissionError("a turn is already running in this chat")
        if inp.run_id is not None:
            return self._resume(inp)
        return self._start_new(inp, session)

    def _start_new(self, inp: SystemStartChatTurnInput, session: ChatSession) -> SystemStartChatTurnOutput:
        provider, model = self._resolve_provider(inp.provider_id, inp.model, session)
        now = _now()
        if session.message_count == 0 and session.title.strip() in _DEFAULT_TITLES and inp.text.strip():
            session.title = _fallback_title(inp.text)
            session.updated_at = now
            self._chat_repo.save_session(session)
        user_message = ChatMessage(
            id=uuid4(),
            session_id=inp.session_id,
            run_id=None,
            seq=-1,
            role=ChatMessageRole.user,
            blocks=[ChatContentBlock(kind=ChatContentKind.text, text=inp.text)],
            created_at=now,
        )
        user_seq = self._chat_repo.append_message(self._folder, user_message)
        run = AgentRunRecord(
            id=uuid4(),
            session_id=inp.session_id,
            project_folder=self._folder,
            status=AgentRunStatus.pending,
            created_at=now,
            started_at=None,
            finished_at=None,
            trigger_seq=user_seq,
            model=model,
            provider_id=provider.id,
        )
        self._chat_repo.save_run(run)
        self._spawn(run, provider, model, (), {})
        return SystemStartChatTurnOutput(run_id=run.id, user_message_seq=user_seq)

    def _resume(self, inp: SystemStartChatTurnInput) -> SystemStartChatTurnOutput:
        run = self._chat_repo.get_run(self._folder, inp.run_id) if inp.run_id else None
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
        self._bus.discard(run.id)
        self._spawn(run, provider, run.model or "", inp.approved_call_ids, inp.tool_answers)
        return SystemStartChatTurnOutput(run_id=run.id, user_message_seq=run.trigger_seq)

    def _resolve_provider(
        self, provider_id: UUID | None, model: str | None, session: ChatSession
    ) -> tuple[AIProvider, str]:
        pid = provider_id or session.default_provider_id
        mdl = model or session.default_model
        if pid is None or not mdl:
            stored = self._settings_repo.get()
            if pid is None and stored.get("default_ai_provider_id"):
                pid = UUID(str(stored["default_ai_provider_id"]))
            if not mdl:
                mdl = stored.get("default_ai_model")
        if pid is None:
            raise ValueError(
                localized_error(
                    "AI-провайдер не выбран: настройте провайдера по умолчанию в настройках",
                    "No AI provider selected: configure a default provider in settings",
                )
            )
        provider = self._ai_provider_repo.get(pid)
        if provider is None:
            raise NotFoundError(localized_error(f"AI-провайдер {pid!r} не найден", f"AI provider {pid!r} not found"))
        if not mdl:
            raise ValueError(
                localized_error(
                    "модель не выбрана: выберите модель по умолчанию в настройках",
                    "No model selected: choose a default model in settings",
                )
            )
        return provider, mdl

    def _spawn(
        self,
        run: AgentRunRecord,
        provider: AIProvider,
        model: str,
        approved_call_ids: tuple[str, ...],
        tool_answers: dict[str, dict[str, str]],
    ) -> None:
        cancel = asyncio.Event()
        task = asyncio.create_task(self._run_turn_task(run, provider, model, cancel, approved_call_ids, tool_answers))
        self._run_manager.register(run.id, task, run.session_id, run.project_folder)

    async def _run_turn_task(
        self,
        run: AgentRunRecord,
        provider: AIProvider,
        model: str,
        cancel: asyncio.Event,
        approved_call_ids: tuple[str, ...],
        tool_answers: dict[str, dict[str, str]],
    ) -> None:
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
        # The chat is bound to a project iff its session carries project_id; then
        # the agent gets project tools + a project-aware prompt. Otherwise it runs
        # in system scope (app/system tools only). The transcript always lives in
        # self._folder; project tools resolve the project from its id themselves.
        # Interface (conversation) language: the request header (inherited by this
        # background task) wins; fall back to persisted settings, then ru. Re-set
        # it so deeper code (e.g. the chat summarizer) reads the resolved value.
        language = current_interface_language(self._settings_repo.get().get(_INTERFACE_LANGUAGE_KEY))
        set_interface_language(language.value)
        session = self._chat_repo.get_session(self._folder, run.session_id)
        persona_id = session.persona if session else None
        persona_instructions = session.persona_instructions if session else None
        custom_personas = {str(p.id): p.instruction for p in self._agent_persona_repo.list_all()}
        project = self._resolve_project(session.project_id if session else None)
        if project is not None:
            system = build_system_prompt(
                project,
                select_edit_format(provider.type, model),
                rules=None,
                persona_id=persona_id,
                persona_instructions=persona_instructions,
                custom_personas=custom_personas,
                language=language,
            )
            loop_project_id: UUID | None = project.id
        else:
            system = apply_persona(
                _SYSTEM_PROMPT[language], persona_id, persona_instructions, custom_personas, language=language
            )
            loop_project_id = None
        try:
            run.status = AgentRunStatus.running
            run.started_at = _now()
            self._chat_repo.save_run(run)
            result = await loop.run(
                project_id=loop_project_id,
                project_folder=self._folder,
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
            logger.warning("system agent run failed", run_id=str(run.id), error_type=type(exc).__name__)
            run.status = AgentRunStatus.failed
            run.error = type(exc).__name__
        finally:
            if run.status != AgentRunStatus.awaiting_approval:
                run.finished_at = _now()
            run.diagnostics = [*run.diagnostics, *loop.diagnostics][-_MAX_RUN_DIAGNOSTICS:]
            self._chat_repo.save_run(run)
            self._bus.close(run.id)
            self._run_manager.unregister(run.id)
        if cancelled:
            raise asyncio.CancelledError

    @staticmethod
    def _apply_result(run: AgentRunRecord, result: LoopResult) -> None:
        run.status = result.status
        run.iterations = result.iterations
        run.usage = result.usage
        if result.error:
            run.error = result.error
        if result.last_seq is not None:
            run.last_emitted_seq = result.last_seq
