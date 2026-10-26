"""Тело compile-задачи: разбор потока сборки, очередь, copy-only ветка и проверки.

Перенесено из TriggerCompileUC без изменения сообщений и их порядка.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from hse_doc_studio.core.checks.protocols import ICheckRunner
from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.core.jobs.entities import CheckPlan, CompileJobPayload
from hse_doc_studio.core.jobs.office import REASON_WRITE_FAILED, OfficeConvertStatus
from hse_doc_studio.core.jobs.outputs import IJobOutputs
from hse_doc_studio.core.jobs.protocols import JobLogSink
from hse_doc_studio.core.language_check import ILanguageCheckService
from hse_doc_studio.core.office import CONVERTIBLE_OFFICE_EXTS, IOfficeConvertService, sibling_pdf_path
from hse_doc_studio.core.system_capacity import (
    MAX_CONCURRENT_COMPILES_CEILING,
    MIN_CONCURRENT_COMPILES,
    ISystemCapacityProbe,
    SystemCapacity,
    default_max_concurrent_compiles,
)
from hse_doc_studio.core.value_objects import CheckResult
from hse_doc_studio.infra.compile.concurrency import CompileConcurrencyLimiter
from hse_doc_studio.infra.compile.docker_compile_executor import (
    _SENTINEL_DONE,
    _SENTINEL_FAILED,
    _SENTINEL_PAGES,
    _SENTINEL_WORDS,
)
from hse_doc_studio.infra.jobs.office_convert import convert_office_to_sibling

# Пока сборка ждёт слот в очереди, поток логов пустой — фронтовый сторож
# (90с тишины → «похоже, зависла») сработал бы ложно. Heartbeat каждые ~25с
# держит SSE-поток живым, сколько бы очередь ни длилась.
QUEUE_HEARTBEAT_INTERVAL_S = 25.0


def pdf_page_count(pdf_path: Path) -> int | None:
    """Число страниц PDF (для pptx-предпросмотра = число слайдов)."""
    try:
        from pypdf import PdfReader  # noqa: PLC0415 — тяжёлый импорт только по месту

        with pdf_path.open("rb") as fh:
            return len(PdfReader(fh).pages)
    except Exception:  # noqa: BLE001 — счётчик страниц не критичен
        return None


def parse_words_sentinel(line: str) -> tuple[int | None, int | None]:
    """Parse a `__WORDS__:<words>:<chars>` sentinel into (words, chars)."""
    payload = line[len(_SENTINEL_WORDS) :]
    words_str, _sep, chars_str = payload.partition(":")
    try:
        return int(words_str), int(chars_str)
    except ValueError:
        return None, None


@dataclass
class BuildState:
    """Что накопила фаза сборки; без `__FAILED__` в потоке сборка считается успешной."""

    success: bool = True
    pages: int | None = None
    words: int | None = None
    chars: int | None = None


async def consume_build_stream(lines: AsyncIterator[str], log: JobLogSink, state: BuildState) -> None:
    """Разбирает поток executor: сентинелы уходят в `state`, остальное в лог."""
    async for line in lines:
        if line == _SENTINEL_DONE:
            state.success = True
        elif line == _SENTINEL_FAILED:
            state.success = False
        elif line.startswith(_SENTINEL_PAGES):
            try:
                state.pages = int(line[len(_SENTINEL_PAGES) :])
            except ValueError:
                state.pages = None
        elif line.startswith(_SENTINEL_WORDS):
            state.words, state.chars = parse_words_sentinel(line)
        else:
            log.emit(line)


def resolve_compile_limit(user_settings: dict[str, object], capacity_probe: ISystemCapacityProbe | None) -> int:
    """Сколько сборок пускать одновременно — ровно то же число, что в Настройках.

    Лимит читается из СЫРЫХ настроек, а пользователь его обычно не трогал —
    без зонда очередь работала бы по старой константе 2, хотя в Настройках
    показано посчитанное по машине значение.
    """
    stored = user_settings.get("max_concurrent_compiles")
    if isinstance(stored, int | str):
        limit = int(stored)
    else:
        capacity = capacity_probe.detect() if capacity_probe else SystemCapacity()
        limit = default_max_concurrent_compiles(capacity)
    return max(MIN_CONCURRENT_COMPILES, min(limit, MAX_CONCURRENT_COMPILES_CEILING))


class CapacityGate:
    """Глобальный лимит одновременных docker-сборок с сообщениями об очереди.

    «Собрать всё» ставит лишние сборки в ОЧЕРЕДЬ вместо запуска десятков
    texlive-контейнеров разом. Лимит живая настройка (Settings → Компилятор) и
    читается на каждый захват. Отмена ожидающей сборки работает как обычно.
    """

    def __init__(
        self,
        limiter: CompileConcurrencyLimiter,
        capacity_probe: ISystemCapacityProbe | None,
        heartbeat_interval_s: float | None = None,
    ) -> None:
        self._limiter = limiter
        self._capacity_probe = capacity_probe
        self._heartbeat_interval_s = heartbeat_interval_s

    @asynccontextmanager
    async def slot(self, user_settings: dict[str, object], log: JobLogSink) -> AsyncIterator[None]:
        compile_limit = resolve_compile_limit(user_settings, self._capacity_probe)
        heartbeat: asyncio.Task[None] | None = None
        if self._limiter.active >= compile_limit:
            log.emit(
                f"[queue] waiting for a free build slot (limit: {compile_limit} concurrent builds)…"
                if current_interface_language() is Lang.en
                else f"[queue] ожидание свободного слота сборки (лимит: {compile_limit} одновременно)…"
            )
            heartbeat = asyncio.create_task(self._heartbeat(log))
        try:
            async with self._limiter.slot(compile_limit):
                if heartbeat is not None:
                    heartbeat.cancel()
                    heartbeat = None
                    log.emit(
                        "[queue] build slot acquired — starting the build"
                        if current_interface_language() is Lang.en
                        else "[queue] слот получен — сборка начинается"
                    )
                yield
        finally:
            # Отмена/краш во время ожидания слота: heartbeat не должен пережить сборку.
            if heartbeat is not None:
                heartbeat.cancel()

    async def _heartbeat(self, log: JobLogSink) -> None:
        """Периодический «я жив» ожидающей в очереди сборки.

        Пока сборка ждёт слот, docker молчит — без этих строк фронтовый сторож
        тишины (90с) ложно пометил бы её зависшей. Задача отменяется сразу
        после получения слота (или вместе со сборкой).
        """
        while True:
            # Модульная константа читается в момент ожидания: тесты подменяют её без пересборки раннера.
            interval = QUEUE_HEARTBEAT_INTERVAL_S if self._heartbeat_interval_s is None else self._heartbeat_interval_s
            await asyncio.sleep(interval)
            log.emit(
                f"[queue] still queued — {self._limiter.active} build(s) running…"
                if current_interface_language() is Lang.en
                else f"[queue] всё ещё в очереди — выполняется сборок: {self._limiter.active}…"
            )


async def run_copy_only(  # noqa: PLR0913
    job_id: UUID,
    payload: CompileJobPayload,
    workspace: Path,
    log: JobLogSink,
    state: BuildState,
    converter: IOfficeConvertService,
    outputs: IJobOutputs,
    resolve_office_image: Callable[[], str],
) -> None:
    """Copy-only вариант (engine: none, например pptx/reveal): файл и есть артефакт.

    Сборка помечается успешной, чтобы документ не застрял красным; проверки
    потом решают warn/ok. Office-файл (pptx-вариант ИЛИ произвольный кастомный
    аплоад) конвертируется в соседний PDF для встроенного предпросмотра, это
    best-effort: без Docker/образа сборка всё равно успешна. Уже-PDF — просто
    считаем страницы; неизвестный формат — превью недоступно, это не ошибка.
    """
    log.emit(
        f"[compile:{job_id}] this variant needs no compilation (engine: none) — the file is used as is"
        if current_interface_language() is Lang.en
        else f"[compile:{job_id}] вариант не требует компиляции (engine: none) — файл используется как есть"
    )
    state.success = True

    source_ext = Path(payload.source_file).suffix.lower()
    if source_ext == ".pdf":
        state.pages = pdf_page_count(workspace / payload.source_file)
    elif source_ext in CONVERTIBLE_OFFICE_EXTS:
        state.pages = await _convert_office_preview(
            job_id, payload.source_file, workspace, log, converter, outputs, resolve_office_image
        )


async def _convert_office_preview(  # noqa: PLR0913
    job_id: UUID,
    source_file: str,
    workspace: Path,
    log: JobLogSink,
    converter: IOfficeConvertService,
    outputs: IJobOutputs,
    resolve_office_image: Callable[[], str],
) -> int | None:
    """office-файл → соседний PDF-предпросмотр; возвращает число страниц или None.

    PDF кладётся рядом с исходником (presentation.pptx → presentation.pdf) —
    detail-эндпоинт отдаёт его как `preview_file`, встроенный вьювер показывает
    PDF вместо карточки скачивания. Любой отказ (нет Docker, не установлен образ
    Gotenberg, ошибка LibreOffice) не роняет сборку; исключение конвертера
    наверх не прячется, как и раньше.
    """
    en = current_interface_language() is Lang.en
    output_path = sibling_pdf_path(source_file)
    log.emit(
        f"[compile:{job_id}] converting to PDF for preview (Gotenberg/LibreOffice)…"
        if en
        else f"[compile:{job_id}] конвертация в PDF для предпросмотра (Gotenberg/LibreOffice)…"
    )
    result = await convert_office_to_sibling(
        converter,
        outputs,
        workspace,
        source_file,
        output_path,
        image=resolve_office_image(),
        want_pages=True,
    )
    if result.status is not OfficeConvertStatus.ok:
        if result.reason_code == REASON_WRITE_FAILED:
            log.emit(f"[compile:{job_id}] preview write failed: {result.detail}")
        else:
            log.emit(
                f"[compile:{job_id}] PDF preview unavailable (is the Gotenberg image installed? "
                f"`docker pull gotenberg/gotenberg:8`) — the pptx itself is still the deliverable"
                if en
                else f"[compile:{job_id}] PDF-предпросмотр недоступен (установлен ли образ Gotenberg? "
                f"`docker pull gotenberg/gotenberg:8`) — сам pptx остаётся артефактом"
            )
        return None
    pages = result.pages
    name = Path(output_path).name
    log.emit(
        f"[compile:{job_id}] preview PDF ready: {name}" + (f" ({pages} slides)" if pages else "")
        if en
        else f"[compile:{job_id}] PDF-предпросмотр готов: {name}" + (f" ({pages} слайдов)" if pages else "")
    )
    return pages


async def run_checks(  # noqa: PLR0913
    plan: CheckPlan,
    payload: CompileJobPayload,
    workspace: Path,
    log: JobLogSink,
    outcome_success: bool,
    check_runner: ICheckRunner,
    lt_manager: ILanguageCheckService,
    resolve_lt_image: Callable[[], str],
) -> list[CheckResult]:
    """Фаза проверок после сборки; идёт вне охраны сборки, как и раньше."""
    # Live heartbeat: docker-фаза закончилась, а проверки (включая HTTP-вызов
    # LanguageTool) могут идти несколько секунд при открытой шине. Строка не даёт
    # SSE-потоку замолчать, чтобы 90-секундный сторож клиента не сработал.
    log.publish_only(
        "[checks] running checks…" if current_interface_language() is Lang.en else "[checks] выполняются проверки…"
    )
    # LanguageTool управляется автоматически: если правило использует движок
    # `external`, контейнер поднимается лениво перед проверками. В custom_mode
    # `external` подавляется принудительно, поэтому там контейнер не нужен.
    if plan.needs_languagetool and not payload.custom_mode:
        await lt_manager.ensure_running(resolve_lt_image())

    # run_all читает файлы и ходит по HTTP в LanguageTool: уносим в поток, чтобы
    # цикл событий и живой SSE-лог этой сборки не вставали на время проверок.
    check_results = await asyncio.to_thread(
        check_runner.run_all,
        rules_with_severity=list(plan.rules_with_severity),
        project_folder=workspace,
        doc_id=payload.doc_id,
        source_file=payload.source_file,
        log_content=log.text() if not outcome_success else None,
        base_dir=payload.base_dir,
        custom_mode=payload.custom_mode,
    )
    # Отдельно проигнорированные находки снимаем здесь: id вида `lt:<RULE>`
    # в каталоге не объявлены, поэтому сопоставляем с rule_id результата.
    if plan.ignored_rule_ids:
        check_results = [r for r in check_results if r.rule_id not in plan.ignored_rule_ids]
    return check_results
