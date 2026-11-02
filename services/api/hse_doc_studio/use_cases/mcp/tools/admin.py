"""Админские тулы (только сервер, группа admin). Права админа проверяют сами сценарии (`require_admin`)."""

from __future__ import annotations

from uuid import UUID

from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.enums import ToolKind
from hse_doc_studio.core.identity.entities import AuditQuery, User, UserQuery
from hse_doc_studio.core.listing import Window
from hse_doc_studio.use_cases.admin.audit import ListAuditUC
from hse_doc_studio.use_cases.admin.ops_queue import CancelJobUC, QueueSummaryUC
from hse_doc_studio.use_cases.admin.ops_runners import RunnerSummaryUC
from hse_doc_studio.use_cases.admin.users import DisableUserUC, EnableUserUC, ListUsersUC
from hse_doc_studio.use_cases.mcp.tools._base import (
    McpTool,
    int_arg,
    json_result,
    optional_text,
    text_arg,
    uuid_arg,
)

_USER_ID = {"type": "object", "properties": {"user_id": {"type": "string"}}, "required": ["user_id"]}


def _user(user: User) -> dict[str, object]:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "status": user.status,
        "is_instance_admin": user.is_instance_admin,
        "created_at": user.created_at,
        "last_login_at": user.last_login_at,
    }


class _AdminTool(McpTool):
    requires_project = False


class AdminListUsersTool(_AdminTool):
    spec = ToolSpec(
        name="admin_list_users",
        description="Админ: пользователи установки с поиском q (имя или почта).",
        parameters={
            "type": "object",
            "properties": {"q": {"type": "string"}, "limit": {"type": "integer", "default": 50}},
        },
    )
    kind = ToolKind.read

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        query = UserQuery(q=optional_text(args, "q"), window=Window(limit=int_arg(args, "limit", 50, lo=1, hi=200)))
        found = await (await self._deps.get(ListUsersUC)).execute(require_actor(), query)
        return json_result(
            {
                "total": found.total,
                "items": [{**_user(i.user), "project_count": i.project_count} for i in found.items],
            }
        )


class AdminQueueSummaryTool(_AdminTool):
    spec = ToolSpec(
        name="admin_queue_summary",
        description="Админ: сводка очереди задач (сколько ждёт, выполняется, упало).",
        parameters={"type": "object", "properties": {}},
    )
    kind = ToolKind.read

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        return json_result(await (await self._deps.get(QueueSummaryUC)).execute(require_actor()))


class AdminRunnerSummaryTool(_AdminTool):
    spec = ToolSpec(
        name="admin_runner_summary",
        description="Админ: сводка раннеров сборки (в сети, заняты, устарели).",
        parameters={"type": "object", "properties": {}},
    )
    kind = ToolKind.read

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        return json_result(await (await self._deps.get(RunnerSummaryUC)).execute(require_actor()))


class AdminListAuditTool(_AdminTool):
    spec = ToolSpec(
        name="admin_list_audit",
        description="Админ: журнал аудита, новые события первыми. category (префикс действия, напр. mcp) и q.",
        parameters={
            "type": "object",
            "properties": {
                "category": {"type": "string"},
                "q": {"type": "string"},
                "limit": {"type": "integer", "default": 50},
            },
        },
    )
    kind = ToolKind.read

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        category = optional_text(args, "category")
        page = await (await self._deps.get(ListAuditUC)).execute(
            require_actor(),
            AuditQuery(
                categories=(category,) if category else (),
                q=optional_text(args, "q"),
                limit=int_arg(args, "limit", 50, lo=1, hi=200),
            ),
        )
        return json_result(
            [
                {
                    "at": v.entry.at,
                    "action": v.entry.action,
                    "actor": v.actor,
                    "target": v.target_label or v.entry.target,
                    "details": v.entry.details,
                }
                for v in page.items
            ]
        )


class AdminDisableUserTool(_AdminTool):
    spec = ToolSpec(
        name="admin_disable_user",
        description="Админ: заблокировать пользователя (его сессии и токены перестают действовать).",
        parameters=_USER_ID,
    )
    kind = ToolKind.write

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        user = await (await self._deps.get(DisableUserUC)).execute(require_actor(), text_arg(args, "user_id"))
        return json_result(_user(user))


class AdminEnableUserTool(_AdminTool):
    spec = ToolSpec(name="admin_enable_user", description="Админ: разблокировать пользователя.", parameters=_USER_ID)
    kind = ToolKind.write

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        user = await (await self._deps.get(EnableUserUC)).execute(require_actor(), text_arg(args, "user_id"))
        return json_result(_user(user))


class AdminCancelJobTool(_AdminTool):
    spec = ToolSpec(
        name="admin_cancel_job",
        description="Админ: отменить задачу очереди (сборку, конвертацию) по её id.",
        parameters={"type": "object", "properties": {"job_id": {"type": "string"}}, "required": ["job_id"]},
    )
    kind = ToolKind.exec_

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        job_id: UUID = uuid_arg(args, "job_id")
        return json_result(await (await self._deps.get(CancelJobUC)).execute(require_actor(), job_id))
