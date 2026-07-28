from __future__ import annotations

import asyncio
import time
from pathlib import Path
from uuid import UUID

from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.agent.tools import ToolDefinition
from hse_doc_studio.core.entities import CompileRecord
from hse_doc_studio.core.enums import CompileStatus, Lang, ToolKind
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.infra.persistence.compile import JsonCompileRepository
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
    def __init__(
        self,
        trigger_compile_uc: TriggerCompileUC,
        get_project_uc: GetProjectUC,
        compile_repo: JsonCompileRepository,
    ) -> None:
        self._trigger = trigger_compile_uc
        self._get_project = get_project_uc
        self._compile_repo = compile_repo

    def definition(self) -> ToolDefinition:
        # Available to local/weak models too: "собери проект" is the canonical
        # build request and must work on Ollama. The approval gate (exec) still
        # guards each run, so an unreliable model can't build without a confirm.
        return ToolDefinition(spec=_SPEC, kind=ToolKind.exec_, handler=self, weak_model_safe=True)

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        lang = current_interface_language()
        doc_id = str(args.get("doc_id", "")).strip()
        if not doc_id:
            return ToolResult.error("specify the doc_id parameter" if lang == Lang.en else "укажите параметр doc_id")
        try:
            out = await self._trigger.execute(TriggerCompileInput(project_id=ctx.project_id, doc_id=doc_id))
        except (ValueError, NotFoundError) as exc:
            return ToolResult.error(str(exc))

        project_result = await self._get_project.execute(GetProjectInput(project_id=ctx.project_id))
        record = await self._poll(project_result.project.folder, out.compile_id)
        if record is None:
            return ToolResult.error(
                f"build of {doc_id} did not finish within {int(_POLL_TIMEOUT_S)} s"
                if lang == Lang.en
                else f"сборка {doc_id} не завершилась за {int(_POLL_TIMEOUT_S)} с"
            )
        return self._format(doc_id, record, lang)

    async def _poll(self, folder: Path, compile_id: UUID) -> CompileRecord | None:
        deadline = time.monotonic() + _POLL_TIMEOUT_S
        while time.monotonic() < deadline:
            record = self._compile_repo.get_for_project(folder, compile_id)
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
