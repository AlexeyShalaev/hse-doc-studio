"""Характеризация сборки на уровне API: пока конвейер переезжает, поведение не меняется.

Идёт настоящий стек: роутер, DI, `TriggerCompileUC`, `DockerCompileExecutor`,
`CompileRunner`, лимитер, шина логов, JSON-репозитории, git. Подменено только то,
что требует машины с Docker: бинарник `docker` (скрипт-пустышка, см.
`tests/fixtures/fake_docker.py`), префлайт демона и образа, запуск LanguageTool и
конвертация office. Тесты читают только публичное: HTTP-ответы, файлы проекта и
журнал вызовов пустышки, поэтому переживают перенос логики между модулями.
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from hse_doc_studio.api.config import settings as app_settings
from hse_doc_studio.core.compile.docker_diagnosis import DockerUnavailableReason
from hse_doc_studio.core.enums import CheckSeverity
from hse_doc_studio.core.value_objects import CheckResult
from hse_doc_studio.infra.checks.runner import CheckRunner
from hse_doc_studio.infra.compile.docker_compile_executor import DockerCompileExecutor
from hse_doc_studio.infra.compile.docker_image_manager import DockerImageManager, DockerStatus, ImageInfo
from hse_doc_studio.infra.languagetool.container_manager import LanguageToolContainerManager
from hse_doc_studio.infra.office.convert_manager import OfficeConvertManager
from httpx import AsyncClient, Response
from pypdf import PdfWriter
from pytest_mock import MockerFixture

from tests.factories import project_api_payload
from tests.fixtures.fake_docker import FakeDocker, install_fake_docker

_TERMINAL = {"success", "failure", "cancelled"}
_DEADLINE_S = 15.0

# Строки журнала по умолчанию (русский интерфейс).
_QUEUE_WAIT_RU = "[queue] ожидание свободного слота сборки (лимит: 1 одновременно)…"
_QUEUE_GOT_RU = "[queue] слот получен — сборка начинается"
_QUEUE_WAIT_EN = "[queue] waiting for a free build slot (limit: 1 concurrent builds)…"
_QUEUE_GOT_EN = "[queue] build slot acquired — starting the build"
_QUEUE_STILL_RU = "[queue] всё ещё в очереди — выполняется сборок: 1…"
_CHECKS_RU = "[checks] выполняются проверки…"
_CANCELLED = "[cancelled] build cancelled by user"
_DANGLING_CITE_LINE = "LaTeX Warning: Citation `ghost' on page 3 undefined on input line 12."
_DANGLING_CITE_RULE = "gost-7.32-2017/dangling-cite"


@dataclass
class Preflight:
    status: AsyncMock
    inspect: AsyncMock


@pytest.fixture(autouse=True)
def fake_docker(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FakeDocker:
    """Любой docker в тесте — пустышка; тесты, которым нужен другой нрав, ставят свою."""
    return install_fake_docker(monkeypatch, tmp_path)


@pytest.fixture(autouse=True)
def preflight(mocker: MockerFixture) -> Preflight:
    """Демон отвечает, образ установлен. Остальные тесты переопределяют ответы."""
    status = mocker.patch.object(
        DockerImageManager,
        "docker_status",
        return_value=DockerStatus(available=True, version="fake", detail=None),
    )
    inspect = mocker.patch.object(
        DockerImageManager,
        "inspect",
        return_value=ImageInfo(image="texlive/texlive:latest", id="sha256:fake", size_bytes=1, created="2026-01-01"),
    )
    return Preflight(status=status, inspect=inspect)


@pytest.fixture(autouse=True)
def languagetool_start(mocker: MockerFixture) -> AsyncMock:
    return mocker.patch.object(LanguageToolContainerManager, "ensure_running", return_value=None)


@pytest_asyncio.fixture
async def project(test_app: AsyncClient, tmp_path: Path) -> dict[str, Any]:
    folder = tmp_path / "proj"
    folder.mkdir()
    resp = await test_app.post("/api/v1/projects", json=project_api_payload(str(folder)))
    assert resp.status_code == 201, resp.text
    return resp.json()


# --- helpers -----------------------------------------------------------------


def _pdf_bytes(pages: int) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=72, height=72)
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


async def _wait_until(predicate: Callable[[], Awaitable[bool] | bool], what: str, timeout: float = _DEADLINE_S) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        outcome = predicate()
        if isinstance(outcome, Awaitable):
            outcome = await outcome
        if outcome:
            return
        if asyncio.get_running_loop().time() > deadline:
            pytest.fail(f"timed out waiting for: {what}")
        await asyncio.sleep(0.03)


async def _trigger(
    client: AsyncClient, project: dict[str, Any], doc_id: str = "thesis", *, language: str | None = None
) -> str:
    headers = {"X-Interface-Language": language} if language else None
    resp = await client.post(f"/api/v1/projects/{project['id']}/documents/{doc_id}/compile", headers=headers)
    assert resp.status_code == 202, resp.text
    return resp.json()["compile_id"]


async def _record(client: AsyncClient, project: dict[str, Any], compile_id: str, doc_id: str = "thesis") -> dict:
    resp = await client.get(f"/api/v1/projects/{project['id']}/documents/{doc_id}/compiles/{compile_id}")
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _wait_terminal(client: AsyncClient, project: dict[str, Any], compile_id: str, doc_id: str = "thesis") -> dict:
    last: dict = {}

    async def _done() -> bool:
        nonlocal last
        last = await _record(client, project, compile_id, doc_id)
        return last["status"] in _TERMINAL

    await _wait_until(_done, f"compile {compile_id} to finish")
    # Итоговая запись видна раньше, чем обновлены статус документа, журнал изменений,
    # коммит и архив PDF; шина логов закрывается после всего этого, и поток
    # возвращается именно тогда.
    await _stream(client, project, compile_id)
    return last


async def _compile(client: AsyncClient, project: dict[str, Any], doc_id: str = "thesis") -> dict:
    compile_id = await _trigger(client, project, doc_id)
    return await _wait_terminal(client, project, compile_id, doc_id)


async def _doc_status(client: AsyncClient, project: dict[str, Any], doc_id: str = "thesis") -> str:
    resp = await client.get(f"/api/v1/projects/{project['id']}/documents/{doc_id}")
    assert resp.status_code == 200, resp.text
    return resp.json()["status"]


async def _changelog(client: AsyncClient, project: dict[str, Any]) -> list[dict]:
    resp = await client.get(f"/api/v1/projects/{project['id']}/changelog")
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _vcs_compile_commits(client: AsyncClient, project: dict[str, Any]) -> list[dict]:
    resp = await client.get(f"/api/v1/projects/{project['id']}/vcs/history")
    assert resp.status_code == 200, resp.text
    return [c for c in resp.json() if c["kind"] == "compile"]


async def _stream(client: AsyncClient, project: dict[str, Any], compile_id: str) -> tuple[list[str], dict]:
    """SSE-поток сборки: (строки log-событий, полезная нагрузка done)."""
    resp = await asyncio.wait_for(
        client.get(f"/api/v1/projects/{project['id']}/compiles/{compile_id}/stream"), timeout=_DEADLINE_S
    )
    return _parse_sse(resp)


def _parse_sse(resp: Response) -> tuple[list[str], dict]:
    assert resp.status_code == 200, resp.text
    lines: list[str] = []
    done: dict | None = None
    for block in resp.text.split("\n\n"):
        if not block.strip():
            continue
        event, _, data = block.partition("\n")
        payload = json.loads(data.removeprefix("data: "))
        if event == "event: log":
            lines.append(payload)
        elif event == "event: done":
            done = payload
    assert done is not None, resp.text
    return lines, done


def _file(project: dict[str, Any], rel: str) -> Path:
    return Path(project["folder"]) / rel


async def _set_concurrency(client: AsyncClient, limit: int) -> None:
    resp = await client.put("/api/v1/settings", json={"max_concurrent_compiles": limit})
    assert resp.status_code == 200, resp.text


async def _set_project_checks_disabled(client: AsyncClient, project: dict[str, Any], rule_ids: list[str]) -> None:
    resp = await client.patch(f"/api/v1/projects/{project['id']}", json={"checks_override": {"disabled": rule_ids}})
    assert resp.status_code == 200, resp.text


def _fake_check_results(*rule_ids: str) -> list[CheckResult]:
    return [CheckResult(rule_id=rid, severity=CheckSeverity.warn, message=f"finding {rid}") for rid in rule_ids]


# --- 1. успешная сборка ------------------------------------------------------


async def test__compile__success__persists_record_pdf_archive_document_status_and_changelog(
    test_app: AsyncClient,
    project: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Сборка длится заметно дольше проверки раннего состояния, иначе та гоняется со сборкой.
    fake_docker = install_fake_docker(monkeypatch, tmp_path, duration_s=0.5)
    compile_id = await _trigger(test_app, project)

    # Сборка ещё идёт: запись создана, документ заперт «сборкой».
    early = await _record(test_app, project, compile_id)
    assert early["status"] in {"pending", "running"}
    assert await _doc_status(test_app, project) == "building"

    record = await _wait_terminal(test_app, project, compile_id)

    assert record["status"] == "success"
    assert record["engine"] == "xelatex"
    assert (record["pages"], record["words"], record["chars"]) == (7, 19, 125)
    assert record["finished_at"] is not None
    log = record["log"]
    assert f"[compile:{compile_id}] xelatex via latexmk" in log
    assert "fake latexmk: line 1" in log
    assert f"[compile:{compile_id}] latexmk converged (rc=0)" in log
    assert f"[compile:{compile_id}] pdf written to thesis.pdf" in log
    # Служебные маркеры потока в журнал не попадают.
    for marker in ("__DONE__", "__FAILED__", "__PAGES__", "__WORDS__"):
        assert marker not in log

    # PDF лёг рядом с исходником и не остался в .build.
    assert _file(project, "thesis/thesis.pdf").read_bytes() == b"%PDF-1.4 fake build\n"
    assert not _file(project, "thesis/.build/thesis/thesis.pdf").exists()
    # Архивная копия для визуального сравнения отдаётся по API.
    archived = await test_app.get(
        f"/api/v1/projects/{project['id']}/documents/thesis/compiles/{compile_id}/pdf",
    )
    assert archived.status_code == 200, archived.text
    assert archived.content == b"%PDF-1.4 fake build\n"

    assert await _doc_status(test_app, project) in {"ok", "warn", "err"}
    entries = [e for e in await _changelog(test_app, project) if e["kind"].startswith("compile")]
    assert [(e["kind"], e["doc_id"], e["summary"]) for e in entries] == [
        ("compile_ok", "thesis", "Compile succeeded for thesis")
    ]

    # Один запуск latexmk и один texcount: ничего лишнего docker не звали.
    assert len(fake_docker.build_calls()) == 1
    assert len(fake_docker.calls()) == 2


async def test__compile__success__document_status_follows_check_severities(
    test_app: AsyncClient, project: dict[str, Any], mocker: MockerFixture
) -> None:
    run_all = mocker.patch.object(CheckRunner, "run_all", return_value=[])
    assert (await _compile(test_app, project))["check_results"] == []
    assert await _doc_status(test_app, project) == "ok"

    run_all.return_value = _fake_check_results("x/warn-only")
    record = await _compile(test_app, project)
    assert [r["rule_id"] for r in record["check_results"]] == ["x/warn-only"]
    assert await _doc_status(test_app, project) == "warn"

    run_all.return_value = [CheckResult(rule_id="x/err", severity=CheckSeverity.err, message="boom")]
    assert (await _compile(test_app, project))["status"] == "success"
    assert await _doc_status(test_app, project) == "err"


async def test__compile__success__finished_at_is_taken_before_checks_run(
    test_app: AsyncClient, project: dict[str, Any], mocker: MockerFixture
) -> None:
    checks_done: list[datetime] = []

    def _slow_checks(**_kwargs: Any) -> list[CheckResult]:
        threading.Event().wait(0.4)
        checks_done.append(datetime.now(tz=timezone.utc))
        return []

    mocker.patch.object(CheckRunner, "run_all", side_effect=_slow_checks)

    record = await _compile(test_app, project)

    finished_at = datetime.fromisoformat(record["finished_at"])
    assert finished_at < checks_done[0]
    entries = [e for e in await _changelog(test_app, project) if e["kind"] == "compile_ok"]
    assert datetime.fromisoformat(entries[0]["at"]) == finished_at


# --- 2. ошибка latexmk -------------------------------------------------------


async def test__compile__latexmk_exit_12__fails_resets_state_and_feeds_log_to_checks(
    test_app: AsyncClient, project: dict[str, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = install_fake_docker(
        monkeypatch, tmp_path, exit_code=12, output_lines=("fake latexmk: line 1", _DANGLING_CITE_LINE)
    )

    record = await _compile(test_app, project)

    assert record["status"] == "failure"
    assert "latexmk exited with code 12" in record["log"]
    assert _DANGLING_CITE_LINE in record["log"]
    # Состояние latexmk сброшено, чтобы следующая сборка не упёрлась в «gave an error»,
    # а .log остался для разбора.
    assert not _file(project, "thesis/.build/thesis/thesis.fdb_latexmk").exists()
    assert _file(project, "thesis/.build/thesis/thesis.log").exists()
    assert not _file(project, "thesis/thesis.pdf").exists()
    # Лог упавшей сборки скормлен правилам log_parse.
    assert _DANGLING_CITE_RULE in [r["rule_id"] for r in record["check_results"]]
    assert await _doc_status(test_app, project) == "err"
    entries = [e for e in await _changelog(test_app, project) if e["kind"].startswith("compile")]
    assert [(e["kind"], e["summary"]) for e in entries] == [("compile_fail", "Compile failed for thesis")]
    # texcount после неуспеха не зовут.
    assert len(fake.calls()) == 1


# --- 3. тишина ---------------------------------------------------------------


async def test__compile__no_output_past_idle_timeout__kills_process_and_fails(
    test_app: AsyncClient,
    project: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(app_settings.compile, "idle_timeout_s", 2.0)
    fake = install_fake_docker(monkeypatch, tmp_path, duration_s=60.0, output_lines=("fake latexmk: line 1",))

    record = await _compile(test_app, project)

    assert record["status"] == "failure"
    assert "[error] no output for" in record["log"]
    assert "killing process" in record["log"]
    assert "term" in fake.markers()
    assert not _file(project, "thesis/.build/thesis/thesis.fdb_latexmk").exists()
    assert await _doc_status(test_app, project) == "err"


# --- 4. отмена ---------------------------------------------------------------


async def _start_hanging_build(
    client: AsyncClient,
    project: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    ignore_term: bool,
) -> tuple[str, FakeDocker]:
    fake = install_fake_docker(monkeypatch, tmp_path, duration_s=60.0, ignore_term=ignore_term)
    compile_id = await _trigger(client, project)
    await _wait_until(lambda: "started" in fake.markers(), "fake latexmk to start")
    return compile_id, fake


async def test__compile__cancel_during_latexmk__sends_sigterm_and_finishes_the_task(
    test_app: AsyncClient,
    project: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    compile_id, fake = await _start_hanging_build(test_app, project, monkeypatch, tmp_path, ignore_term=False)

    resp = await test_app.post(f"/api/v1/projects/{project['id']}/compiles/{compile_id}/cancel")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"cancelled_task": True, "record_finalised": False}

    # Процесс получил SIGTERM и вышел, задача завершилась: поток логов закрылся.
    # Итоговый статус здесь намеренно не фиксируется. SIGTERM-ответивший процесс
    # закрывает stdout одновременно с выходом, и отмена задачи приходит либо в
    # docker-фазу (запись `cancelled`), либо уже в фазу проверок (запись остаётся
    # `running`, см. раздел 12). Детерминированный путь отмены — через SIGKILL ниже.
    _lines, done = await _stream(test_app, project, compile_id)
    assert fake.markers() == ["started", "term"]
    assert done["status"] in {"cancelled", "running"}
    record = await _record(test_app, project, compile_id)
    assert record["status"] == done["status"]


async def test__compile__cancel_when_process_ignores_sigterm__kills_it_after_grace_period(
    test_app: AsyncClient,
    project: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("hse_doc_studio.infra.compile.compile_runner._PROCESS_TERMINATE_TIMEOUT_S", 0.3)
    monkeypatch.setattr("hse_doc_studio.infra.compile.docker_compile_executor._PROCESS_TERMINATE_TIMEOUT_S", 0.3)
    compile_id, fake = await _start_hanging_build(test_app, project, monkeypatch, tmp_path, ignore_term=True)

    resp = await test_app.post(f"/api/v1/projects/{project['id']}/compiles/{compile_id}/cancel")
    assert resp.status_code == 200, resp.text

    # Отмена после SIGKILL приходит синхронно, пока задача ждёт строку из канала, то
    # есть внутри защитного блока сборки: запись финализируется как отменённая.
    record = await _wait_terminal(test_app, project, compile_id)
    assert record["status"] == "cancelled"
    assert _CANCELLED in record["log"]
    assert record["check_results"] == []
    assert "term-ignored" in fake.markers()
    assert await _doc_status(test_app, project) == "err"
    entries = [e for e in await _changelog(test_app, project) if e["kind"].startswith("compile")]
    assert [(e["kind"], e["summary"]) for e in entries] == [("compile_fail", "Compile cancelled for thesis")]
    assert not _file(project, "thesis/thesis.pdf").exists()
    lines, done = await _stream(test_app, project, compile_id)
    assert _CANCELLED in lines
    assert done["status"] == "cancelled"


# --- 5. очередь --------------------------------------------------------------


async def _two_queued_compiles(
    client: AsyncClient,
    project: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    second_language: str | None = None,
) -> dict:
    """Две сборки при лимите 1; возвращает запись второй (она ждала слот)."""
    await _set_concurrency(client, 1)
    fake = install_fake_docker(monkeypatch, tmp_path, duration_s=0.8)
    first = await _trigger(client, project, "thesis")
    await _wait_until(lambda: "started" in fake.markers(), "first build to take the slot")
    second = await _trigger(client, project, "annotation", language=second_language)
    first_record = await _wait_terminal(client, project, first, "thesis")
    assert first_record["status"] == "success"
    return await _wait_terminal(client, project, second, "annotation")


def _index_of(log: str, needle: str) -> int:
    lines = log.splitlines()
    assert needle in lines, log
    return lines.index(needle)


async def test__compile__limit_reached__second_build_queues_then_starts(
    test_app: AsyncClient, project: dict[str, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    record = await _two_queued_compiles(test_app, project, monkeypatch, tmp_path)

    assert record["status"] == "success"
    log = record["log"]
    waiting = _index_of(log, _QUEUE_WAIT_RU)
    acquired = _index_of(log, _QUEUE_GOT_RU)
    started = next(i for i, ln in enumerate(log.splitlines()) if "xelatex via latexmk" in ln)
    assert waiting < acquired < started


async def test__compile__limit_reached_with_english_header__queue_lines_are_english(
    test_app: AsyncClient, project: dict[str, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    record = await _two_queued_compiles(test_app, project, monkeypatch, tmp_path, second_language="en")

    log = record["log"]
    assert _index_of(log, _QUEUE_WAIT_EN) < _index_of(log, _QUEUE_GOT_EN)
    assert _QUEUE_WAIT_RU not in log
    assert _QUEUE_GOT_RU not in log


async def test__compile__waiting_in_queue__heartbeat_lines_keep_the_log_alive(
    test_app: AsyncClient, project: dict[str, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("hse_doc_studio.use_cases.compile.trigger_compile._QUEUE_HEARTBEAT_INTERVAL_S", 0.1)

    record = await _two_queued_compiles(test_app, project, monkeypatch, tmp_path)

    log = record["log"]
    assert _QUEUE_STILL_RU in log.splitlines()
    assert _index_of(log, _QUEUE_WAIT_RU) < log.splitlines().index(_QUEUE_STILL_RU) < _index_of(log, _QUEUE_GOT_RU)


async def test__compile__under_the_limit__no_queue_lines(test_app: AsyncClient, project: dict[str, Any]) -> None:
    record = await _compile(test_app, project)

    assert "[queue]" not in record["log"]


# --- 6. SSE-поток ------------------------------------------------------------


async def test__compile__stream_during_build__ends_with_persisted_status_and_carries_checks_line(
    test_app: AsyncClient, project: dict[str, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = install_fake_docker(monkeypatch, tmp_path, duration_s=0.6)
    compile_id = await _trigger(test_app, project)
    await _wait_until(lambda: "started" in fake.markers(), "fake latexmk to start")

    lines, done = await _stream(test_app, project, compile_id)

    assert done["status"] == "success"
    assert any("xelatex via latexmk" in ln for ln in lines)
    assert "fake latexmk: line 1" in lines
    # Строка про проверки живёт только в потоке, в журнал записи она не попадает.
    assert _CHECKS_RU in lines
    record = await _wait_terminal(test_app, project, compile_id)
    assert _CHECKS_RU not in record["log"]
    assert lines.index("fake latexmk: line 1") < lines.index(_CHECKS_RU)


async def test__compile__stream_after_finish__replays_the_whole_log_and_final_status(
    test_app: AsyncClient, project: dict[str, Any]
) -> None:
    compile_id = await _trigger(test_app, project)
    record = await _wait_terminal(test_app, project, compile_id)

    lines, done = await _stream(test_app, project, compile_id)

    assert done["status"] == "success"
    assert lines[: len(record["log"].splitlines())] == record["log"].splitlines()


async def test__compile__stream_of_failed_build__ends_with_failure_status(
    test_app: AsyncClient, project: dict[str, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    install_fake_docker(monkeypatch, tmp_path, exit_code=12, duration_s=0.3)
    compile_id = await _trigger(test_app, project)

    _lines, done = await _stream(test_app, project, compile_id)

    assert done["status"] == "failure"


# --- 7. сборка без docker ----------------------------------------------------


async def test__compile__custom_pdf__skips_docker_and_checks_and_counts_pages(
    test_app: AsyncClient,
    project: dict[str, Any],
    fake_docker: FakeDocker,
    preflight: Preflight,
    languagetool_start: AsyncMock,
) -> None:
    upload = await test_app.post(
        f"/api/v1/projects/{project['id']}/documents/thesis/custom-file",
        files={"file": ("my-doc.pdf", _pdf_bytes(2), "application/pdf")},
    )
    assert upload.status_code == 200, upload.text

    record = await _compile(test_app, project)

    assert record["status"] == "success"
    assert record["pages"] == 2
    assert (
        f"[compile:{record['id']}] вариант не требует компиляции (engine: none) — файл используется как есть"
        in (record["log"])
    )
    assert fake_docker.calls() == []
    preflight.status.assert_not_awaited()
    preflight.inspect.assert_not_awaited()
    languagetool_start.assert_not_awaited()


async def test__compile__pptx_variant__converts_preview_and_counts_slides(
    test_app: AsyncClient, project: dict[str, Any], fake_docker: FakeDocker, preflight: Preflight, mocker: MockerFixture
) -> None:
    convert = mocker.patch.object(OfficeConvertManager, "convert_to_pdf", return_value=_pdf_bytes(3))

    record = await _compile(test_app, project, "presentation")

    assert record["status"] == "success"
    assert record["pages"] == 3
    log = record["log"]
    assert f"[compile:{record['id']}] конвертация в PDF для предпросмотра (Gotenberg/LibreOffice)…" in log
    assert f"[compile:{record['id']}] PDF-предпросмотр готов: presentation.pdf (3 слайдов)" in log
    assert _file(project, "presentation/pptx/presentation.pdf").read_bytes() == _pdf_bytes(3)
    convert.assert_awaited_once()
    assert fake_docker.calls() == []
    preflight.status.assert_not_awaited()


async def test__compile__pptx_variant_without_converter__still_succeeds_without_preview(
    test_app: AsyncClient, project: dict[str, Any], mocker: MockerFixture
) -> None:
    mocker.patch.object(OfficeConvertManager, "convert_to_pdf", return_value=None)

    record = await _compile(test_app, project, "presentation")

    assert record["status"] == "success"
    assert record["pages"] is None
    assert "PDF-предпросмотр недоступен" in record["log"]
    assert not _file(project, "presentation/pptx/presentation.pdf").exists()


# --- 8. падение задачи -------------------------------------------------------


async def test__compile__executor_raises__fails_with_crash_line_and_skips_checks(
    test_app: AsyncClient, project: dict[str, Any], mocker: MockerFixture, languagetool_start: AsyncMock
) -> None:
    mocker.patch.object(DockerCompileExecutor, "run", side_effect=RuntimeError("executor exploded"))
    run_all = mocker.patch.object(CheckRunner, "run_all", return_value=[])

    record = await _compile(test_app, project)

    assert record["status"] == "failure"
    assert "[error] compile task crashed: executor exploded" in record["log"]
    assert record["check_results"] == []
    run_all.assert_not_called()
    languagetool_start.assert_not_awaited()
    assert await _doc_status(test_app, project) == "err"
    entries = [e for e in await _changelog(test_app, project) if e["kind"].startswith("compile")]
    assert [e["kind"] for e in entries] == ["compile_fail"]


# --- 9. проверки -------------------------------------------------------------


async def test__compile__ignored_finding_ids__are_filtered_from_results(
    test_app: AsyncClient, project: dict[str, Any], mocker: MockerFixture
) -> None:
    run_all = mocker.patch.object(CheckRunner, "run_all", return_value=_fake_check_results("lt:KEEP", "lt:SKIP"))
    await _set_project_checks_disabled(test_app, project, ["lt:SKIP"])

    record = await _compile(test_app, project)

    assert [r["rule_id"] for r in record["check_results"]] == ["lt:KEEP"]
    kwargs = run_all.call_args.kwargs
    assert kwargs["doc_id"] == "thesis"
    assert kwargs["source_file"] == "thesis/thesis.tex"
    assert kwargs["custom_mode"] is False
    # После успешной сборки правила читают .log сами, лог сборки им не передают.
    assert kwargs["log_content"] is None


async def test__compile__failed_build__passes_build_log_to_checks(
    test_app: AsyncClient,
    project: dict[str, Any],
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    install_fake_docker(monkeypatch, tmp_path, exit_code=12)
    run_all = mocker.patch.object(CheckRunner, "run_all", return_value=[])

    record = await _compile(test_app, project)

    assert record["status"] == "failure"
    assert run_all.call_args.kwargs["log_content"] == record["log"]


async def test__compile__rules_with_external_engine__languagetool_started_once(
    test_app: AsyncClient, project: dict[str, Any], languagetool_start: AsyncMock
) -> None:
    await _compile(test_app, project)

    languagetool_start.assert_awaited_once()


# --- 10. автокоммит ----------------------------------------------------------


def _touch_source(project: dict[str, Any], marker: str) -> None:
    with _file(project, "thesis/thesis.tex").open("a", encoding="utf-8") as fh:
        fh.write(f"\n% {marker}\n")


async def test__compile__success_with_auto_commit__creates_compile_commit(
    test_app: AsyncClient, project: dict[str, Any]
) -> None:
    _touch_source(project, "before compile")
    assert await _vcs_compile_commits(test_app, project) == []

    await _compile(test_app, project)

    commits = await _vcs_compile_commits(test_app, project)
    assert [c["message"] for c in commits] == ["Сборка: thesis · 7 стр."]


async def test__compile__failure_with_auto_commit__creates_no_commit(
    test_app: AsyncClient, project: dict[str, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    install_fake_docker(monkeypatch, tmp_path, exit_code=12)
    _touch_source(project, "before failed compile")

    record = await _compile(test_app, project)

    assert record["status"] == "failure"
    assert await _vcs_compile_commits(test_app, project) == []


async def test__compile__success_with_auto_commit_disabled__creates_no_commit(
    test_app: AsyncClient, project: dict[str, Any]
) -> None:
    resp = await test_app.patch(
        f"/api/v1/projects/{project['id']}/vcs/settings", json={"auto_commit_on_compile": False}
    )
    assert resp.status_code == 200, resp.text
    _touch_source(project, "before compile")

    record = await _compile(test_app, project)

    assert record["status"] == "success"
    assert await _vcs_compile_commits(test_app, project) == []


# --- 11. префлайт ------------------------------------------------------------


async def test__compile__docker_daemon_unavailable__409_without_record_or_building_status(
    test_app: AsyncClient, project: dict[str, Any], preflight: Preflight
) -> None:
    preflight.status.return_value = DockerStatus(
        available=False,
        version=None,
        detail="daemon is down",
        reason=DockerUnavailableReason.DAEMON_UNREACHABLE,
        socket_gid=None,
    )

    resp = await test_app.post(f"/api/v1/projects/{project['id']}/documents/thesis/compile")

    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "docker_unavailable"
    assert detail["detail"] == "daemon is down"
    assert detail["reason"] == str(DockerUnavailableReason.DAEMON_UNREACHABLE)
    await _assert_nothing_scheduled(test_app, project)


async def test__compile__image_not_installed__409_without_record_or_building_status(
    test_app: AsyncClient, project: dict[str, Any], preflight: Preflight
) -> None:
    preflight.inspect.return_value = None

    resp = await test_app.post(f"/api/v1/projects/{project['id']}/documents/thesis/compile")

    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "image_missing"
    assert detail["image"]
    assert detail["image"] in detail["detail"]
    await _assert_nothing_scheduled(test_app, project)


async def _assert_nothing_scheduled(client: AsyncClient, project: dict[str, Any]) -> None:
    listing = await client.get(f"/api/v1/projects/{project['id']}/documents/thesis/compiles")
    assert listing.status_code == 200, listing.text
    assert listing.json() == []
    assert await _doc_status(client, project) == "draft"


# --- 12. зафиксированный изъян: сбой в фазе проверок --------------------------
#
# Проверки идут ПОСЛЕ защитного блока сборки (`except CancelledError/Exception`
# охватывает только docker-фазу). Поэтому отмена или исключение именно в проверках
# не доходят до записи итогового состояния: запись остаётся `running`, документ
# `building`, а поток логов закрывается в `finally`. Это неправильно, но это
# сегодняшнее поведение; рефакторинг конвейера не вправе его менять молча.


async def _break_checks_phase(
    client: AsyncClient,
    project: dict[str, Any],
    mocker: MockerFixture,
    *,
    cancel: bool,
) -> tuple[str, threading.Event]:
    """Довести сборку до фазы проверок, оборвать её и дождаться закрытия потока."""
    reached = threading.Event()
    release = threading.Event()

    def _checks(**_kwargs: Any) -> list[CheckResult]:
        reached.set()
        release.wait(timeout=_DEADLINE_S)
        if not cancel:
            raise RuntimeError("checks exploded")
        return []

    mocker.patch.object(CheckRunner, "run_all", side_effect=_checks)
    compile_id = await _trigger(client, project)
    await _wait_until(reached.is_set, "the checks phase to start")
    if cancel:
        resp = await client.post(f"/api/v1/projects/{project['id']}/compiles/{compile_id}/cancel")
        assert resp.status_code == 200, resp.text
        assert resp.json()["cancelled_task"] is True
    else:
        release.set()
    return compile_id, release


async def test__compile__cancel_during_checks__record_stays_running(
    test_app: AsyncClient, project: dict[str, Any], mocker: MockerFixture
) -> None:
    compile_id, release = await _break_checks_phase(test_app, project, mocker, cancel=True)
    try:
        # Поток закрылся (шину закрывает finally), а статус так и не стал терминальным.
        _lines, done = await _stream(test_app, project, compile_id)
    finally:
        release.set()

    assert done["status"] == "running"
    record = await _record(test_app, project, compile_id)
    assert record["status"] == "running"
    assert _CANCELLED not in record["log"]
    assert await _doc_status(test_app, project) == "building"


async def test__compile__exception_during_checks__record_stays_running(
    test_app: AsyncClient, project: dict[str, Any], mocker: MockerFixture
) -> None:
    compile_id, release = await _break_checks_phase(test_app, project, mocker, cancel=False)
    try:
        _lines, done = await _stream(test_app, project, compile_id)
    finally:
        release.set()

    assert done["status"] == "running"
    record = await _record(test_app, project, compile_id)
    assert record["status"] == "running"
    assert "[error] compile task crashed" not in record["log"]
    assert await _doc_status(test_app, project) == "building"
