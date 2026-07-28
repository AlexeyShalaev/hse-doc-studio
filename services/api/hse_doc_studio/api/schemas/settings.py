from __future__ import annotations

from pydantic import BaseModel


class SettingsResponse(BaseModel):
    theme: str
    # Interface (UI) language {"ru", "en"} — independent from document language.
    interface_language: str
    default_engine: str
    latex_passes: int
    # Максимум одновременных docker-сборок; лишние ждут в очереди.
    max_concurrent_compiles: int
    latex_flags: str | None
    compile_image: str | None
    default_ai_provider_id: str | None
    default_ai_model: str | None
    agent_auto_approve_writes: bool
    # null = all tools available; a list restricts the agent's tool catalog.
    agent_enabled_tools: list[str] | None
    # Sticky default agent role new chats inherit.
    default_agent_persona: str | None
    default_agent_persona_instructions: str | None
    # Ставить вышедшие обновления самостоятельно; по умолчанию включено.
    auto_update: bool
    # Порог (ГБ) освобождаемого места для стартового предупреждения; 0 = выкл.
    disk_usage_warn_gb: int


class UpdateSettingsRequest(BaseModel):
    theme: str | None = None
    interface_language: str | None = None
    default_engine: str | None = None
    latex_passes: int | None = None
    max_concurrent_compiles: int | None = None
    latex_flags: str | None = None
    compile_image: str | None = None
    default_ai_provider_id: str | None = None
    default_ai_model: str | None = None
    agent_auto_approve_writes: bool | None = None
    agent_enabled_tools: list[str] | None = None
    default_agent_persona: str | None = None
    default_agent_persona_instructions: str | None = None
    auto_update: bool | None = None
    disk_usage_warn_gb: int | None = None
