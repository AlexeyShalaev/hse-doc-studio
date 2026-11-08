from __future__ import annotations

import time
from copy import copy
from pathlib import Path
from uuid import UUID

from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.agent.tools import ToolDefinition
from hse_doc_studio.core.compile.failure import INTERRUPTED, failure_message
from hse_doc_studio.core.entities import CompileRecord
from hse_doc_studio.core.enums import CompileStatus, Lang, ToolKind
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.core.jobs.errors import NoRunnerAvailableError
from hse_doc_studio.core.repositories import ICompileRepository
from hse_doc_studio.core.shutdown import RESTART_RETRY_AFTER_S, ServerRestartingError, ShutdownSignal
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
        *,
        shutdown: ShutdownSignal | None = None,
        builds_survive_restart: bool = False,
    ) -> None:
        self._trigger = trigger_compile_uc
        self._get_project = get_project_uc
        self._compile_repo = compile_repo
        # Остановка процесса во время ожидания: отвечаем сразу, а не 500 после отмены запроса сервером.
        self._shutdown = shutdown or ShutdownSignal()
        self._survives_restart = builds_survive_restart

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
        except NoRunnerAvailableError as exc:
            # Сборку некому взять: причина словами (личный раннер на паузе, нет раннера с office и т. п.).
            return ToolResult.error(f"[{exc.code}] {exc}")
        if self._reports_running and args.get("wait") is False:
            return self._running(doc_id, out.compile_id, lang, waited=False)

        project_result = await self._get_project.execute(GetProjectInput(project_id=ctx.project_id))
        record = await self._poll(project_result.project.folder, out.compile_id)
        if record is None and self._shutdown.requested:
            raise ServerRestartingError(self._restarting_text(doc_id, out.compile_id, lang))
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
            if self._shutdown.requested or await self._shutdown.wait_for(_POLL_INTERVAL_S):
                return None
        return None

    def _restarting_text(self, doc_id: str, compile_id: UUID, lang: Lang) -> str:
        """Что будет со сборкой, пока сервер перезапускается: продолжится на раннере или прервётся."""
        wait = RESTART_RETRY_AFTER_S
        if lang == Lang.en:
            head = f"The Studio server is restarting (for example, an update), so this call cannot wait for {doc_id}."
            if self._survives_restart:
                return (
                    f"{head} Build {compile_id} keeps running on the runner and gets its result after the restart: "
                    f"in {wait} s check it with get_compile (compile_id={compile_id}). Do not start it again."
                )
            return f"{head} Build {compile_id} is interrupted by the restart: call compile_document again in {wait} s."
        head = f"Сервер Студии перезапускается (например, обновление), дождаться сборки {doc_id} в этом вызове нельзя."
        if self._survives_restart:
            return (
                f"{head} Сборка {compile_id} продолжается на раннере и получит итог после перезапуска: через {wait} с "
                f"проверьте её через get_compile (compile_id={compile_id}). Запускать заново не нужно."
            )
        return f"{head} Сборку {compile_id} прервёт перезапуск: повторите compile_document через {wait} с."

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
        interrupted = record.status == CompileStatus.cancelled and record.error_code == INTERRUPTED
        if interrupted:
            lines[0] = f"Build {doc_id}: interrupted" if en else f"Сборка {doc_id}: прервана"
            lines.append(failure_message(INTERRUPTED, Lang.en if en else Lang.ru))
        if record.status == CompileStatus.failure:
            tail = "\n".join((record.log or "").splitlines()[-_LOG_TAIL_LINES:])
            lines.append(("log tail:\n" if en else "хвост лога:\n") + tail)
        text = "\n".join(lines)
        failed = record.status == CompileStatus.failure or interrupted
        return ToolResult.error(text) if failed else ToolResult.ok(text, truncated=False)
