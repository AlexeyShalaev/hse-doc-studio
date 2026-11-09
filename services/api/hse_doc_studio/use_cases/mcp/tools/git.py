"""git-синхронизация проекта: статус, выборка и синхронизация с удалённым репозиторием.

`git_sync` идёт тем же путём, что кнопка синхронизации в интерфейсе: `StartSyncUC` (POST /git/sync) запускает
фоновую операцию, её ход и итог читает `GetOperationUC` (GET /git/operations/{id}), список конфликтов `GetConflictsUC`
(экран «Конфликты»). Если синхронизация уже идёт, тул, как и интерфейс, присоединяется к ней (`sync_busy`).
В ответе только итог, счётчики и пути файлов: адрес репозитория и доступ к нему туда не попадают.
"""

from __future__ import annotations

import asyncio
import time
from typing import Final

from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.enums import ToolKind
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.git_sync.entities import GitOperation, OperationStatus, SyncOutcome, SyncResult
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.use_cases.git_sync.fetch_remote import FetchGitRemoteInput, FetchGitRemoteUC
from hse_doc_studio.use_cases.git_sync.get_conflicts import GetConflictsInput, GetConflictsUC
from hse_doc_studio.use_cases.git_sync.operations import GetOperationUC
from hse_doc_studio.use_cases.git_sync.start_sync import StartSyncInput, StartSyncUC
from hse_doc_studio.use_cases.git_sync.status import GetGitStatusInput, GetGitStatusUC
from hse_doc_studio.use_cases.mcp.tools._base import McpTool, int_arg, json_result, project_schema

# Ожидание итога в одном вызове: по умолчанию меньше таймаута запроса у клиентов MCP (60 с в SDK).
SYNC_WAIT_S: Final = 45
SYNC_MAX_WAIT_S: Final = 240
_POLL_S = 0.5
# Сколько путей файлов попадает в ответ; остальные видны числом.
_MAX_LISTED: Final = 50


class GitStatusTool(McpTool):
    spec = ToolSpec(
        name="git_status",
        description="Состояние связи проекта с git-remote: подключён ли, впереди/позади, ошибки, идущая операция.",
        parameters=project_schema({}),
    )
    kind = ToolKind.read

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        view = await (await self._deps.get(GetGitStatusUC)).execute(GetGitStatusInput(project_id=ctx.project_id))
        return json_result(view)


class GitFetchTool(McpTool):
    spec = ToolSpec(
        name="git_fetch",
        description="Забрать изменения из git-remote без слияния и показать, насколько проект впереди или позади.",
        parameters=project_schema({}),
    )
    kind = ToolKind.exec_

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        view = await (await self._deps.get(FetchGitRemoteUC)).execute(FetchGitRemoteInput(project_id=ctx.project_id))
        return json_result(view)


class GitSyncTool(McpTool):
    spec = ToolSpec(
        name="git_sync",
        description=(
            "Синхронизировать проект с git-remote, как кнопка синхронизации: сохранить снимок, забрать чужие "
            "изменения (pull) и отправить свои (push). Ждёт итог до wait_s секунд; если не дождался, ответ "
            "status: running, повторный вызов присоединится к той же синхронизации. Итог: outcome (up_to_date, "
            "pushed, fast_forwarded, merged, conflicts), сколько версий получено и отправлено. При конфликтах "
            "отправка не делается, в ответе файлы с конфликтами; решаются они в Студии (кнопка «Разобрать»). "
            'Пример: {"project_id": "<uuid>", "wait_s": 45}.'
        ),
        parameters=project_schema(
            {
                "wait_s": {
                    "type": "integer",
                    "default": SYNC_WAIT_S,
                    "description": f"Сколько секунд ждать итога (0..{SYNC_MAX_WAIT_S})",
                }
            }
        ),
    )
    kind = ToolKind.exec_

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        wait_s = int_arg(args, "wait_s", SYNC_WAIT_S, lo=0, hi=SYNC_MAX_WAIT_S)
        try:
            operation_id, joined = await self._start(ctx)
        except GitSyncError as exc:
            return _refusal(exc)
        except NotFoundError as exc:
            # Удалённый репозиторий не подключён: проект уже прошёл проверку прав, текст сценария понятен.
            return ToolResult.error(str(exc))
        operations = await self._deps.get(GetOperationUC)
        operation = await _wait(operations, operation_id, wait_s)
        view = await self._view(ctx, operation, joined=joined)
        result = json_result(view)
        if operation.status in {OperationStatus.failed, OperationStatus.cancelled}:
            return ToolResult.error(result.text)
        return result

    async def _start(self, ctx: AgentToolContext) -> tuple[str, bool]:
        """Новая синхронизация или уже идущая (как интерфейс при `sync_busy`)."""
        try:
            out = await (await self._deps.get(StartSyncUC)).execute(StartSyncInput(project_id=ctx.project_id))
        except GitSyncError as exc:
            running = exc.ctx.get("operation_id")
            if exc.code is GitErrorCode.sync_busy and isinstance(running, str) and running:
                return running, True
            raise
        return out.operation_id, False

    async def _view(self, ctx: AgentToolContext, operation: GitOperation, *, joined: bool) -> dict[str, object]:
        view: dict[str, object] = {
            "operation_id": operation.id,
            "status": operation.status,
            "phase": operation.phase,
        }
        if joined:
            view["joined"] = True
        result = operation.result
        if isinstance(result, SyncResult):
            view.update(_result_view(result))
            if result.outcome is SyncOutcome.conflicts:
                view["conflict_files"] = await self._conflict_files(ctx)
        if operation.error is not None:
            view["error"] = {"code": operation.error.code, "detail": operation.error.detail}
        view["hint"] = _hint(operation)
        return view

    async def _conflict_files(self, ctx: AgentToolContext) -> list[dict[str, object]]:
        try:
            session = await (await self._deps.get(GetConflictsUC)).execute(GetConflictsInput(project_id=ctx.project_id))
        except GitSyncError:
            return []
        conflicts = [f for f in session.files if f.action == "conflict"]
        return [
            {"path": f.path, "doc_id": f.doc_id, "conflict_type": f.conflict_type, "resolved": f.resolved}
            for f in conflicts[:_MAX_LISTED]
        ]


async def _wait(operations: GetOperationUC, operation_id: str, wait_s: float) -> GitOperation:
    deadline = time.monotonic() + wait_s
    current = await operations.execute(operation_id)
    while current.status is OperationStatus.running and time.monotonic() < deadline:
        await asyncio.sleep(_POLL_S)
        current = await operations.execute(operation_id)
    return current


def _result_view(result: SyncResult) -> dict[str, object]:
    view: dict[str, object] = {
        "outcome": result.outcome,
        "pulled_commits": result.pulled_commits,
        "pushed_commits": result.pushed_commits,
        "files_changed": result.files_changed,
    }
    if result.auto:
        view["auto_merged"] = [
            {"path": a.path, "action": a.action, "copy_path": a.copy_path} for a in result.auto[:_MAX_LISTED]
        ]
    if result.conflicts is not None:
        view["conflicts"] = {"files_total": result.conflicts.files_total, "files_open": result.conflicts.files_open}
    if result.warnings:
        view["warnings"] = [{"code": w.code, "paths": list(w.paths[:_MAX_LISTED])} for w in result.warnings]
    return view


def _hint(operation: GitOperation) -> str:
    result = operation.result
    if operation.status is OperationStatus.running:
        return localized_error(
            "Синхронизация ещё идёт: вызовите git_sync снова, чтобы дождаться итога (новая не начнётся).",
            "The sync is still running: call git_sync again to wait for the result (no new sync starts).",
        )
    if isinstance(result, SyncResult) and result.outcome is SyncOutcome.conflicts:
        return localized_error(
            "Одни и те же места изменены у обоих, отправка заблокирована. Конфликты решаются в Студии: кнопка "
            "«Разобрать» в панели синхронизации проекта. Файлы на диске не тронуты.",
            "The same places were changed on both sides; pushing is blocked. Resolve the conflicts in the Studio: "
            "the “Resolve” button in the project sync panel. Files on disk are untouched.",
        )
    if operation.status is OperationStatus.succeeded:
        return localized_error("Синхронизация завершена.", "The sync has finished.")
    return localized_error("Синхронизация не удалась, причина в error.", "The sync failed, see error.")


def _refusal(exc: GitSyncError) -> ToolResult:
    """Отказ до запуска: `detail` уже локализован и очищен от секретов (core/git_sync/errors.py)."""
    return ToolResult.error(f"{exc.detail} ({exc.code.value})")
