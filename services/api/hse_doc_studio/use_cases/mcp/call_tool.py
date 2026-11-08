"""Вызов тула MCP: включён ли MCP и тул, права на проект, запись в проект, лимит частоты, журнал.

Порядок проверок как у `/api/v1`: сначала права (чужой проект неотличим от несуществующего), потом запрет записи,
потом лимит. Обработчик вызывает те же сценарии, что маршруты; их отказы превращаются в коды `McpErrorCode`.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import structlog

from hse_doc_studio.core.access.checker import IProjectAccessChecker, ProjectForbiddenError
from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.access.paths import scope_path_of_instance_id
from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult
from hse_doc_studio.core.enums import EditFormat
from hse_doc_studio.core.errors import NotFoundError, ProjectReadOnlyError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.mcp.entities import MCP_ADMIN_SCOPE, McpCallOutcome, McpCallRecord, McpSettings
from hse_doc_studio.core.mcp.errors import McpError, McpErrorCode
from hse_doc_studio.core.mcp.protocols import IMcpCallJournal, IMcpSettingsStore
from hse_doc_studio.core.project_access import access_message
from hse_doc_studio.core.projects.usage import ProjectQuotaExceededError
from hse_doc_studio.core.quotas.errors import QuotaExceededError
from hse_doc_studio.core.rate_limit import MCP_CALL, IRateLimiter, RateRule
from hse_doc_studio.core.shutdown import ServerRestartingError
from hse_doc_studio.use_cases.mcp.catalog import McpCatalog, McpToolEntry
from hse_doc_studio.use_cases.mcp.tools._base import ArgumentError
from hse_doc_studio.use_cases.projects.get_project_access import GetProjectAccessInput, GetProjectAccessUC

logger = structlog.get_logger(__name__)

# Имя модели в контексте тула: клиент MCP внешний, его модель Студии неизвестна.
MCP_MODEL = "mcp-client"


@dataclass(frozen=True)
class McpCallResult:
    result: ToolResult
    error_code: McpErrorCode | None = None
    retry_after_s: int | None = None


def visible_to(actor: Actor, entry: McpToolEntry, settings: McpSettings) -> bool:
    """Тул виден и вызываем: включён в настройках, а админский ещё и у админа с областью `mcp:admin`."""
    if not settings.allows(entry.meta):
        return False
    if entry.meta.admin:
        return actor.is_instance_admin and (actor.scopes == frozenset() or MCP_ADMIN_SCOPE in actor.scopes)
    return True


class CallMcpToolUC:
    def __init__(  # noqa: PLR0913 — порты вызова перечислены явно
        self,
        catalog: McpCatalog,
        settings: IMcpSettingsStore,
        journal: IMcpCallJournal,
        access: IProjectAccessChecker,
        project_access: GetProjectAccessUC,
    ) -> None:
        self._catalog = catalog
        self._settings = settings
        self._journal = journal
        self._access = access
        self._project_access = project_access

    async def execute(
        self,
        name: str,
        args: Mapping[str, object],
        *,
        client: str | None = None,
        limiter: IRateLimiter | None = None,
    ) -> McpCallResult:
        """`limiter` тот же ограничитель, что у `/api/v1` (живёт в приложении, а не в контейнере)."""
        actor = require_actor()
        started = time.monotonic()
        project_id: UUID | None = None
        try:
            entry = await self._entry(actor, name)
            project_id = self._project_id(entry, args)
            await self._authorize(entry, project_id, args)
            await self._rate(actor, entry, limiter)
            result = await self._run(entry, project_id, dict(args))
            outcome = McpCallResult(result=result, error_code=McpErrorCode.failed if result.is_error else None)
        except McpError as exc:
            outcome = McpCallResult(ToolResult.error(str(exc)), exc.code, exc.retry_after_s)
        await self._record(actor, name, args, project_id, outcome, started, client)
        return outcome

    async def _entry(self, actor: Actor, name: str) -> McpToolEntry:
        settings = await self._settings.get()
        if not settings.enabled:
            raise McpError(McpErrorCode.mcp_disabled)
        entry = self._catalog.get(name)
        if entry is None:
            raise McpError(McpErrorCode.unknown_tool)
        if not visible_to(actor, entry, settings):
            raise McpError(McpErrorCode.tool_disabled)
        return entry

    @staticmethod
    def _project_id(entry: McpToolEntry, args: Mapping[str, object]) -> UUID | None:
        if not entry.rule.needs_project:
            return None
        raw = args.get("project_id")
        try:
            return UUID(str(raw).strip())
        except ValueError:
            raise McpError(
                McpErrorCode.invalid_arguments,
                localized_error("укажите project_id (UUID проекта)", "specify project_id (the project UUID)"),
            ) from None

    async def _authorize(self, entry: McpToolEntry, project_id: UUID | None, args: Mapping[str, object]) -> None:
        action = entry.rule.action
        if action is None or project_id is None:
            return
        try:
            paths: list[str | None] = [str(args.get(key, "")).strip() for key in entry.rule.path_args]
            # Id экземпляра сводится к слагу автора, как `scope_for_rule` у маршрута; без автора области нет.
            paths += [scope_path_of_instance_id(str(args.get(key, "")).strip()) for key in entry.rule.instance_args]
            for path in paths or [None]:
                await self._access.require(project_id, action, path)
            if entry.rule.guards_write:
                found = await self._project_access.execute(GetProjectAccessInput(project_id=project_id))
                if not found.access.writable:
                    # Причина та же, что в ответе 423: агенту тоже нельзя советовать «обновите Студию» зря.
                    raise McpError(McpErrorCode.read_only, access_message(found.access, found.project.lock.version))
        except (NotFoundError, ProjectForbiddenError, ProjectReadOnlyError) as exc:
            raise map_tool_error(exc) from exc

    @staticmethod
    async def _rate(actor: Actor, entry: McpToolEntry, limiter: IRateLimiter | None) -> None:
        if limiter is None or actor.id is None:
            return
        rules: list[RateRule] = [MCP_CALL]
        if entry.rule.rate is not None:
            rules.append(entry.rule.rate)
        for rule in rules:
            decision = await limiter.hit(rule, f"user:{actor.id}")
            if not decision.allowed:
                raise McpError(McpErrorCode.rate_limited, retry_after_s=decision.retry_after_s)

    async def _run(self, entry: McpToolEntry, project_id: UUID | None, args: dict[str, object]) -> ToolResult:
        args.pop("project_id", None)
        ctx = AgentToolContext(
            project_id=project_id or UUID(int=0), model=MCP_MODEL, edit_format=EditFormat.search_replace
        )
        try:
            return await entry.definition.handler.handle(ctx, args)
        except McpError:
            raise
        except Exception as exc:  # noqa: BLE001 — любой отказ сценария становится ответом тула, не 500
            raise map_tool_error(exc) from exc

    async def _record(  # noqa: PLR0913 — поля записи журнала
        self,
        actor: Actor,
        name: str,
        args: Mapping[str, object],
        project_id: UUID | None,
        outcome: McpCallResult,
        started: float,
        client: str | None,
    ) -> None:
        code = outcome.error_code
        denied = code in {
            McpErrorCode.forbidden,
            McpErrorCode.tool_disabled,
            McpErrorCode.mcp_disabled,
            McpErrorCode.rate_limited,
        }
        record = McpCallRecord(
            at=datetime.now(UTC),
            tool=name[:128],
            outcome=McpCallOutcome.denied if denied else McpCallOutcome.error if code else McpCallOutcome.ok,
            duration_ms=int((time.monotonic() - started) * 1000),
            actor_id=actor.id,
            actor_name=actor.name,
            project_id=str(project_id) if project_id else None,
            error_code=code.value if code else None,
            client=client[:128] if client else None,
            arg_keys=tuple(sorted(str(k)[:64] for k in args)[:32]),
        )
        try:
            await self._journal.record(record)
        except Exception:
            logger.exception("mcp_journal_failed", tool=name)


def map_tool_error(exc: Exception) -> McpError:  # noqa: C901, PLR0911 — таблица соответствий
    """Отказ сценария в код MCP; текст сценария сохраняется, где он уже понятен человеку."""
    if isinstance(exc, McpError):
        return exc
    if isinstance(exc, ServerRestartingError):
        return McpError(McpErrorCode.server_restarting, str(exc), retry_after_s=exc.retry_after_s)
    if isinstance(exc, NotFoundError | FileNotFoundError):
        return McpError(McpErrorCode.not_found)
    if isinstance(exc, ProjectForbiddenError):
        role = exc.required_role
        return McpError(
            McpErrorCode.forbidden,
            localized_error(f"Недостаточно прав: нужна роль {role}.", f"Not enough rights: the {role} role is needed.")
            if role is not None
            else None,
        )
    if isinstance(exc, ProjectReadOnlyError):
        return McpError(McpErrorCode.read_only)
    if isinstance(exc, QuotaExceededError | ProjectQuotaExceededError):
        return McpError(McpErrorCode.quota_exceeded, str(exc) or None)
    if isinstance(exc, IdentityError):
        hidden = exc.code in {IdentityErrorCode.not_found, IdentityErrorCode.forbidden}
        return McpError(McpErrorCode.forbidden if hidden else McpErrorCode.failed, None if hidden else str(exc))
    if isinstance(exc, PermissionError):
        return McpError(McpErrorCode.forbidden, str(exc) or None)
    if isinstance(exc, ArgumentError | ValueError | FileExistsError):
        return McpError(McpErrorCode.invalid_arguments, str(exc) or None)
    logger.exception("mcp_tool_failed", exc_info=exc)
    return McpError(McpErrorCode.failed)
