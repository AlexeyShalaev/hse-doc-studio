"""Каталог тулов MCP: правило на каждый тул и сборка определений из агента и `use_cases/mcp/tools`.

Таблица `MCP_TOOL_RULES` единственное место, где сказано, какое право нужно туле, в какой он группе и опасен ли
(docs/design/mcp.md, раздел 5). Тесты сверяют её с обработчиками: тул без записи в каталог не попадает, запись без
обработчика роняет сборку каталога.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from hse_doc_studio.core.access.actions import Action
from hse_doc_studio.core.agent.entities import ToolSpec
from hse_doc_studio.core.agent.tools import ToolDefinition
from hse_doc_studio.core.enums import ToolKind
from hse_doc_studio.core.mcp.entities import McpToolGroup, McpToolMeta
from hse_doc_studio.core.mcp.protocols import IDependencyResolver
from hse_doc_studio.core.rate_limit import COMPILE, GIT_SYNC, UPLOAD, RateRule
from hse_doc_studio.use_cases.chat._registry import ToolRegistry
from hse_doc_studio.use_cases.mcp.tools import admin, build, cloud, files, git, people, projects, review, submission
from hse_doc_studio.use_cases.mcp.tools import template as template_tools
from hse_doc_studio.use_cases.mcp.tools._base import PROJECT_ID_SCHEMA, McpTool
from hse_doc_studio.use_cases.mcp.tools.compile_document import CompileDocumentTool
from hse_doc_studio.use_cases.mcp.tools.fields import ListProjectFieldsTool

# Записи, которые HTTP пропускает и в проект «только для чтения» (api/guards.py `_ALLOWED_SUFFIXES` и DELETE):
# откат к снимку, выборка из git-remote и удаление проекта.
_WRITE_GUARD_EXEMPT = frozenset({"vcs_restore", "git_fetch", "delete_project"})


@dataclass(frozen=True, slots=True)
class McpToolRule:
    meta: McpToolMeta
    # Право на проект; None значит, что тул работает вне проекта (список проектов, админка).
    action: Action | None = None
    # Аргументы с путями файлов: каждый проверяется как область права.
    path_args: tuple[str, ...] = ()
    # Правило частоты маршрута, которому тул соответствует.
    rate: RateRule | None = None

    @property
    def name(self) -> str:
        return self.meta.name

    @property
    def needs_project(self) -> bool:
        return self.action is not None

    @property
    def guards_write(self) -> bool:
        return self.needs_project and not self.meta.read_only and self.name not in _WRITE_GUARD_EXEMPT


def _rule(  # noqa: PLR0913 — строка таблицы
    name: str,
    group: McpToolGroup,
    kind: ToolKind,
    action: Action | None = None,
    *,
    path_args: tuple[str, ...] = (),
    dangerous: bool = False,
    server_only: bool = False,
    local_only: bool = False,
    rate: RateRule | None = None,
) -> McpToolRule:
    admin_tool = group is McpToolGroup.admin
    meta = McpToolMeta(
        name=name,
        group=group,
        kind=kind,
        dangerous=dangerous,
        server_only=server_only or admin_tool,
        local_only=local_only,
        admin=admin_tool,
    )
    return McpToolRule(meta=meta, action=action, path_args=path_args, rate=rate)


_R, _W, _X = ToolKind.read, ToolKind.write, ToolKind.exec_
_G = McpToolGroup

MCP_TOOL_RULES: tuple[McpToolRule, ...] = (
    _rule("whoami", _G.account, _R),
    # Проекты
    _rule("list_projects", _G.projects, _R),
    _rule("get_project", _G.projects, _R, Action.PROJECT_VIEW),
    _rule("list_templates", _G.projects, _R),
    _rule("create_project", _G.projects, _X),
    _rule("list_project_fields", _G.projects, _R, Action.PROJECT_VIEW),
    _rule("set_project_meta", _G.projects, _W, Action.PROJECT_SETTINGS),
    _rule("set_project_people", _G.projects, _W, Action.PROJECT_SETTINGS),
    _rule("set_language", _G.projects, _W, Action.PROJECT_SETTINGS),
    _rule("delete_project", _G.projects, _X, Action.PROJECT_DELETE, dangerous=True),
    _rule("clone_cloud_project", _G.projects, _X, local_only=True, rate=GIT_SYNC),
    # Обновление шаблона: статус видит участник, план и применение как у маршрутов template-update
    _rule("template_update_status", _G.projects, _R, Action.PROJECT_VIEW),
    _rule("plan_template_update", _G.projects, _X, Action.TEMPLATE_MANAGE),
    _rule("apply_template_update", _G.projects, _X, Action.TEMPLATE_MANAGE),
    # Документы и файлы
    _rule("list_documents", _G.files, _R, Action.PROJECT_VIEW),
    _rule("list_files", _G.files, _R, Action.SOURCES_READ),
    _rule("read_tex", _G.files, _R, Action.FILES_READ, path_args=("path",)),
    _rule("read_pdf", _G.files, _R, Action.FILES_READ, path_args=("path",)),
    _rule("grep_project", _G.files, _R, Action.SOURCES_READ),
    _rule("edit_tex", _G.files, _W, Action.FILES_WRITE, path_args=("path",), rate=UPLOAD),
    _rule("write_file", _G.files, _W, Action.FILES_WRITE, path_args=("path",), rate=UPLOAD),
    _rule("move_file", _G.files, _W, Action.FILES_WRITE, path_args=("src", "dst")),
    _rule("delete_file", _G.files, _W, Action.FILES_WRITE, path_args=("path",), dangerous=True),
    # Сборка
    _rule("compile_document", _G.build, _X, Action.BUILD_RUN, rate=COMPILE),
    _rule("list_compiles", _G.build, _R, Action.OUTPUT_READ),
    _rule("get_compile", _G.build, _R, Action.OUTPUT_READ),
    _rule("cancel_compile", _G.build, _X, Action.BUILD_RUN),
    # Проверки и требования
    _rule("list_check_findings", _G.checks, _R, Action.OUTPUT_READ),
    _rule("run_checks", _G.checks, _X, Action.BUILD_RUN, rate=COMPILE),
    _rule("list_check_rules", _G.checks, _R, Action.OUTPUT_READ),
    _rule("normcontrol_report", _G.checks, _R, Action.OUTPUT_READ),
    _rule("trace_requirements", _G.checks, _R, Action.PROJECT_VIEW),
    _rule("preview_requirements_format", _G.checks, _R, Action.PROJECT_VIEW),
    _rule("set_requirements_format", _G.checks, _W, Action.PROJECT_SETTINGS),
    # Ревью (сценарии сами проверяют COMMENT и автора)
    _rule("list_review_threads", _G.review, _R, Action.SOURCES_READ, server_only=True),
    _rule("create_review_thread", _G.review, _W, Action.COMMENT, server_only=True),
    _rule("reply_review_thread", _G.review, _W, Action.COMMENT, server_only=True),
    _rule("set_review_thread_status", _G.review, _W, Action.COMMENT, server_only=True),
    # История и git
    _rule("vcs_status", _G.history, _R, Action.SOURCES_READ),
    _rule("vcs_list_history", _G.history, _R, Action.SOURCES_READ),
    _rule("vcs_diff", _G.history, _R, Action.SOURCES_READ),
    _rule("vcs_save_snapshot", _G.history, _W, Action.HISTORY_WRITE),
    _rule("vcs_restore", _G.history, _X, Action.HISTORY_REWRITE, dangerous=True),
    _rule("git_status", _G.history, _R, Action.SOURCES_READ),
    _rule("git_fetch", _G.history, _X, Action.HISTORY_WRITE, rate=GIT_SYNC),
    _rule("git_sync", _G.history, _X, Action.HISTORY_REWRITE, dangerous=True, rate=GIT_SYNC),
    # Сдача и подписи
    _rule("list_submission_profiles", _G.submission, _R, Action.PROJECT_VIEW),
    _rule("list_submissions", _G.submission, _R, Action.SUBMISSION_READ),
    _rule("package_project", _G.submission, _X, Action.SUBMISSION_CREATE),
    _rule("list_signatures", _G.submission, _R, Action.OUTPUT_READ),
    # Админка (сценарии сами требуют админа установки)
    _rule("admin_list_users", _G.admin, _R),
    _rule("admin_queue_summary", _G.admin, _R),
    _rule("admin_runner_summary", _G.admin, _R),
    _rule("admin_list_audit", _G.admin, _R),
    _rule("admin_disable_user", _G.admin, _W, dangerous=True),
    _rule("admin_enable_user", _G.admin, _W),
    _rule("admin_cancel_job", _G.admin, _X, dangerous=True),
)

RULES_BY_NAME: Mapping[str, McpToolRule] = {rule.name: rule for rule in MCP_TOOL_RULES}

# Тулы, которых нет у встроенного агента.
MCP_TOOL_CLASSES: tuple[type[McpTool], ...] = (
    projects.WhoamiTool,
    projects.GetProjectTool,
    projects.DeleteProjectTool,
    people.SetProjectPeopleTool,
    ListProjectFieldsTool,
    cloud.CloneCloudProjectTool,
    template_tools.TemplateUpdateStatusTool,
    template_tools.PlanTemplateUpdateTool,
    template_tools.ApplyTemplateUpdateTool,
    files.ListFilesTool,
    files.WriteFileTool,
    files.MoveFileTool,
    files.DeleteFileTool,
    CompileDocumentTool,
    build.ListCompilesTool,
    build.GetCompileTool,
    build.CancelCompileTool,
    build.RunChecksTool,
    build.ListCheckRulesTool,
    build.NormcontrolReportTool,
    review.ListReviewThreadsTool,
    review.CreateReviewThreadTool,
    review.ReplyReviewThreadTool,
    review.SetReviewThreadStatusTool,
    git.GitStatusTool,
    git.GitFetchTool,
    git.GitSyncTool,
    submission.ListSubmissionProfilesTool,
    submission.ListSubmissionsTool,
    submission.ListSignaturesTool,
    admin.AdminListUsersTool,
    admin.AdminQueueSummaryTool,
    admin.AdminRunnerSummaryTool,
    admin.AdminListAuditTool,
    admin.AdminDisableUserTool,
    admin.AdminEnableUserTool,
    admin.AdminCancelJobTool,
)


@dataclass(frozen=True, slots=True)
class McpToolEntry:
    rule: McpToolRule
    definition: ToolDefinition

    @property
    def meta(self) -> McpToolMeta:
        return self.rule.meta

    @property
    def spec(self) -> ToolSpec:
        return self.definition.spec


class McpCatalogError(LookupError):
    """Правило без обработчика или обработчик без правила: ошибка сборки, а не вызова."""


def with_project_id(spec: ToolSpec) -> ToolSpec:
    """Тулы проекта у агента берут проект из контекста чата; клиенту MCP его нужно назвать аргументом."""
    params: dict[str, Any] = dict(spec.parameters)
    properties = {"project_id": dict(PROJECT_ID_SCHEMA), **dict(params.get("properties") or {})}
    required = ["project_id", *[r for r in params.get("required") or [] if r != "project_id"]]
    return replace(spec, parameters={**params, "type": "object", "properties": properties, "required": required})


class McpCatalog:
    """Все тулы MCP в порядке таблицы; локально без серверных (ревью, админка), в облаке без локальных."""

    def __init__(self, registry: ToolRegistry, deps: IDependencyResolver, *, server_mode: bool) -> None:
        definitions: dict[str, ToolDefinition] = {d.spec.name: d for d in registry.all()}
        for cls in MCP_TOOL_CLASSES:
            definition = cls(deps).definition()
            if definition.spec.name not in RULES_BY_NAME:
                raise McpCatalogError(definition.spec.name)
            definitions[definition.spec.name] = definition
        entries: list[McpToolEntry] = []
        for rule in MCP_TOOL_RULES:
            if (rule.meta.server_only and not server_mode) or (rule.meta.local_only and server_mode):
                continue
            definition = definitions.get(rule.name)
            if definition is None:
                raise McpCatalogError(rule.name)
            if rule.needs_project:
                definition = replace(definition, spec=with_project_id(definition.spec))
            entries.append(McpToolEntry(rule=rule, definition=definition))
        self._entries = entries
        self._by_name = {e.rule.name: e for e in entries}

    def all(self) -> Sequence[McpToolEntry]:
        return self._entries

    def get(self, name: str) -> McpToolEntry | None:
        return self._by_name.get(name)
