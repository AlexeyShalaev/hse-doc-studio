"""Админские тулы (только сервер, группа admin). Права админа проверяют сами сценарии (`require_admin`)."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import UUID

from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.enums import ToolKind
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.identity.entities import AuditQuery, User, UserQuery
from hse_doc_studio.core.listing import Window
from hse_doc_studio.core.mail.journal import TEMPLATE_MAX, MailLogQuery, MailStatus
from hse_doc_studio.use_cases.admin.audit import ListAuditUC
from hse_doc_studio.use_cases.admin.ops_queue import CancelJobUC, QueueSummaryUC
from hse_doc_studio.use_cases.admin.ops_runners import RunnerSummaryUC
from hse_doc_studio.use_cases.admin.users import DisableUserUC, EnableUserUC, ListUsersUC
from hse_doc_studio.use_cases.mail.log import ListMailLogUC, MailLogView
from hse_doc_studio.use_cases.mcp.tools._base import (
    ArgumentError,
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


# Журнал писем через MCP короче, чем в админке (docs/design/mail-log.md, 6.4): без курсора и превью.
MAIL_LOG_LIMIT = 50
_MAIL_LOG_DEFAULT = 20
_TEMPLATE = re.compile(rf"^[a-z_]{{1,{TEMPLATE_MAX}}}$")
# Адрес почты не длиннее 320 символов (RFC 5321), как у фильтра `recipient` в API.
_RECIPIENT_MAX = 320


def _bad(ru: str, en: str) -> ArgumentError:
    return ArgumentError(localized_error(ru, en))


def _mail_status(args: dict[str, object]) -> tuple[MailStatus, ...]:
    raw = optional_text(args, "status")
    if raw is None:
        return ()
    try:
        return (MailStatus(raw),)
    except ValueError:
        allowed = ", ".join(MailStatus)
        raise _bad(f"status: одно из {allowed}", f"status: one of {allowed}") from None


def _mail_template(args: dict[str, object]) -> tuple[str, ...]:
    raw = optional_text(args, "template")
    if raw is None:
        return ()
    if not _TEMPLATE.fullmatch(raw):
        raise _bad("template: вид письма вроде invite", "template: a mail kind such as invite")
    return (raw,)


def _mail_recipient(args: dict[str, object]) -> str | None:
    raw = optional_text(args, "recipient")
    if raw is not None and len(raw) > _RECIPIENT_MAX:
        raise _bad("recipient: слишком длинный адрес", "recipient: the address is too long")
    return raw


def _since(args: dict[str, object]) -> datetime | None:
    """Начало периода в ISO 8601; без часового пояса считается UTC, дата без времени это полночь."""
    raw = optional_text(args, "since")
    if raw is None:
        return None
    try:
        at = datetime.fromisoformat(raw)
    except ValueError:
        raise _bad(
            f"since: ожидается дата ISO 8601, получено {raw!r}", f"since: an ISO 8601 date is expected, got {raw!r}"
        ) from None
    return at if at.tzinfo is not None else at.replace(tzinfo=UTC)


def _mail_row(view: MailLogView) -> dict[str, object]:
    """Сведения строки без имён, превью, ссылок и текста сбоя: люди и проект только id (L18)."""
    entry = view.entry
    return {
        "id": entry.id,
        "at": entry.at,
        "template": entry.template,
        "to": entry.to_email,
        "to_user_id": entry.to_user_id,
        "subject": entry.subject,
        "status": entry.status,
        "reason": entry.reason,
        "smtp_code": entry.smtp_code,
        "cause": entry.cause,
        "actor_id": entry.actor_user_id,
        "project_id": entry.project_id,
        # Версия 2 (mail-log.md, V15): сколько попыток было, ждёт ли письмо автоповтора, ручной повтор чего.
        "attempts": entry.attempts,
        "next_attempt_at": entry.next_attempt_at,
        "last_attempt_at": entry.last_attempt_at,
        "resent_from_id": entry.resent_from_id,
    }


class AdminListMailLogTool(_AdminTool):
    spec = ToolSpec(
        name="admin_list_mail_log",
        description=(
            "Админ: журнал писем установки, новые первыми. Фильтры: recipient (точный адрес без учёта регистра), "
            "template (вид письма), status (sent, failed, not_sent, suppressed), since (ISO 8601). "
            "Строка: время, вид, получатель, тема, итог, причина, код SMTP, кто вызвал (cause и actor_id), "
            "попытки (attempts), следующий автоповтор (next_attempt_at, null: повторов больше не будет), "
            "время последней попытки и resent_from_id у ручного повтора."
        ),
        parameters={
            "type": "object",
            "properties": {
                "recipient": {"type": "string", "description": "Адрес получателя, точное совпадение"},
                "template": {"type": "string", "description": "Вид письма, например invite"},
                "status": {"type": "string", "enum": [s.value for s in MailStatus]},
                "since": {"type": "string", "description": "Не раньше этого момента, ISO 8601"},
                "limit": {"type": "integer", "default": _MAIL_LOG_DEFAULT, "maximum": MAIL_LOG_LIMIT},
            },
        },
    )
    kind = ToolKind.read

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        query = MailLogQuery(
            templates=_mail_template(args),
            statuses=_mail_status(args),
            recipient=_mail_recipient(args),
            since=_since(args),
            limit=int_arg(args, "limit", _MAIL_LOG_DEFAULT, lo=1, hi=MAIL_LOG_LIMIT),
        )
        page = await (await self._deps.get(ListMailLogUC)).execute(require_actor(), query)
        return json_result([_mail_row(view) for view in page.items])


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
