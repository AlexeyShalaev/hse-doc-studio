"""Ресурсы MCP: проекты, файлы и PDF сборок по адресам `studio://` (docs/design/mcp.md, раздел 5).

Ресурс открыт, если включён MCP и тул того же смысла (`list_projects`, `get_project`, `read_tex`, `get_compile`):
выключенный в настройках тул нельзя обойти чтением ресурса. Права те же, что у тулов.
"""

from __future__ import annotations

import mimetypes
import re
from dataclasses import dataclass
from uuid import UUID

from hse_doc_studio.core.access.actions import Action
from hse_doc_studio.core.access.checker import IProjectAccessChecker
from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.mcp.errors import McpError, McpErrorCode
from hse_doc_studio.core.mcp.protocols import IMcpSettingsStore
from hse_doc_studio.core.rate_limit import IRateLimiter
from hse_doc_studio.use_cases.compile.get_archived_pdf import GetArchivedPdfInput, GetArchivedPdfUC
from hse_doc_studio.use_cases.files.get_file import GetFileInput, GetFileUC
from hse_doc_studio.use_cases.mcp.call_tool import CallMcpToolUC, map_tool_error, visible_to
from hse_doc_studio.use_cases.mcp.catalog import McpCatalog

SCHEME = "studio://"
PROJECTS_URI = "studio://projects"
_PROJECT = re.compile(r"^studio://projects/(?P<pid>[0-9a-fA-F-]{32,36})$")
_FILE = re.compile(r"^studio://projects/(?P<pid>[0-9a-fA-F-]{32,36})/files/(?P<path>.+)$")
_PDF = re.compile(
    r"^studio://projects/(?P<pid>[0-9a-fA-F-]{32,36})/compiles/(?P<doc>[^/]+)/(?P<cid>[0-9a-fA-F-]{32,36})/pdf$"
)

_TEXT_SUFFIXES = (".tex", ".bib", ".sty", ".cls", ".md", ".txt", ".yaml", ".yml", ".json", ".csv", ".log")


@dataclass(frozen=True)
class McpResourceTemplate:
    uri_template: str
    name: str
    description: str
    mime_type: str | None = None


@dataclass(frozen=True)
class McpResourceContent:
    uri: str
    mime_type: str
    text: str | None = None
    blob: bytes | None = None


RESOURCE_TEMPLATES: tuple[McpResourceTemplate, ...] = (
    McpResourceTemplate(
        "studio://projects/{project_id}", "project", "Карточка проекта и документы", "application/json"
    ),
    McpResourceTemplate("studio://projects/{project_id}/files/{path}", "file", "Файл проекта"),
    McpResourceTemplate(
        "studio://projects/{project_id}/compiles/{doc_id}/{compile_id}/pdf", "pdf", "PDF сборки", "application/pdf"
    ),
)


class ReadMcpResourceUC:
    def __init__(  # noqa: PLR0913 — порты чтения перечислены явно
        self,
        catalog: McpCatalog,
        settings: IMcpSettingsStore,
        call_tool: CallMcpToolUC,
        access: IProjectAccessChecker,
        get_file: GetFileUC,
        get_pdf: GetArchivedPdfUC,
    ) -> None:
        self._catalog = catalog
        self._settings = settings
        self._call_tool = call_tool
        self._access = access
        self._get_file = get_file
        self._get_pdf = get_pdf

    async def execute(self, uri: str, *, limiter: IRateLimiter | None = None) -> McpResourceContent:
        if uri == PROJECTS_URI:
            return await self._via_tool(uri, "list_projects", {}, limiter)
        if m := _PROJECT.match(uri):
            return await self._via_tool(uri, "get_project", {"project_id": m["pid"]}, limiter)
        if m := _FILE.match(uri):
            return await self._file(uri, _uuid(m["pid"]), m["path"])
        if m := _PDF.match(uri):
            return await self._pdf(uri, _uuid(m["pid"]), m["doc"], _uuid(m["cid"]))
        raise McpError(McpErrorCode.not_found)

    async def _via_tool(
        self, uri: str, tool: str, args: dict[str, object], limiter: IRateLimiter | None
    ) -> McpResourceContent:
        out = await self._call_tool.execute(tool, args, limiter=limiter)
        if out.error_code is not None:
            raise McpError(out.error_code, out.result.text, retry_after_s=out.retry_after_s)
        mime = "application/json" if out.result.text.lstrip().startswith(("{", "[")) else "text/plain"
        return McpResourceContent(uri=uri, mime_type=mime, text=out.result.text)

    async def _allowed(self, tool: str) -> None:
        settings = await self._settings.get()
        if not settings.enabled:
            raise McpError(McpErrorCode.mcp_disabled)
        entry = self._catalog.get(tool)
        if entry is None or not visible_to(require_actor(), entry, settings):
            raise McpError(McpErrorCode.tool_disabled)

    async def _file(self, uri: str, project_id: UUID, path: str) -> McpResourceContent:
        await self._allowed("read_tex")
        await self._require(project_id, Action.FILES_READ, path)
        try:
            out = await self._get_file.execute(GetFileInput(project_id=project_id, path=path))
        except (FileNotFoundError, NotFoundError):
            raise McpError(McpErrorCode.not_found) from None
        mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
        if path.lower().endswith(_TEXT_SUFFIXES) or mime.startswith("text/"):
            return McpResourceContent(
                uri=uri,
                mime_type=mime if mime.startswith("text/") else "text/plain",
                text=out.content.decode("utf-8", errors="replace"),
            )
        return McpResourceContent(uri=uri, mime_type=mime, blob=out.content)

    async def _pdf(self, uri: str, project_id: UUID, doc_id: str, compile_id: UUID) -> McpResourceContent:
        await self._allowed("get_compile")
        await self._require(project_id, Action.OUTPUT_READ, None)
        try:
            out = await self._get_pdf.execute(
                GetArchivedPdfInput(project_id=project_id, doc_id=doc_id, compile_id=compile_id)
            )
        except (FileNotFoundError, NotFoundError):
            raise McpError(McpErrorCode.not_found) from None
        if out.content is not None:
            return McpResourceContent(uri=uri, mime_type="application/pdf", blob=out.content)
        if out.redirect_url is not None:
            return McpResourceContent(uri=uri, mime_type="text/uri-list", text=out.redirect_url)
        raise McpError(McpErrorCode.not_found)

    async def _require(self, project_id: UUID, action: Action, path: str | None) -> None:
        try:
            await self._access.require(project_id, action, path)
        except Exception as exc:  # noqa: BLE001 — отказ прав разбирает общий `map_tool_error`
            raise map_tool_error(exc) from exc


def _uuid(raw: str) -> UUID:
    try:
        return UUID(raw)
    except ValueError:
        raise McpError(McpErrorCode.not_found) from None
