"""Тулы аккаунта и проектов, которых нет у встроенного агента."""

from __future__ import annotations

from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.enums import ToolKind
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.use_cases.mcp.tools._base import McpTool, json_result, project_schema, text_arg
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC
from hse_doc_studio.use_cases.projects.get_project_access import GetProjectAccessInput, GetProjectAccessUC
from hse_doc_studio.use_cases.projects.unregister_project import UnregisterProjectInput, UnregisterProjectUC


class WhoamiTool(McpTool):
    spec = ToolSpec(
        name="whoami",
        description="Кто подключён: пользователь Студии, от имени которого выполняются инструменты, и его права.",
        parameters={"type": "object", "properties": {}},
    )
    kind = ToolKind.read
    requires_project = False

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        actor = require_actor()
        return json_result(
            {
                "kind": actor.kind,
                "id": actor.id,
                "name": actor.name,
                "email": actor.email,
                "is_instance_admin": actor.is_instance_admin,
                "source": actor.source,
                "scopes": sorted(actor.scopes),
            }
        )


class GetProjectTool(McpTool):
    spec = ToolSpec(
        name="get_project",
        description=(
            "Карточка проекта: название, вид, язык, авторы, руководитель, документы, моя роль и можно ли писать "
            "в проект."
        ),
        parameters=project_schema({}),
    )
    kind = ToolKind.read

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        found = await (await self._deps.get(GetProjectUC)).execute(GetProjectInput(project_id=ctx.project_id))
        access = await (await self._deps.get(GetProjectAccessUC)).execute(
            GetProjectAccessInput(project_id=ctx.project_id)
        )
        project = found.project
        membership = found.membership
        return json_result(
            {
                "id": project.id,
                "name": project.name,
                "kind": project.kind,
                "staffing": project.staffing,
                "lang": project.lang,
                "authors": project.authors,
                "supervisor": project.supervisor,
                "co_supervisor": project.co_supervisor,
                "meta": project.meta,
                "documents": [
                    {"id": d.id, "status": d.status, "last_compile_id": d.last_compile_id} for d in project.documents
                ],
                "archived": project.archived,
                "updated_at": project.updated_at,
                "my_role": membership.my_role if membership is not None else None,
                "writable": access.access.writable,
                "access_mode": access.access.mode,
            }
        )


class DeleteProjectTool(McpTool):
    spec = ToolSpec(
        name="delete_project",
        description=(
            "Удалить проект (убрать из Студии). Опасно: действие необратимо из интерфейса. Передай confirm "
            "с точным названием проекта."
        ),
        parameters=project_schema(
            {"confirm": {"type": "string", "description": "Точное название проекта для подтверждения"}},
            ("confirm",),
        ),
    )
    kind = ToolKind.exec_

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        confirm = text_arg(args, "confirm")
        project = (
            await (await self._deps.get(GetProjectUC)).execute(GetProjectInput(project_id=ctx.project_id))
        ).project
        if confirm != project.name.strip():
            return ToolResult.error(
                localized_error(
                    "confirm не совпадает с названием проекта: удаление отменено",
                    "confirm does not match the project name: nothing was deleted",
                )
            )
        await (await self._deps.get(UnregisterProjectUC)).execute(UnregisterProjectInput(project_id=ctx.project_id))
        return ToolResult.ok(localized_error(f"Проект «{project.name}» удалён.", f"Project “{project.name}” deleted."))
