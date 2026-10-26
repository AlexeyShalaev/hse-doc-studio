from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from hse_doc_studio.core.checks.protocols import ICheckRunner
from hse_doc_studio.core.compile.errors import DockerUnavailableError, ImageMissingError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.jobs.entities import BuildOutcome, CompileResult, JobResult, JobSpec, compile_payload_of
from hse_doc_studio.core.jobs.enums import JobStatus
from hse_doc_studio.core.jobs.outputs import IJobOutputs
from hse_doc_studio.core.jobs.protocols import JobRunContext
from hse_doc_studio.core.language_check import ILanguageCheckService
from hse_doc_studio.core.office import IOfficeConvertService
from hse_doc_studio.core.repositories import ISettingsRepository
from hse_doc_studio.core.system_capacity import ISystemCapacityProbe
from hse_doc_studio.infra.compile.concurrency import CompileConcurrencyLimiter
from hse_doc_studio.infra.compile.docker_compile_executor import DockerCompileExecutor
from hse_doc_studio.infra.compile.docker_image_manager import DockerImageManager
from hse_doc_studio.infra.jobs.compile_body import (
    QUEUE_HEARTBEAT_INTERVAL_S,
    BuildState,
    CapacityGate,
    consume_build_stream,
    run_checks,
    run_copy_only,
)

# Нижняя граница $max_repeat latexmk: меньше не сойтись документу с hyperref,
# оглавлением и перекрёстными ссылками (latexmk упрётся в предел до стабилизации ссылок).
_MIN_LATEX_PASSES = 3


class EmbeddedCompileRunner:
    """Раннер compile-задачи внутри процесса приложения: docker-сборка или copy-only, затем проверки."""

    def __init__(  # noqa: PLR0913
        self,
        executor: DockerCompileExecutor,
        image_manager: DockerImageManager,
        office_convert: IOfficeConvertService,
        check_runner: ICheckRunner,
        lt_manager: ILanguageCheckService,
        settings_repo: ISettingsRepository,
        capacity_probe: ISystemCapacityProbe | None,
        limiter: CompileConcurrencyLimiter,
        outputs: IJobOutputs,
        resolve_image: Callable[[], str],
        resolve_lt_image: Callable[[], str],
        resolve_office_image: Callable[[], str],
        heartbeat_interval_s: float = QUEUE_HEARTBEAT_INTERVAL_S,
    ) -> None:
        self._executor = executor
        self._image_manager = image_manager
        self._office_convert = office_convert
        self._check_runner = check_runner
        self._lt_manager = lt_manager
        self._settings_repo = settings_repo
        self._outputs = outputs
        self._resolve_image = resolve_image
        self._resolve_lt_image = resolve_lt_image
        self._resolve_office_image = resolve_office_image
        self._gate = CapacityGate(limiter, capacity_probe, heartbeat_interval_s)

    async def preflight(self, spec: JobSpec) -> None:
        """Не ставит сборку, если образ LaTeX не установлен локально.

        Скачивание многогигабайтного образа отдельное действие пользователя
        (Настройки → Образы → «Установить»): клик по «Сборке» не должен молча
        превращаться в долгую загрузку. Copy-only варианты не требуют ни docker,
        ни образа.
        """
        if not compile_payload_of(spec).needs_compile:
            return
        image = self._resolve_image()
        docker_status = await self._image_manager.docker_status()
        if not docker_status.available:
            raise DockerUnavailableError(
                docker_status.detail or localized_error("Демон Docker недоступен", "Docker daemon is not reachable"),
                reason=str(docker_status.reason) if docker_status.reason else None,
                socket_gid=docker_status.socket_gid,
            )
        if await self._image_manager.inspect(image) is None:
            raise ImageMissingError(image)

    async def run_build(self, spec: JobSpec, ctx: JobRunContext) -> BuildOutcome:
        payload = compile_payload_of(spec)
        # Настройка пользователя (Settings → Compiler) важнее значения из шаблона;
        # latex_passes трактуется как предел $max_repeat у latexmk.
        user_settings = self._settings_repo.get()
        max_iterations = max(int(user_settings.get("latex_passes", payload.default_passes)), _MIN_LATEX_PASSES)

        state = BuildState()
        if payload.needs_compile:
            async with self._gate.slot(user_settings, ctx.log):
                lines = await self._executor.run(
                    project_folder=ctx.workspace,
                    source_file=payload.source_file,
                    engine=str(payload.engine),
                    max_iterations=max_iterations,
                    doc_id=payload.doc_id,
                    compile_id=spec.id,
                    # Образ выбирается заново после ожидания слота, как и раньше.
                    image=self._resolve_image(),
                    on_process_started=ctx.on_process,
                )
                await consume_build_stream(lines, ctx.log, state)
        else:
            await run_copy_only(
                spec.id,
                payload,
                ctx.workspace,
                ctx.log,
                state,
                self._office_convert,
                self._outputs,
                self._resolve_office_image,
            )
        # Время окончания снимается до проверок и не сдвигается на их длительность.
        return BuildOutcome(
            success=state.success,
            status=JobStatus.succeeded if state.success else JobStatus.failed,
            finished_at=datetime.now(tz=timezone.utc),
            pages=state.pages,
            words=state.words,
            chars=state.chars,
        )

    async def run_post(self, spec: JobSpec, ctx: JobRunContext, outcome: BuildOutcome) -> JobResult:
        payload = compile_payload_of(spec)
        check_results = await run_checks(
            payload.check_plan,
            payload,
            ctx.workspace,
            ctx.log,
            outcome.success,
            self._check_runner,
            self._lt_manager,
            self._resolve_lt_image,
        )
        return JobResult(
            status=outcome.status,
            data=CompileResult(
                build_ok=outcome.success,
                check_results=tuple(check_results),
                pages=outcome.pages,
                words=outcome.words,
                chars=outcome.chars,
                finished_at=outcome.finished_at,
            ),
        )
