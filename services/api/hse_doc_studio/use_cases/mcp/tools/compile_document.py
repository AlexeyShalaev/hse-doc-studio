"""Сборка документа для клиента MCP: тот же запуск, что у агента и кнопки «Собрать», но без долгого ожидания.

Клиент MCP обрывает вызов по своему таймауту (60 с по умолчанию в SDK, 75 с у ingress облака), а облачная
сборка на личном раннере идёт и дольше. Поэтому тул ждёт итог не дольше `COMPILE_WAIT_S`, а дальше отвечает
compile_id и `status: in_progress`; при `wait=false` отвечает сразу. Итог читается через get_compile.
"""

from __future__ import annotations

from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.enums import ToolKind
from hse_doc_studio.use_cases.chat._registry import ToolRegistry
from hse_doc_studio.use_cases.chat.tools.compile_document import CompileDocumentTool as AgentCompileDocumentTool
from hse_doc_studio.use_cases.mcp.tools._base import McpTool, bool_arg, project_schema

COMPILE_WAIT_S = 45


class CompileDocumentTool(McpTool):
    spec = ToolSpec(
        name="compile_document",
        description=(
            f"Собрать PDF документа, как кнопка «Собрать». Перед вызовом сохрани правки (edit_tex, write_file). "
            f"wait=true ждёт итог до {COMPILE_WAIT_S} с: статус, страницы, замечания, хвост лога при ошибке; если "
            f"сборка идёт дольше, ответ status: in_progress и compile_id. wait=false сразу возвращает compile_id. "
            f"Итог такой сборки смотри через get_compile. Пример: "
            '{"doc_id": "vkr", "wait": false}.'
        ),
        parameters=project_schema(
            {
                "doc_id": {"type": "string", "description": "Идентификатор документа, напр. vkr"},
                "wait": {
                    "type": "boolean",
                    "default": True,
                    "description": f"Ждать итог до {COMPILE_WAIT_S} с (true) или сразу вернуть compile_id (false)",
                },
            },
            ("doc_id",),
        ),
    )
    kind = ToolKind.exec_

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        definition = (await self._deps.get(ToolRegistry)).get("compile_document")
        agent_tool = definition.handler if definition is not None else None
        if not isinstance(agent_tool, AgentCompileDocumentTool):
            raise TypeError("compile_document")
        call_args = {**args, "wait": bool_arg(args, "wait", True)}
        return await agent_tool.with_wait_limit(COMPILE_WAIT_S).handle(ctx, call_args)
