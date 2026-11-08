from __future__ import annotations

import asyncio
import time
from copy import copy
from pathlib import Path
from uuid import UUID

from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.agent.tools import ToolDefinition
from hse_doc_studio.core.entities import CompileRecord
from hse_doc_studio.core.enums import CompileStatus, Lang, ToolKind
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.core.repositories import ICompileRepository
from hse_doc_studio.use_cases.compile.trigger_compile import TriggerCompileInput, TriggerCompileUC
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

_TERMINAL = (CompileStatus.success, CompileStatus.failure, CompileStatus.cancelled)
_POLL_INTERVAL_S = 1.5
_POLL_TIMEOUT_S = 240.0
_LOG_TAIL_LINES = 30

_SPEC = ToolSpec(
    name="compile_document",
    description=(
        "Скомпилировать документ (XeLaTeX в контейнере) и дождаться результата. "
        "Возвращает статус сборки, число страниц, хвост лога при ошибке и сводку "
        "замечаний проверок. Перед вызовом сохрани правки через edit_tex."
    ),
    parameters={
        "type": "object",
        "properties": {"doc_id": {"type": "string", "description": "Идентификатор документа, напр. vkr"}},
        "required": ["doc_id"],
    },
)


class CompileDocumentTool:
    # Сколько ждать итога в одном вызове. Клиенту MCP отвечаем раньше его таймаута, и сборку он досматривает
    # через get_compile: копия с `with_wait_limit` вместо ошибки по таймауту отвечает «ещё идёт» с compile_id.
    _wait_s: float = _POLL_TIMEOUT_S
    _reports_running = False

    def __init__(
        self,
        trigger_compile_uc: TriggerCompileUC,
        get_project_uc: GetProjectUC,
        compile_repo: ICompileRepository,
    ) -> None:
        self._trigger = trigger_compile_uc
        self._get_project = get_project_uc
        self._compile_repo = compile_repo

    def definition(self) -> ToolDefinition:
        # Available to local/weak models too: "собери проект" is the canonical
        # build request and must work on Ollama. The approval gate (exec) still
        # guards each run, so an unreliable model can't build without a confirm.
        return ToolDefinition(spec=_SPEC, kind=ToolKind.exec_, handler=self, weak_model_safe=True)

    def with_wait_limit(self, seconds: float) -> CompileDocumentTool:
        """Копия для клиента MCP: ждёт не дольше `seconds`, понимает `wait=false`, долгую сборку не считает ошибкой."""
        tool = copy(self)
        tool._wait_s = seconds
        tool._reports_running = True
        return tool

    def _running(self, doc_id: str, compile_id: UUID, lang: Lang, *, waited: bool) -> ToolResult:
        """Сборка идёт дальше без этого вызова: не ошибка, а compile_id, по которому смотреть итог."""
        if lang == Lang.en:
            head = (
                f"Build {doc_id} is still running after {int(self._wait_s)} s"
                if waited
                else f"Build {doc_id} started and runs in the background"
            )
            return ToolResult.ok(
                f"{head}.\nstatus: in_progress\ncompile_id: {compile_id}\n"
                f"Result: get_compile with this compile_id; stop: cancel_compile. Do not start the build again."
            )
        head = (
            f"Сборка {doc_id} ещё идёт после {int(self._wait_s)} с ожидания"
            if waited
            else f"Сборка {doc_id} запущена и идёт в фоне"
        )
        return ToolResult.ok(
            f"{head}.\nstatus: in_progress\ncompile_id: {compile_id}\n"
            f"Итог: get_compile с этим compile_id; остановить: cancel_compile. Запускать сборку заново не нужно."
        )

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        lang = current_interface_language()
        doc_id = str(args.get("doc_id", "")).strip()
        if not doc_id:
            return ToolResult.error("specify the doc_id parameter" if lang == Lang.en else "укажите параметр doc_id")
        try:
            out = await self._trigger.execute(TriggerCompileInput(project_id=ctx.project_id, doc_id=doc_id))
        except (ValueError, NotFoundError) as exc:
            return ToolResult.error(str(exc))
        if self._reports_running and args.get("wait") is False:
            return self._running(doc_id, out.compile_id, lang, waited=False)

        project_result = await self._get_project.execute(GetProjectInput(project_id=ctx.project_id))
        record = await self._poll(project_result.project.folder, out.compile_id)
        if record is None:
            if self._reports_running:
                return self._running(doc_id, out.compile_id, lang, waited=True)
            return ToolResult.error(
                f"build of {doc_id} did not finish within {int(_POLL_TIMEOUT_S)} s"
                if lang == Lang.en
                else f"сборка {doc_id} не завершилась за {int(_POLL_TIMEOUT_S)} с"
            )
        return self._format(doc_id, record, lang)

    async def _poll(self, folder: Path, compile_id: UUID) -> CompileRecord | None:
        deadline = time.monotonic() + self._wait_s
        while time.monotonic() < deadline:
            record = await self._compile_repo.get_for_project(folder, compile_id)
            if record is not None and record.status in _TERMINAL:
                return record
            await asyncio.sleep(_POLL_INTERVAL_S)
        return None

    @staticmethod
    def _format(doc_id: str, record: CompileRecord, lang: Lang) -> ToolResult:
        en = lang == Lang.en
        lines = [f"Build {doc_id}: {record.status}" if en else f"Сборка {doc_id}: {record.status}"]
        if record.pages is not None:
            lines.append(f"pages: {record.pages}" if en else f"страниц: {record.pages}")
        errors = [r for r in record.check_results if str(r.severity) == "err"]
        warns = [r for r in record.check_results if str(r.severity) == "warn"]
        lines.append(
            f"findings: {len(errors)} errors, {len(warns)} warnings"
            if en
            else f"замечаний: ошибок {len(errors)}, предупреждений {len(warns)}"
        )
        if record.status == CompileStatus.failure:
            tail = "\n".join((record.log or "").splitlines()[-_LOG_TAIL_LINES:])
            lines.append(("log tail:\n" if en else "хвост лога:\n") + tail)
        text = "\n".join(lines)
        return (
            ToolResult.ok(text, truncated=False) if record.status != CompileStatus.failure else ToolResult.error(text)
        )
