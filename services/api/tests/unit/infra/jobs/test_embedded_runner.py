"""EmbeddedCompileRunner и compile_body: перенос тела _run_compile_task без изменения поведения."""

from __future__ import annotations

import asyncio
import io
import threading
from collections.abc import AsyncIterator, Callable
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from hse_doc_studio.core.compile.errors import DockerUnavailableError, ImageMissingError
from hse_doc_studio.core.enums import CheckSeverity
from hse_doc_studio.core.i18n import set_interface_language
from hse_doc_studio.core.jobs.entities import BuildOutcome, CompileJobPayload, CompileResult, JobSpec
from hse_doc_studio.core.jobs.enums import JobStatus
from hse_doc_studio.core.jobs.protocols import JobRunContext
from hse_doc_studio.core.system_capacity import (
    MAX_CONCURRENT_COMPILES_CEILING,
    MIN_CONCURRENT_COMPILES,
    SystemCapacity,
    default_max_concurrent_compiles,
)
from hse_doc_studio.core.value_objects import CheckResult
from hse_doc_studio.infra.compile.concurrency import CompileConcurrencyLimiter
from hse_doc_studio.infra.jobs.compile_body import parse_words_sentinel, resolve_compile_limit
from hse_doc_studio.infra.jobs.embedded_runner import EmbeddedCompileRunner
from hse_doc_studio.infra.jobs.outputs import LocalJobOutputs
from pypdf import PdfWriter

from tests.unit.core.jobs.samples import JOB_ID, make_compile_payload, make_compile_spec


def _pdf_bytes(pages: int) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=100, height=100)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


class FakeLog:
    """Различает emit (запись и шина) и publish_only (только шина), как настоящий приёмник."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.published: list[str] = []

    def emit(self, line: str) -> None:
        self.lines.append(line)
        self.published.append(line)

    def publish_only(self, line: str) -> None:
        self.published.append(line)

    def text(self) -> str:
        return "\n".join(self.lines)


class FakeExecutor:
    def __init__(self, lines: list[str] | None = None) -> None:
        self.lines = lines if lines is not None else ["[compile] building", "__DONE__"]
        self.calls: list[dict[str, Any]] = []

    async def run(self, **kwargs: Any) -> AsyncIterator[str]:
        self.calls.append(kwargs)
        return self._stream()

    async def _stream(self) -> AsyncIterator[str]:
        for line in self.lines:
            yield line


class Harness:
    def __init__(self, tmp_path: Path, *, settings: dict[str, object] | None = None) -> None:
        self.workspace = tmp_path
        self.log = FakeLog()
        self.executor = FakeExecutor()
        self.image_manager = MagicMock()
        self.image_manager.docker_status = AsyncMock(return_value=MagicMock(available=True))
        self.image_manager.inspect = AsyncMock(return_value=MagicMock())
        self.converter = MagicMock()
        self.converter.convert_to_pdf = AsyncMock(return_value=None)
        self.check_runner = MagicMock()
        self.check_runner.run_all.return_value = []
        self.lt_manager = MagicMock()
        self.lt_manager.ensure_running = AsyncMock(return_value=None)
        self.settings_repo = MagicMock()
        self.settings_repo.get = AsyncMock(side_effect=lambda: dict(self.settings))
        self.settings: dict[str, object] = {"max_concurrent_compiles": 2, **(settings or {})}
        self.capacity_probe = MagicMock()
        self.limiter = CompileConcurrencyLimiter()
        self.image = "texlive:one"
        self.processes: list[object] = []
        self.runner = self.make_runner()

    async def _resolve_image(self) -> str:
        return self.image

    async def _resolve_lt_image(self) -> str:
        return "lt:image"

    async def _resolve_office_image(self) -> str:
        return "gotenberg:active"

    def make_runner(self, heartbeat_interval_s: float = 25.0) -> EmbeddedCompileRunner:
        return EmbeddedCompileRunner(
            executor=self.executor,  # type: ignore[arg-type]
            image_manager=self.image_manager,
            office_convert=self.converter,
            check_runner=self.check_runner,
            lt_manager=self.lt_manager,
            settings_repo=self.settings_repo,
            capacity_probe=self.capacity_probe,
            limiter=self.limiter,
            outputs=LocalJobOutputs(),
            resolve_image=self._resolve_image,
            resolve_lt_image=self._resolve_lt_image,
            resolve_office_image=self._resolve_office_image,
            heartbeat_interval_s=heartbeat_interval_s,
        )

    @property
    def ctx(self) -> JobRunContext:
        return JobRunContext(log=self.log, workspace=self.workspace, on_process=self.processes.append)

    def spec(self, **payload_changes: Any) -> JobSpec:
        payload = replace(make_compile_payload(), **payload_changes)
        return replace(make_compile_spec(local_root=self.workspace), payload=payload)


def _copy_only(**changes: Any) -> dict[str, Any]:
    return {"needs_compile": False, "source_file": "tz/_custom/ТЗ.docx", **changes}


@pytest.fixture(autouse=True)
def _language_ru() -> None:
    set_interface_language("ru")


# --- разбор потока ---


def test__parse_words_sentinel__well_formed_line__roundtrips_word_and_char_counts() -> None:
    assert parse_words_sentinel("__WORDS__:24:135") == (24, 135)


@pytest.mark.parametrize("line", ["__WORDS__:bad", "__WORDS__:24", "__WORDS__:"])
def test__parse_words_sentinel__garbage_line__returns_none_pair(line: str) -> None:
    assert parse_words_sentinel(line) == (None, None)


@pytest.mark.parametrize(
    ("lines", "success", "pages", "words", "chars"),
    [
        (["line", "__DONE__"], True, None, None, None),
        (["line"], True, None, None, None),
        (["line", "__FAILED__"], False, None, None, None),
        (["__PAGES__:12", "__WORDS__:10:50", "__DONE__"], True, 12, 10, 50),
        (["__PAGES__:abc", "__WORDS__:x:y", "__DONE__"], True, None, None, None),
        (["__FAILED__", "__DONE__"], True, None, None, None),
    ],
)
async def test__run_build__stream_sentinels__parsed_into_outcome_and_kept_out_of_log(
    tmp_path: Path, lines: list[str], success: bool, pages: int | None, words: int | None, chars: int | None
) -> None:
    h = Harness(tmp_path)
    h.executor.lines = lines

    outcome = await h.runner.run_build(h.spec(), h.ctx)

    assert (outcome.success, outcome.pages, outcome.words, outcome.chars) == (success, pages, words, chars)
    assert outcome.status is (JobStatus.succeeded if success else JobStatus.failed)
    assert all(not line.startswith("__") for line in h.log.lines)


async def test__run_build__docker__passes_executor_arguments_and_process_callback(tmp_path: Path) -> None:
    h = Harness(tmp_path)

    await h.runner.run_build(h.spec(), h.ctx)

    call = h.executor.calls[0]
    assert call["project_folder"] == tmp_path
    assert call["source_file"] == "tz/main.tex"
    assert call["engine"] == "xelatex"
    assert call["doc_id"] == "tz"
    assert call["compile_id"] == JOB_ID
    assert call["image"] == "texlive:one"
    call["on_process_started"]("process")
    assert h.processes == ["process"]


@pytest.mark.parametrize(
    ("settings", "expected"),
    [({}, 5), ({"latex_passes": 1}, 3), ({"latex_passes": "9"}, 9), ({"latex_passes": 3}, 3)],
)
async def test__run_build__latex_passes__user_setting_wins_with_floor_of_three(
    tmp_path: Path, settings: dict[str, object], expected: int
) -> None:
    h = Harness(tmp_path, settings=settings)

    await h.runner.run_build(h.spec(), h.ctx)

    assert h.executor.calls[0]["max_iterations"] == expected


async def test__run_build__non_numeric_latex_passes__raises_before_any_build_work(tmp_path: Path) -> None:
    h = Harness(tmp_path, settings={"latex_passes": "many"})

    with pytest.raises(ValueError, match="many"):
        await h.runner.run_build(h.spec(), h.ctx)

    assert h.executor.calls == []
    assert h.log.lines == []


async def test__run_build__finished_at_captured_when_build_ends(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    before = datetime.now(tz=timezone.utc)

    outcome = await h.runner.run_build(h.spec(), h.ctx)

    assert before <= outcome.finished_at <= datetime.now(tz=timezone.utc)


# --- очередь ---


@pytest.mark.parametrize(
    ("stored", "expected"),
    [(100, MAX_CONCURRENT_COMPILES_CEILING), (0, MIN_CONCURRENT_COMPILES), ("3", 3), (-4, MIN_CONCURRENT_COMPILES)],
)
def test__resolve_compile_limit__stored_value__clamped_to_bounds(stored: object, expected: int) -> None:
    assert resolve_compile_limit({"max_concurrent_compiles": stored}, None) == expected


def test__resolve_compile_limit__not_stored_and_no_probe__uses_unknown_machine_default() -> None:
    assert resolve_compile_limit({}, None) == default_max_concurrent_compiles(SystemCapacity())


def test__resolve_compile_limit__not_stored__uses_probe_snapshot() -> None:
    probe = MagicMock()
    probe.detect.return_value = SystemCapacity(cpu_count=16, total_ram_mb=32 * 1024)

    assert resolve_compile_limit({}, probe) == default_max_concurrent_compiles(probe.detect.return_value)


async def test__run_build__free_slot__no_queue_messages(tmp_path: Path) -> None:
    h = Harness(tmp_path)

    await h.runner.run_build(h.spec(), h.ctx)

    assert h.log.lines == ["[compile] building"]


async def _wait_for(condition: Callable[[], bool], timeout_s: float = 2.0) -> None:
    async with asyncio.timeout(timeout_s):
        while not condition():
            await asyncio.sleep(0.005)


async def _hold_slot(limiter: CompileConcurrencyLimiter, limit: int) -> tuple[asyncio.Event, asyncio.Task[None]]:
    release = asyncio.Event()
    acquired = asyncio.Event()

    async def hold() -> None:
        async with limiter.slot(limit):
            acquired.set()
            await release.wait()

    task = asyncio.create_task(hold())
    await acquired.wait()
    return release, task


async def test__run_build__limit_reached__waits_with_heartbeat_then_starts(tmp_path: Path) -> None:
    h = Harness(tmp_path, settings={"max_concurrent_compiles": 1})
    h.runner = h.make_runner(heartbeat_interval_s=0.01)
    release, holder = await _hold_slot(h.limiter, 1)
    h.image = "texlive:before"

    build = asyncio.create_task(h.runner.run_build(h.spec(), h.ctx))
    await _wait_for(lambda: any("всё ещё в очереди" in line for line in h.log.lines))
    assert h.log.lines[0] == "[queue] ожидание свободного слота сборки (лимит: 1 одновременно)…"
    assert h.executor.calls == []
    h.image = "texlive:after"
    release.set()
    await holder
    await build

    assert h.log.lines[h.log.lines.index("[queue] слот получен — сборка начинается") + 1] == "[compile] building"
    # Образ выбирается заново уже после ожидания слота.
    assert h.executor.calls[0]["image"] == "texlive:after"
    # Heartbeat остановлен в момент получения слота.
    count = sum("всё ещё в очереди" in line for line in h.log.lines)
    await asyncio.sleep(0.05)
    assert sum("всё ещё в очереди" in line for line in h.log.lines) == count
    assert h.limiter.active == 0


async def test__run_build__queue_messages__english_when_interface_language_is_en(tmp_path: Path) -> None:
    set_interface_language("en")
    h = Harness(tmp_path, settings={"max_concurrent_compiles": 1})
    h.runner = h.make_runner(heartbeat_interval_s=0.01)
    release, holder = await _hold_slot(h.limiter, 1)

    build = asyncio.create_task(h.runner.run_build(h.spec(), h.ctx))
    await _wait_for(lambda: any("still queued" in line for line in h.log.lines))
    release.set()
    await holder
    await build

    assert h.log.lines[0] == "[queue] waiting for a free build slot (limit: 1 concurrent builds)…"
    assert "[queue] still queued — 1 build(s) running…" in h.log.lines
    assert "[queue] build slot acquired — starting the build" in h.log.lines


async def test__run_build__cancelled_while_queued__heartbeat_stops(tmp_path: Path) -> None:
    h = Harness(tmp_path, settings={"max_concurrent_compiles": 1})
    h.runner = h.make_runner(heartbeat_interval_s=0.01)
    release, holder = await _hold_slot(h.limiter, 1)

    build = asyncio.create_task(h.runner.run_build(h.spec(), h.ctx))
    await _wait_for(lambda: any("всё ещё в очереди" in line for line in h.log.lines))
    build.cancel()
    with pytest.raises(asyncio.CancelledError):
        await build
    count = len(h.log.lines)
    await asyncio.sleep(0.05)

    assert len(h.log.lines) == count
    assert h.executor.calls == []
    release.set()
    await holder


async def test__run_build__executor_raises__slot_released_and_exception_propagates(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    h.executor.run = AsyncMock(side_effect=RuntimeError("docker exploded"))  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="docker exploded"):
        await h.runner.run_build(h.spec(), h.ctx)

    assert h.limiter.active == 0


# --- preflight ---


async def test__preflight__copy_only__touches_neither_docker_nor_image(tmp_path: Path) -> None:
    h = Harness(tmp_path)

    await h.runner.preflight(h.spec(**_copy_only()))

    h.image_manager.docker_status.assert_not_awaited()
    h.image_manager.inspect.assert_not_awaited()


async def test__preflight__docker_down__raises_with_detail_reason_and_gid(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    h.image_manager.docker_status.return_value = MagicMock(
        available=False, detail="no socket", reason="socket_permission", socket_gid=999
    )

    with pytest.raises(DockerUnavailableError) as raised:
        await h.runner.preflight(h.spec())

    assert str(raised.value) == "no socket"
    assert (raised.value.reason, raised.value.socket_gid) == ("socket_permission", 999)
    h.image_manager.inspect.assert_not_awaited()


async def test__preflight__docker_down_without_detail__localized_default_text(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    h.image_manager.docker_status.return_value = MagicMock(available=False, detail=None, reason=None, socket_gid=None)

    with pytest.raises(DockerUnavailableError) as raised:
        await h.runner.preflight(h.spec())

    assert str(raised.value) == "Демон Docker недоступен"
    assert raised.value.reason is None


async def test__preflight__image_not_installed__raises_image_missing_for_active_image(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    h.image_manager.inspect.return_value = None

    with pytest.raises(ImageMissingError) as raised:
        await h.runner.preflight(h.spec())

    assert raised.value.image == "texlive:one"
    h.image_manager.inspect.assert_awaited_once_with("texlive:one")


async def test__preflight__everything_ready__passes(tmp_path: Path) -> None:
    h = Harness(tmp_path)

    await h.runner.preflight(h.spec())

    h.image_manager.docker_status.assert_awaited_once()


# --- copy-only ---


async def test__run_build__copy_only_unknown_extension__success_without_conversion_or_pages(tmp_path: Path) -> None:
    h = Harness(tmp_path)

    outcome = await h.runner.run_build(h.spec(**_copy_only(source_file="tz/_custom/file.xyz")), h.ctx)

    assert outcome.success is True
    assert outcome.pages is None
    assert h.log.lines == [
        f"[compile:{JOB_ID}] вариант не требует компиляции (engine: none) — файл используется как есть"
    ]
    h.converter.convert_to_pdf.assert_not_awaited()
    assert h.executor.calls == []


async def test__run_build__copy_only_pdf__counts_pages_without_conversion(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    (tmp_path / "tz").mkdir()
    (tmp_path / "tz" / "doc.pdf").write_bytes(_pdf_bytes(4))

    outcome = await h.runner.run_build(h.spec(**_copy_only(source_file="tz/doc.pdf")), h.ctx)

    assert outcome.pages == 4
    h.converter.convert_to_pdf.assert_not_awaited()


async def test__run_build__copy_only_pdf_unreadable__pages_none(tmp_path: Path) -> None:
    h = Harness(tmp_path)

    outcome = await h.runner.run_build(h.spec(**_copy_only(source_file="tz/missing.pdf")), h.ctx)

    assert outcome.success is True
    assert outcome.pages is None


async def test__run_build__copy_only_office__converts_with_active_image_and_logs_ru(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    (tmp_path / "tz" / "_custom").mkdir(parents=True)
    h.converter.convert_to_pdf.return_value = _pdf_bytes(3)

    outcome = await h.runner.run_build(h.spec(**_copy_only()), h.ctx)

    assert outcome.pages == 3
    assert outcome.success is True
    assert (tmp_path / "tz/_custom/ТЗ.pdf").read_bytes() == _pdf_bytes(3)
    h.converter.convert_to_pdf.assert_awaited_once_with(tmp_path / "tz/_custom/ТЗ.docx", image="gotenberg:active")
    assert h.log.lines == [
        f"[compile:{JOB_ID}] вариант не требует компиляции (engine: none) — файл используется как есть",
        f"[compile:{JOB_ID}] конвертация в PDF для предпросмотра (Gotenberg/LibreOffice)…",
        f"[compile:{JOB_ID}] PDF-предпросмотр готов: ТЗ.pdf (3 слайдов)",
    ]


async def test__run_build__copy_only_office__english_log_lines(tmp_path: Path) -> None:
    set_interface_language("en")
    h = Harness(tmp_path)
    (tmp_path / "tz" / "_custom").mkdir(parents=True)
    h.converter.convert_to_pdf.return_value = _pdf_bytes(2)

    await h.runner.run_build(h.spec(**_copy_only()), h.ctx)

    assert h.log.lines == [
        f"[compile:{JOB_ID}] this variant needs no compilation (engine: none) — the file is used as is",
        f"[compile:{JOB_ID}] converting to PDF for preview (Gotenberg/LibreOffice)…",
        f"[compile:{JOB_ID}] preview PDF ready: ТЗ.pdf (2 slides)",
    ]


async def test__run_build__copy_only_office_unavailable__logs_hint_and_keeps_success(tmp_path: Path) -> None:
    h = Harness(tmp_path)

    outcome = await h.runner.run_build(h.spec(**_copy_only()), h.ctx)

    assert outcome.success is True
    assert outcome.pages is None
    assert h.log.lines[-1] == (
        f"[compile:{JOB_ID}] PDF-предпросмотр недоступен (установлен ли образ Gotenberg? "
        "`docker pull gotenberg/gotenberg:8`) — сам pptx остаётся артефактом"
    )
    assert not (tmp_path / "tz/_custom/ТЗ.pdf").exists()


async def test__run_build__copy_only_office_unavailable__english_hint(tmp_path: Path) -> None:
    set_interface_language("en")
    h = Harness(tmp_path)

    await h.runner.run_build(h.spec(**_copy_only()), h.ctx)

    assert h.log.lines[-1] == (
        f"[compile:{JOB_ID}] PDF preview unavailable (is the Gotenberg image installed? "
        "`docker pull gotenberg/gotenberg:8`) — the pptx itself is still the deliverable"
    )


async def test__run_build__copy_only_office_write_fails__logs_error_and_keeps_success(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    h.converter.convert_to_pdf.return_value = _pdf_bytes(1)
    # Папки tz/_custom нет, а на её месте лежит файл: записать PDF нельзя.
    (tmp_path / "tz").write_text("not a directory")

    outcome = await h.runner.run_build(h.spec(**_copy_only()), h.ctx)

    assert outcome.success is True
    assert outcome.pages is None
    assert h.log.lines[-1].startswith(f"[compile:{JOB_ID}] preview write failed: ")


async def test__run_build__copy_only_converter_raises__exception_propagates(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    h.converter.convert_to_pdf.side_effect = RuntimeError("gotenberg crashed")

    with pytest.raises(RuntimeError, match="gotenberg crashed"):
        await h.runner.run_build(h.spec(**_copy_only()), h.ctx)


async def test__run_build__copy_only_office_without_page_count__ready_line_has_no_slide_suffix(
    tmp_path: Path,
) -> None:
    h = Harness(tmp_path)
    (tmp_path / "tz" / "_custom").mkdir(parents=True)
    h.converter.convert_to_pdf.return_value = b"%PDF-1.4 broken"

    outcome = await h.runner.run_build(h.spec(**_copy_only()), h.ctx)

    assert outcome.pages is None
    assert h.log.lines[-1] == f"[compile:{JOB_ID}] PDF-предпросмотр готов: ТЗ.pdf"


# --- проверки ---


def _outcome(success: bool = True) -> BuildOutcome:
    return BuildOutcome(
        success=success,
        status=JobStatus.succeeded if success else JobStatus.failed,
        finished_at=datetime(2026, 10, 26, 9, 30, tzinfo=timezone.utc),
        pages=7,
        words=100,
        chars=500,
    )


async def test__run_post__success__log_content_not_passed_and_result_carries_build_fields(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    found = CheckResult(rule_id="gost/margins", severity=CheckSeverity.warn, message="m")
    h.check_runner.run_all.return_value = [found]
    spec = h.spec()

    result = await h.runner.run_post(spec, h.ctx, _outcome())

    kwargs = h.check_runner.run_all.call_args.kwargs
    assert kwargs["log_content"] is None
    assert kwargs["project_folder"] == tmp_path
    assert (kwargs["doc_id"], kwargs["source_file"], kwargs["base_dir"], kwargs["custom_mode"]) == (
        "tz",
        "tz/main.tex",
        "",
        False,
    )
    assert len(kwargs["rules_with_severity"]) == 2
    assert result.status is JobStatus.succeeded
    assert result.data == CompileResult(
        build_ok=True,
        check_results=(found,),
        pages=7,
        words=100,
        chars=500,
        finished_at=datetime(2026, 10, 26, 9, 30, tzinfo=timezone.utc),
    )


async def test__run_post__build_failed__log_content_is_full_log_and_status_failed(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    h.log.emit("first")
    h.log.emit("second")

    result = await h.runner.run_post(h.spec(), h.ctx, _outcome(success=False))

    assert h.check_runner.run_all.call_args.kwargs["log_content"] == "first\nsecond"
    assert result.status is JobStatus.failed
    assert result.data is not None
    assert result.data_as(CompileResult).build_ok is False


async def test__run_post__checks_banner__published_but_kept_out_of_log(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    h.log.emit("build line")

    await h.runner.run_post(h.spec(), h.ctx, _outcome())

    assert h.log.lines == ["build line"]
    assert h.log.published == ["build line", "[checks] выполняются проверки…"]


async def test__run_post__banner__english(tmp_path: Path) -> None:
    set_interface_language("en")
    h = Harness(tmp_path)

    await h.runner.run_post(h.spec(), h.ctx, _outcome())

    assert h.log.published == ["[checks] running checks…"]


async def test__run_post__ignored_rule_ids__filtered_out_of_results(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    keep = CheckResult(rule_id="gost/margins", severity=CheckSeverity.err, message="keep")
    drop = CheckResult(rule_id="lt:TYPO", severity=CheckSeverity.info, message="drop")
    h.check_runner.run_all.return_value = [keep, drop]

    result = await h.runner.run_post(h.spec(), h.ctx, _outcome())

    assert result.data_as(CompileResult).check_results == (keep,)


async def test__run_post__languagetool_needed__started_with_active_image_before_checks(tmp_path: Path) -> None:
    h = Harness(tmp_path)

    await h.runner.run_post(h.spec(), h.ctx, _outcome())

    h.lt_manager.ensure_running.assert_awaited_once_with("lt:image")


async def test__run_post__custom_mode__languagetool_not_started(tmp_path: Path) -> None:
    h = Harness(tmp_path)

    await h.runner.run_post(h.spec(custom_mode=True), h.ctx, _outcome())

    h.lt_manager.ensure_running.assert_not_awaited()
    assert h.check_runner.run_all.call_args.kwargs["custom_mode"] is True


async def test__run_post__plan_without_languagetool__not_started(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    spec = h.spec()
    payload: CompileJobPayload = spec.payload  # type: ignore[assignment]
    plan = replace(payload.check_plan, needs_languagetool=False)

    await h.runner.run_post(replace(spec, payload=replace(payload, check_plan=plan)), h.ctx, _outcome())

    h.lt_manager.ensure_running.assert_not_awaited()


async def test__run_post__runs_checks_in_worker_thread(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    threads: list[int] = []
    h.check_runner.run_all.side_effect = lambda **_: threads.append(threading.get_ident()) or []

    await h.runner.run_post(h.spec(), h.ctx, _outcome())

    assert threads
    assert threads[0] != threading.get_ident()
