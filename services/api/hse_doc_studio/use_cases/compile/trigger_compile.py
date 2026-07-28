from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

import structlog

from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.entities import ChangeLogEntry, CompileRecord, Project
from hse_doc_studio.core.enums import (
    ChangeLogKind,
    CheckEngine,
    CheckSeverity,
    CompileStatus,
    DocumentStatus,
    EngineType,
    Lang,
    VcsCommitKind,
)
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import current_interface_language, localized_error
from hse_doc_studio.core.repositories import (
    IChangeLogRepository,
    IProjectIndexRepository,
    IProjectRepository,
    ISettingsRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import CheckResolutionService, ProjectTemplateService
from hse_doc_studio.core.system_capacity import (
    MAX_CONCURRENT_COMPILES_CEILING,
    MIN_CONCURRENT_COMPILES,
    ISystemCapacityProbe,
    SystemCapacity,
    default_max_concurrent_compiles,
)
from hse_doc_studio.core.team import doc_base_dir
from hse_doc_studio.core.value_objects import CheckResult, ChecksOverride
from hse_doc_studio.core.vcs.constants import DEFAULT_VCS_EXCLUDE
from hse_doc_studio.core.vcs.entities import VcsSettings
from hse_doc_studio.core.vcs.protocols import IVcsFolderLocks, IVcsService
from hse_doc_studio.infra.checks.runner import CheckRunner
from hse_doc_studio.infra.compile.compile_runner import CompileRunner
from hse_doc_studio.infra.compile.concurrency import CompileConcurrencyLimiter
from hse_doc_studio.infra.compile.docker_compile_executor import (
    _SENTINEL_DONE,
    _SENTINEL_FAILED,
    _SENTINEL_PAGES,
    _SENTINEL_WORDS,
    DockerCompileExecutor,
)
from hse_doc_studio.infra.compile.docker_image_manager import DockerImageManager
from hse_doc_studio.infra.compile.errors import DockerUnavailableError, ImageMissingError
from hse_doc_studio.infra.compile.log_bus import CompileLogBus
from hse_doc_studio.infra.compile.pdf_archive import archive_compiled_pdf
from hse_doc_studio.infra.languagetool.container_manager import LanguageToolContainerManager
from hse_doc_studio.infra.office.convert_manager import CONVERTIBLE_OFFICE_EXTS, OfficeConvertManager
from hse_doc_studio.infra.persistence.compile import JsonCompileRepository
from hse_doc_studio.infra.project_init.template_renderer import (
    instantiate_nda,
    regenerate_dynamic_includes,
)
from hse_doc_studio.use_cases.compile.list_images import resolve_active_image
from hse_doc_studio.use_cases.languagetool.list_languagetool_images import (
    resolve_active_languagetool_image,
)
from hse_doc_studio.use_cases.office_services.list_office_service_images import (
    resolve_active_office_image,
)

logger = structlog.get_logger()

# Пока сборка ждёт слот в очереди, поток логов пустой — фронтовый сторож
# (90с тишины → «похоже, зависла») сработал бы ложно. Heartbeat каждые ~25с
# держит SSE-поток живым, сколько бы очередь ни длилась.
_QUEUE_HEARTBEAT_INTERVAL_S = 25.0


def _pdf_page_count(pdf_path: Path) -> int | None:
    """Число страниц PDF (для pptx-предпросмотра = число слайдов)."""
    try:
        from pypdf import PdfReader  # noqa: PLC0415 — тяжёлый импорт только по месту

        with pdf_path.open("rb") as fh:
            return len(PdfReader(fh).pages)
    except Exception:  # noqa: BLE001 — счётчик страниц не критичен
        return None


def _parse_words_sentinel(line: str) -> tuple[int | None, int | None]:
    """Parse a `__WORDS__:<words>:<chars>` sentinel into (words, chars)."""
    payload = line[len(_SENTINEL_WORDS) :]
    words_str, _sep, chars_str = payload.partition(":")
    try:
        return int(words_str), int(chars_str)
    except ValueError:
        return None, None


@dataclass
class TriggerCompileInput:
    project_id: uuid.UUID
    doc_id: str


@dataclass
class TriggerCompileOutput:
    compile_id: uuid.UUID


def _find_project(
    project_id: uuid.UUID,
    project_repo: IProjectRepository,
    project_index_repo: IProjectIndexRepository,
) -> tuple[Path, Project] | tuple[None, None]:
    known_folders = project_index_repo.list_known()
    for folder in known_folders:
        try:
            project = project_repo.get(folder)
            if project is not None and project.id == project_id:
                return folder, project
        except Exception as exc:
            logger.warning(
                "trigger_compile: error loading project",
                folder=str(folder),
                exc=str(exc),
            )
    return None, None


class TriggerCompileUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        compile_repo: JsonCompileRepository,
        template_repo: ITemplateRepository,
        template_service: ProjectTemplateService,
        check_resolution_service: CheckResolutionService,
        check_runner: CheckRunner,
        changelog_repo: IChangeLogRepository,
        log_bus: CompileLogBus,
        settings_repo: ISettingsRepository,
        compile_runner: CompileRunner,
        compile_limiter: CompileConcurrencyLimiter,
        executor: DockerCompileExecutor,
        image_manager: DockerImageManager,
        lt_manager: LanguageToolContainerManager,
        office_manager: OfficeConvertManager,
        vcs_service: IVcsService,
        vcs_locks: IVcsFolderLocks,
        capacity_probe: ISystemCapacityProbe | None = None,
    ) -> None:
        self._project_repo = project_repo
        self._project_index_repo = project_index_repo
        self._compile_repo = compile_repo
        self._template_repo = template_repo
        self._template_service = template_service
        self._check_resolution_service = check_resolution_service
        self._check_runner = check_runner
        self._changelog_repo = changelog_repo
        self._log_bus = log_bus
        self._settings_repo = settings_repo
        self._compile_runner = compile_runner
        self._compile_limiter = compile_limiter
        self._executor = executor
        self._image_manager = image_manager
        self._lt_manager = lt_manager
        self._office_manager = office_manager
        self._vcs_service = vcs_service
        self._vcs_locks = vcs_locks
        # Лимит сборок читается из СЫРЫХ настроек, а пользователь его обычно не
        # трогал — без зонда здесь очередь работала бы по старой константе 2,
        # хотя в Настройках показано посчитанное по машине значение.
        self._capacity_probe = capacity_probe

    async def _convert_office_preview(
        self,
        compile_id: uuid.UUID,
        project_folder: Path,
        source_file: str,
        log_lines: list[str],
    ) -> int | None:
        """office-файл → соседний PDF-предпросмотр; возвращает число страниц или None.

        PDF кладётся рядом с исходником (presentation.pptx → presentation.pdf) —
        detail-эндпоинт отдаёт его как `preview_file`, встроенный вьювер
        показывает PDF вместо карточки скачивания. Любой сбой (нет Docker,
        не установлен образ Gotenberg, ошибка LibreOffice) не роняет сборку.
        """
        en = current_interface_language() is Lang.en

        def _log(msg: str) -> None:
            log_lines.append(msg)
            self._log_bus.publish(compile_id, msg)

        src_abs = project_folder / source_file
        pdf_abs = src_abs.with_suffix(".pdf")
        _log(
            f"[compile:{compile_id}] converting to PDF for preview (Gotenberg/LibreOffice)…"
            if en
            else f"[compile:{compile_id}] конвертация в PDF для предпросмотра (Gotenberg/LibreOffice)…"
        )
        pdf_bytes = await self._office_manager.convert_to_pdf(
            src_abs, image=resolve_active_office_image(self._settings_repo, "convert")
        )
        if pdf_bytes is None:
            _log(
                f"[compile:{compile_id}] PDF preview unavailable (is the Gotenberg image installed? "
                f"`docker pull gotenberg/gotenberg:8`) — the pptx itself is still the deliverable"
                if en
                else f"[compile:{compile_id}] PDF-предпросмотр недоступен (установлен ли образ Gotenberg? "
                f"`docker pull gotenberg/gotenberg:8`) — сам pptx остаётся артефактом"
            )
            return None
        try:
            pdf_abs.write_bytes(pdf_bytes)
        except OSError as exc:
            _log(f"[compile:{compile_id}] preview write failed: {exc}")
            return None
        pages = _pdf_page_count(pdf_abs)
        _log(
            f"[compile:{compile_id}] preview PDF ready: {pdf_abs.name}" + (f" ({pages} slides)" if pages else "")
            if en
            else f"[compile:{compile_id}] PDF-предпросмотр готов: {pdf_abs.name}"
            + (f" ({pages} слайдов)" if pages else "")
        )
        return pages

    async def execute(self, inp: TriggerCompileInput) -> TriggerCompileOutput:  # noqa: C901
        project_folder, project = _find_project(inp.project_id, self._project_repo, self._project_index_repo)
        if project is None or project_folder is None:
            raise NotFoundError(
                localized_error(f"Проект {inp.project_id} не найден", f"Project not found: {inp.project_id}")
            )

        doc = next((d for d in project.documents if d.id == inp.doc_id), None)
        if doc is None:
            raise NotFoundError(
                localized_error(
                    f"Документ {inp.doc_id!r} не найден в проекте {inp.project_id}",
                    f"Document {inp.doc_id!r} not found in project {inp.project_id}",
                )
            )

        version = self._template_repo.get_version(
            project.lock.pack_id,
            project.lock.template_id,
            project.lock.version,
        )
        if version is None:
            version_ref = f"{project.lock.pack_id}/{project.lock.template_id}/{project.lock.version}"
            raise NotFoundError(
                localized_error(
                    f"Версия шаблона не найдена: {version_ref}", f"Template version not found: {version_ref}"
                )
            )

        # Join с паком — строго по def_id: в team-проекте doc.id несёт суффикс
        # владельца ("vkr--shalaev") и с id определения не совпадает.
        doc_def = self._template_service.find_definition(version, doc)
        if doc_def is None:
            raise NotFoundError(
                localized_error(
                    f"Определение документа {doc.def_id!r} не найдено в версии шаблона",
                    f"Document definition {doc.def_id!r} not found in template version",
                )
            )

        # Re-render dynamic includes (common/meta.tex etc.) from the CURRENT
        # project state before xelatex runs. This is what makes editable data
        # (author/supervisor names, group, NDA, …) reach the PDF on every build
        # without re-rendering — or clobbering — the user's own .tex files.
        regenerate_dynamic_includes(project, version, self._template_repo)
        # If NDA was toggled on after creation, materialise its files now
        # (idempotent — never overwrites the student's edited copies).
        instantiate_nda(project, version, self._template_repo)

        # A custom-file document has an arbitrary user-uploaded file as its one
        # true source — it bypasses chosen_variant/variants resolution entirely
        # (resolve_instance_source resolves via chosen_variant, which does not
        # apply here) and is always copy-only, exactly like an `engine: none`
        # variant today.
        engine = project.lock.engine
        needs_compile = True
        if doc.custom_file is not None:
            source_file = doc.custom_file.stored_path
            needs_compile = False
        else:
            # Путь от корня проекта с префиксом базы владельца (team:
            # "shalaev/vkr/vkr.tex", shared — "shared/…"; solo — как в паке).
            source_file, _output_file = self._template_service.resolve_instance_source(project, doc, version)

            # A chosen variant may declare its own engine — or `engine: none`, a
            # copy-only artifact (pptx / reveal HTML) that is NOT a LaTeX source
            # and must never be fed to xelatex (that fails with "Missing
            # \begin{document}" on the binary .pptx, leaving the doc permanently
            # red). Copy-only variants skip compilation AND the docker preflight:
            # the rendered file already is the deliverable.
            if doc_def.variants:
                chosen_variant_def = next(
                    (v for v in doc_def.variants if v.id == doc.chosen_variant),
                    doc_def.variants[0],
                )
                if chosen_variant_def.engine is None:
                    needs_compile = False
                else:
                    engine = chosen_variant_def.engine

        # Preflight: refuse to schedule the build if the LaTeX image isn't
        # installed locally. Pulling a multi-GB image is a separate user
        # action (Settings → Образы → "Установить") so a Сборка click never
        # silently turns into a long, opaque download. The active image is
        # the user's pick from settings, or the deployment default. Skipped for
        # copy-only variants, which need neither docker nor the image.
        if needs_compile:
            image = resolve_active_image(self._settings_repo)
            docker_status = await self._image_manager.docker_status()
            if not docker_status.available:
                raise DockerUnavailableError(
                    docker_status.detail
                    or localized_error("Демон Docker недоступен", "Docker daemon is not reachable"),
                    reason=str(docker_status.reason) if docker_status.reason else None,
                    socket_gid=docker_status.socket_gid,
                )
            if await self._image_manager.inspect(image) is None:
                raise ImageMissingError(image)
        compile_id = uuid.uuid4()
        now = datetime.now(tz=timezone.utc)

        record = CompileRecord(
            id=compile_id,
            project_folder=project_folder,
            doc_id=inp.doc_id,
            engine=engine,
            status=CompileStatus.pending,
            started_at=now,
            finished_at=None,
            log="",
            output_path=None,
            check_results=[],
            pages=None,
        )
        self._compile_repo.save(record)

        doc_index = project.documents.index(doc)
        project.documents[doc_index] = replace(doc, status=DocumentStatus.building, last_compile_id=compile_id)
        self._project_repo.save(project)

        task = asyncio.create_task(
            self._run_compile_task(
                compile_id=compile_id,
                project_folder=project_folder,
                doc_id=inp.doc_id,
                def_id=doc.def_id,
                base_dir=doc_base_dir(project, doc),
                doc_checks_override=doc.checks_override,
                project_checks_override=project.checks_override,
                source_file=source_file,
                engine=engine,
                version=version,
                needs_compile=needs_compile,
                custom_mode=doc.custom_file is not None,
            )
        )
        self._compile_runner.register(compile_id, task, project_folder, inp.doc_id)

        return TriggerCompileOutput(compile_id=compile_id)

    async def _run_compile_task(  # noqa: C901, PLR0912, PLR0915
        self,
        compile_id: uuid.UUID,
        project_folder: Path,
        doc_id: str,
        def_id: str,
        base_dir: str,
        doc_checks_override: ChecksOverride,
        project_checks_override: ChecksOverride,
        source_file: str,
        engine: EngineType,
        version: TemplateVersion,
        needs_compile: bool = True,
        custom_mode: bool = False,
    ) -> None:
        record = self._compile_repo.get_for_project(project_folder, compile_id)
        if record is None:
            logger.warning("compile task: record not found", compile_id=str(compile_id))
            self._compile_runner.unregister(compile_id)
            return

        running_record = CompileRecord(
            id=record.id,
            project_folder=record.project_folder,
            doc_id=record.doc_id,
            engine=record.engine,
            status=CompileStatus.running,
            started_at=record.started_at,
            finished_at=None,
            log="",
            output_path=record.output_path,
            check_results=record.check_results,
            pages=record.pages,
            words=record.words,
            chars=record.chars,
        )
        self._compile_repo.save(running_record)

        log_lines: list[str] = []
        success = True
        cancelled = False
        crashed_exc: BaseException | None = None
        pages_val: int | None = None
        words_val: int | None = None
        chars_val: int | None = None

        # User settings override the template defaults — they're set in global
        # Settings → Compiler and apply to all compiles. The legacy
        # `latex_passes` setting is now interpreted as latexmk's $max_repeat
        # safety cap (latexmk runs the engine until .aux/.toc stabilise, this
        # just bounds the loop). Floor at 3 — anything lower can't converge a
        # document with hyperref + TOC + cross-references (latexmk would hit
        # the cap before refs stabilise and fail with exit 12).
        user_settings = self._settings_repo.get()
        effective_max_iterations = max(
            int(user_settings.get("latex_passes", version.engine_config.passes)),
            3,
        )

        # From here until the terminal record is persisted we run under a
        # single try/finally. The log bus is closed exactly once — AFTER the
        # final record is saved — because the SSE `done` event derives its
        # status from that persisted record (see GetCompileStreamUC and the
        # compile router). Closing the bus in the streaming `finally` (before
        # checks ran and before the terminal record was written) let a
        # subscriber drain the stream, read a still-`running` record and emit
        # `done {status: "running"}`, wedging the client at "выполняется…"
        # until its 90s stall watchdog fired.
        try:
            try:
                if needs_compile:
                    # Глобальный лимит одновременных docker-сборок: «Собрать
                    # всё» ставит лишние сборки в ОЧЕРЕДЬ вместо запуска
                    # десятков texlive-контейнеров разом. Лимит — живая
                    # настройка (Settings → Компилятор), читается на каждый
                    # захват. Отмена ожидающей сборки работает как обычно.
                    compile_limit = self._resolve_compile_limit(user_settings)
                    heartbeat: asyncio.Task[None] | None = None
                    if self._compile_limiter.active >= compile_limit:
                        wait_msg = (
                            f"[queue] waiting for a free build slot (limit: {compile_limit} concurrent builds)…"
                            if current_interface_language() is Lang.en
                            else f"[queue] ожидание свободного слота сборки (лимит: {compile_limit} одновременно)…"
                        )
                        log_lines.append(wait_msg)
                        self._log_bus.publish(compile_id, wait_msg)
                        heartbeat = asyncio.create_task(self._queue_heartbeat(compile_id, log_lines))
                    try:
                        async with self._compile_limiter.slot(compile_limit):
                            if heartbeat is not None:
                                heartbeat.cancel()
                                heartbeat = None
                                start_msg = (
                                    "[queue] build slot acquired — starting the build"
                                    if current_interface_language() is Lang.en
                                    else "[queue] слот получен — сборка начинается"
                                )
                                log_lines.append(start_msg)
                                self._log_bus.publish(compile_id, start_msg)
                            gen = await self._executor.run(
                                project_folder=project_folder,
                                source_file=source_file,
                                engine=str(engine),
                                max_iterations=effective_max_iterations,
                                doc_id=doc_id,
                                compile_id=compile_id,
                                image=resolve_active_image(self._settings_repo),
                                on_process_started=lambda p: self._compile_runner.set_process(compile_id, p),
                            )

                            async for line in gen:
                                if line == _SENTINEL_DONE:
                                    success = True
                                elif line == _SENTINEL_FAILED:
                                    success = False
                                elif line.startswith(_SENTINEL_PAGES):
                                    try:
                                        pages_val = int(line[len(_SENTINEL_PAGES) :])
                                    except ValueError:
                                        pages_val = None
                                elif line.startswith(_SENTINEL_WORDS):
                                    words_val, chars_val = _parse_words_sentinel(line)
                                else:
                                    log_lines.append(line)
                                    self._log_bus.publish(compile_id, line)
                    finally:
                        # Отмена/краш во время ожидания слота: heartbeat не
                        # должен пережить сборку.
                        if heartbeat is not None:
                            heartbeat.cancel()
                else:
                    # Copy-only variant (engine: none — e.g. pptx/reveal): the
                    # rendered file IS the deliverable, there is nothing to
                    # compile with LaTeX. Mark a successful "build" so the doc
                    # isn't stuck red; the checks below still decide warn/ok.
                    skip_msg = (
                        f"[compile:{compile_id}] this variant needs no compilation "
                        f"(engine: none) — the file is used as is"
                        if current_interface_language() is Lang.en
                        else f"[compile:{compile_id}] вариант не требует компиляции "
                        f"(engine: none) — файл используется как есть"
                    )
                    log_lines.append(skip_msg)
                    self._log_bus.publish(compile_id, skip_msg)
                    success = True

                    # Office-файл (pptx-вариант ИЛИ произвольный кастомный
                    # аплоад): конвертируем в соседний PDF для встроенного
                    # предпросмотра (managed-Gotenberg/LibreOffice). Best-effort:
                    # без Docker/образа сборка всё равно успешна — превью просто
                    # останется карточкой скачивания. Уже-PDF — просто считаем
                    # страницы без конвертации; неизвестный формат — превью
                    # недоступно (pages_val остаётся None), это не ошибка.
                    source_ext = Path(source_file).suffix.lower()
                    if source_ext == ".pdf":
                        pages_val = _pdf_page_count(project_folder / source_file)
                    elif source_ext in CONVERTIBLE_OFFICE_EXTS:
                        pages_val = await self._convert_office_preview(
                            compile_id=compile_id,
                            project_folder=project_folder,
                            source_file=source_file,
                            log_lines=log_lines,
                        )
            except asyncio.CancelledError:
                cancelled = True
                success = False
                cancel_msg = "[cancelled] build cancelled by user"
                log_lines.append(cancel_msg)
                self._log_bus.publish(compile_id, cancel_msg)
            except Exception as exc:
                crashed_exc = exc
                success = False
                err_msg = f"[error] compile task crashed: {exc}"
                log_lines.append(err_msg)
                self._log_bus.publish(compile_id, err_msg)
                logger.exception("compile task crashed", compile_id=str(compile_id))

            full_log = "\n".join(log_lines)
            finished_at = datetime.now(tz=timezone.utc)

            if cancelled:
                final_status = CompileStatus.cancelled
                check_results: list[CheckResult] = []
            elif crashed_exc is not None:
                final_status = CompileStatus.failure
                check_results = []
            else:
                # Live heartbeat: the docker phase is done, but checks (incl. the
                # LanguageTool HTTP call) can take a few seconds while the bus is
                # still open. Publishing a line keeps the SSE stream from going
                # silent so the client's 90s stall watchdog doesn't fire on an
                # otherwise-healthy run.
                self._log_bus.publish(
                    compile_id,
                    "[checks] running checks…"
                    if current_interface_language() is Lang.en
                    else "[checks] выполняются проверки…",
                )

                # Pack-author may declare per-document check overrides in version.yaml
                # (e.g. presentation skips formatting GOST rules). Pull that override
                # out of the matching DocumentDefinition and apply it as the
                # pack-level doc layer.
                doc_def = next((d for d in version.documents if d.id == def_id), None)
                doc_def_checks = doc_def.checks if doc_def is not None else ChecksOverride()

                # Скоупинг правил (`applies_to`) в паке перечисляет id
                # ОПРЕДЕЛЕНИЙ — резолвим по def_id, а не по id инстанса.
                rules_with_severity = self._check_resolution_service.resolve(
                    rules=list(version.rules),
                    doc_id=def_id,
                    version_cfg=version.checks_config,
                    doc_definition_checks=doc_def_checks,
                    project_override=project_checks_override,
                    doc_override=doc_checks_override,
                    user_override=ChecksOverride(),
                )
                # LanguageTool is auto-managed: if any resolved rule uses the
                # `external` engine, lazily bring the container up (on a free port)
                # before checks run. No-op if it's already running; silently skips
                # if Docker is down or the image isn't installed. The engine reads
                # the resolved endpoint from the manager. Skipped entirely in
                # custom_mode — `external` is force-suppressed there anyway.
                if not custom_mode and any(rule.engine == CheckEngine.external for rule, _ in rules_with_severity):
                    await self._lt_manager.ensure_running(resolve_active_languagetool_image(self._settings_repo))

                # run_all does blocking IO (file reads, and the LanguageTool HTTP
                # call for the `external` engine). Offload to a worker thread so the
                # event loop — and the live SSE log stream for this compile — keep
                # running while checks execute.
                check_results = await asyncio.to_thread(
                    self._check_runner.run_all,
                    rules_with_severity=rules_with_severity,
                    project_folder=project_folder,
                    doc_id=doc_id,
                    source_file=source_file,
                    log_content=full_log if not success else None,
                    base_dir=base_dir,
                    custom_mode=custom_mode,
                )
                # Drop individually-ignored findings. Resolution above already
                # removes declared rules listed in `disabled`, but dynamic-id
                # findings (e.g. LanguageTool's `lt:<RULE>`) aren't declared in the
                # catalog, so the user's "Игнорировать" on a specific finding is
                # applied here by matching the produced result's rule_id.
                ignored_ids = (
                    set(version.checks_config.disabled)
                    | set(doc_def_checks.disabled)
                    | set(project_checks_override.disabled)
                    | set(doc_checks_override.disabled)
                )
                if ignored_ids:
                    check_results = [r for r in check_results if r.rule_id not in ignored_ids]
                final_status = CompileStatus.success if success else CompileStatus.failure

            has_errors = any(r.severity == CheckSeverity.err for r in check_results)
            has_warnings = any(r.severity == CheckSeverity.warn for r in check_results)

            final_record = CompileRecord(
                id=compile_id,
                project_folder=project_folder,
                doc_id=doc_id,
                engine=engine,
                status=final_status,
                started_at=running_record.started_at,
                finished_at=finished_at,
                log=full_log,
                output_path=None,
                check_results=check_results,
                pages=pages_val,
                words=words_val,
                chars=chars_val,
            )
            self._compile_repo.save(final_record)

            if final_status in (CompileStatus.cancelled, CompileStatus.failure) or has_errors:
                new_doc_status = DocumentStatus.err
            elif has_warnings:
                new_doc_status = DocumentStatus.warn
            else:
                new_doc_status = DocumentStatus.ok

            try:
                updated_project = self._project_repo.get(project_folder)
                if updated_project is not None:
                    updated_docs = [
                        replace(d, status=new_doc_status, last_compile_id=compile_id) if d.id == doc_id else d
                        for d in updated_project.documents
                    ]
                    updated_project.documents[:] = updated_docs
                    self._project_repo.save(updated_project)
            except Exception as exc:
                logger.warning(
                    "compile task: failed to update document status",
                    compile_id=str(compile_id),
                    exc=str(exc),
                )

            if final_status == CompileStatus.cancelled:
                kind = ChangeLogKind.compile_fail
                summary = f"Compile cancelled for {doc_id}"
            else:
                kind = ChangeLogKind.compile_ok if success else ChangeLogKind.compile_fail
                summary = f"Compile {'succeeded' if success else 'failed'} for {doc_id}"
            try:
                self._changelog_repo.append(
                    project_folder,
                    ChangeLogEntry(
                        id=uuid.uuid4(),
                        at=finished_at,
                        kind=kind,
                        doc_id=doc_id,
                        summary=summary,
                        note=None,
                    ),
                )
            except Exception as exc:
                logger.warning(
                    "compile task: failed to append changelog",
                    compile_id=str(compile_id),
                    exc=str(exc),
                )

            # ProjectVCS: on a successful build, snapshot the sources (and the
            # finalized PDF if track_pdf is on). Runs after the terminal record is
            # persisted and the PDF has been moved next to its source, under the
            # shared per-folder lock so it can't race a concurrent snapshot.
            if final_status == CompileStatus.success:
                await self._vcs_commit_on_success(project_folder, doc_id, pages_val)
                # Keep this PDF for visual diff against later builds.
                archive_compiled_pdf(project_folder, doc_id, compile_id, source_file)

            logger.debug(
                "compile task finished",
                compile_id=str(compile_id),
                status=final_status,
                doc_id=doc_id,
            )
        finally:
            # Close the bus only now — the terminal record is persisted, so the
            # SSE backfill yields the correct __STATUS__. unregister here too so
            # a crash mid-finalise still frees the in-memory slot.
            self._log_bus.close(compile_id)
            self._compile_runner.unregister(compile_id)

    def _resolve_compile_limit(self, user_settings: dict[str, object]) -> int:
        """Сколько сборок пускать одновременно — ровно то же число, что в Настройках."""
        stored = user_settings.get("max_concurrent_compiles")
        if isinstance(stored, int | str):
            limit = int(stored)
        else:
            capacity = self._capacity_probe.detect() if self._capacity_probe else SystemCapacity()
            limit = default_max_concurrent_compiles(capacity)
        return max(MIN_CONCURRENT_COMPILES, min(limit, MAX_CONCURRENT_COMPILES_CEILING))

    async def _queue_heartbeat(self, compile_id: uuid.UUID, log_lines: list[str]) -> None:
        """Периодический «я жив» ожидающей в очереди сборки.

        Пока сборка ждёт слот, docker молчит — без этих строк фронтовый сторож
        тишины (90с) ложно пометил бы её зависшей. Задача отменяется сразу
        после получения слота (или вместе со сборкой).
        """
        while True:
            await asyncio.sleep(_QUEUE_HEARTBEAT_INTERVAL_S)
            msg = (
                f"[queue] still queued — {self._compile_limiter.active} build(s) running…"
                if current_interface_language() is Lang.en
                else f"[queue] всё ещё в очереди — выполняется сборок: {self._compile_limiter.active}…"
            )
            log_lines.append(msg)
            self._log_bus.publish(compile_id, msg)

    async def _vcs_commit_on_success(self, project_folder: Path, doc_id: str, pages: int | None) -> None:
        """Record a `compile` snapshot in the project's VCS store. Best-effort:
        a VCS failure must never affect the build's outcome."""
        try:
            project = self._project_repo.get(project_folder)
            if project is None or not self._vcs_service.is_available(project):
                return
            settings = VcsSettings.from_meta(project.meta)
            if not settings.auto_commit_on_compile:
                return
            pages_part = f" · {pages} стр." if pages else ""
            message = f"Сборка: {doc_id}{pages_part}"
            async with self._vcs_locks.for_folder(project_folder):
                if not self._vcs_service.is_initialized(project):
                    await asyncio.to_thread(self._vcs_service.init, project, list(DEFAULT_VCS_EXCLUDE))
                await asyncio.to_thread(
                    lambda: self._vcs_service.commit(
                        project,
                        message=message,
                        kind=VcsCommitKind.compile,
                        include_pdf=settings.track_pdf,
                    )
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("vcs compile-commit failed", doc_id=doc_id, exc=str(exc))
