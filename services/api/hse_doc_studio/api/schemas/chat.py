from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class TokenUsageResponse(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int


class ChatContentBlockResponse(BaseModel):
    kind: str
    text: str | None = None
    call_id: str | None = None
    tool_name: str | None = None
    args: dict[str, Any] = Field(default_factory=dict)
    result: str | None = None
    is_error: bool = False


class ChatMessageResponse(BaseModel):
    id: UUID
    seq: int
    role: str
    blocks: list[ChatContentBlockResponse]
    created_at: datetime
    model: str | None = None
    provider_id: UUID | None = None
    usage: TokenUsageResponse | None = None
    approval: str


class ChatSessionResponse(BaseModel):
    id: UUID
    title: str
    doc_id: str | None
    # The project this chat is bound to (None = global/system chat). Surfaced so
    # the UI can route a project-scoped queued prompt to a matching chat.
    project_id: UUID | None = None
    created_at: datetime
    updated_at: datetime
    archived: bool
    message_count: int
    last_run_id: UUID | None
    default_provider_id: UUID | None
    default_model: str | None
    # The agent role for this chat: persona id (or None) + free-form text for "custom".
    persona: str | None = None
    persona_instructions: str | None = None
    # True when this session has an in-flight agent run right now (live across
    # the session list, so parallel agent activity is visible).
    is_running: bool = False


class ChatSessionDetailResponse(ChatSessionResponse):
    messages: list[ChatMessageResponse]
    active_run_id: UUID | None


class CreateChatSessionRequest(BaseModel):
    title: str | None = None
    doc_id: str | None = None
    provider_id: UUID | None = None
    model: str | None = None
    # Unified agent: bind a chat to a project so it gets project tools + context.
    # None = a global/system chat (app/system tools only).
    project_id: UUID | None = None
    # Agent role: persona id + free-form text (when persona == "custom").
    persona: str | None = None
    persona_instructions: str | None = None


class RenameChatSessionRequest(BaseModel):
    # Partial session update: only the provided fields change.
    title: str | None = None
    persona: str | None = None
    persona_instructions: str | None = None


class PersonaResponse(BaseModel):
    id: str
    label: str
    description: str
    # False = a user-defined custom role (vs. a shipped built-in).
    builtin: bool = True


class StartTurnRequest(BaseModel):
    text: str
    # Optional per-turn overrides; otherwise the session default, then the global
    # default_ai_provider_id / default_ai_model from settings are used.
    provider_id: UUID | None = None
    model: str | None = None


class StartTurnResponse(BaseModel):
    run_id: UUID
    user_message_seq: int


class ApproveTurnRequest(BaseModel):
    # The tool-call ids the user approved; the paused run resumes and executes them.
    call_ids: list[str]


class AnswerTurnRequest(BaseModel):
    # ask_user answers keyed by tool-call id; each a map of question → chosen
    # answer text. Resumes a question-paused run.
    answers: dict[str, dict[str, str]]


class CancelTurnResponse(BaseModel):
    cancelled_task: bool
    record_finalized: bool


class AgentToolResponse(BaseModel):
    name: str
    description: str
    kind: str  # read | write | exec
    requires_project: bool = True
