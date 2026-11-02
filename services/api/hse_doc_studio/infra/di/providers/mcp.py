"""MCP-сервер Студии (docs/design/mcp.md): каталог тулов, сценарии вызова, настройки и журнал."""

from __future__ import annotations

from dishka import AsyncContainer, Provider, Scope, provide

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.access.checker import IProjectAccessChecker
from hse_doc_studio.core.identity.protocols import IAuditLog, IAuditReader, IInstanceSettingsRepository
from hse_doc_studio.core.mcp.protocols import IMcpCallJournal, IMcpSettingsStore
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.core.repositories import ISettingsRepository
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.infra.mcp.local import LocalMcpSettingsStore, MemoryMcpCallJournal
from hse_doc_studio.infra.mcp.server import AuditMcpCallJournal, ServerMcpSettingsStore
from hse_doc_studio.use_cases.chat._registry import ToolRegistry
from hse_doc_studio.use_cases.compile.get_archived_pdf import GetArchivedPdfUC
from hse_doc_studio.use_cases.files.get_file import GetFileUC
from hse_doc_studio.use_cases.mcp.call_tool import CallMcpToolUC
from hse_doc_studio.use_cases.mcp.catalog import McpCatalog
from hse_doc_studio.use_cases.mcp.journal import ListMcpCallsUC
from hse_doc_studio.use_cases.mcp.list_tools import ListMcpToolsUC
from hse_doc_studio.use_cases.mcp.resources import ReadMcpResourceUC
from hse_doc_studio.use_cases.mcp.settings import GetMcpSettingsUC, UpdateMcpSettingsUC
from hse_doc_studio.use_cases.projects.get_project_access import GetProjectAccessUC


class McpProvider(Provider):
    """Общее для обоих режимов; хранилища здесь локальные, серверный провайдер их перекрывает."""

    scope = Scope.REQUEST

    @provide(scope=Scope.APP)
    def get_mcp_settings_store(self, repo: ISettingsRepository) -> IMcpSettingsStore:
        return LocalMcpSettingsStore(repo)

    @provide(scope=Scope.APP)
    def get_mcp_call_journal(self) -> IMcpCallJournal:
        return MemoryMcpCallJournal()

    @provide
    def get_mcp_catalog(self, registry: ToolRegistry, container: AsyncContainer) -> McpCatalog:
        return McpCatalog(registry, container, server_mode=settings.mode is StudioMode.server)

    @provide
    def get_call_mcp_tool_uc(
        self,
        catalog: McpCatalog,
        store: IMcpSettingsStore,
        journal: IMcpCallJournal,
        access: IProjectAccessChecker,
        project_access: GetProjectAccessUC,
    ) -> CallMcpToolUC:
        return CallMcpToolUC(catalog, store, journal, access, project_access)

    @provide
    def get_list_mcp_tools_uc(self, catalog: McpCatalog, store: IMcpSettingsStore) -> ListMcpToolsUC:
        return ListMcpToolsUC(catalog, store)

    @provide
    def get_read_mcp_resource_uc(  # noqa: PLR0913 — порты чтения ресурса
        self,
        catalog: McpCatalog,
        store: IMcpSettingsStore,
        call_tool: CallMcpToolUC,
        access: IProjectAccessChecker,
        get_file: GetFileUC,
        get_pdf: GetArchivedPdfUC,
    ) -> ReadMcpResourceUC:
        return ReadMcpResourceUC(catalog, store, call_tool, access, get_file, get_pdf)

    @provide
    def get_get_mcp_settings_uc(self, catalog: McpCatalog, store: IMcpSettingsStore) -> GetMcpSettingsUC:
        return GetMcpSettingsUC(catalog, store)

    @provide
    def get_update_mcp_settings_uc(self, catalog: McpCatalog, store: IMcpSettingsStore) -> UpdateMcpSettingsUC:
        return UpdateMcpSettingsUC(catalog, store)

    @provide
    def get_list_mcp_calls_uc(self, journal: IMcpCallJournal) -> ListMcpCallsUC:
        return ListMcpCallsUC(journal)


class ServerMcpProvider(Provider):
    """Облако: настройки на установку и журнал в аудите."""

    scope = Scope.APP

    @provide(override=True)
    def get_mcp_settings_store(
        self, repo: IInstanceSettingsRepository, audit: IAuditLog, uow: IUnitOfWork
    ) -> IMcpSettingsStore:
        return ServerMcpSettingsStore(repo, audit, uow)

    @provide(override=True)
    def get_mcp_call_journal(self, audit: IAuditLog, reader: IAuditReader, uow: IUnitOfWork) -> IMcpCallJournal:
        return AuditMcpCallJournal(audit, reader, uow)
