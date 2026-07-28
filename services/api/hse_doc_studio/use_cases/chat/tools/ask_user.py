from __future__ import annotations

from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.agent.tools import ToolDefinition
from hse_doc_studio.core.enums import Lang, ToolKind
from hse_doc_studio.core.i18n import current_interface_language

_SPEC = ToolSpec(
    name="ask_user",
    description=(
        "Задать пользователю уточняющие вопросы с вариантами ответа и дождаться выбора, "
        "прежде чем продолжать. Используй, когда не хватает информации для уверенного действия "
        "(какой документ/профиль/подход выбрать и т.п.). Можно задать сразу несколько вопросов. "
        "У пользователя всегда есть вариант «Другое» со своим вводом, его добавлять не нужно. "
        "После ответа ты получишь выбор пользователя и продолжишь."
    ),
    parameters={
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "description": "Список вопросов (1–4).",
                "items": {
                    "type": "object",
                    "properties": {
                        "header": {
                            "type": "string",
                            "description": "Короткая метка-заголовок (до ~12 симв.), напр. «Профиль».",
                        },
                        "question": {"type": "string", "description": "Полный текст вопроса."},
                        "multiSelect": {
                            "type": "boolean",
                            "description": "true — можно выбрать несколько вариантов.",
                        },
                        "options": {
                            "type": "array",
                            "description": "Варианты ответа (2–4).",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "label": {"type": "string"},
                                    "description": {"type": "string"},
                                },
                                "required": ["label"],
                            },
                        },
                    },
                    "required": ["question", "options"],
                },
            }
        },
        "required": ["questions"],
    },
)


class AskUserTool:
    """Interactive: the agent loop intercepts this call, surfaces the questions
    to the UI, and feeds the user's answers back as the tool result. The handler
    is a defensive fallback only — it should never actually run."""

    def definition(self) -> ToolDefinition:
        return ToolDefinition(spec=_SPEC, kind=ToolKind.ask, handler=self, weak_model_safe=True, requires_project=False)

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        lang = current_interface_language()
        return ToolResult.error(
            "ask_user is handled by the interface; direct invocation is not supported"
            if lang == Lang.en
            else "ask_user обрабатывается интерфейсом, прямой вызов не поддерживается"
        )
