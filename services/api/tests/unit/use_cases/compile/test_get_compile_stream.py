"""GetCompileStreamUC: поток ждёт итога облачной сборки и отдаёт причину сбоя вместе со статусом."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from hse_doc_studio.core.entities import CompileRecord
from hse_doc_studio.core.enums import CompileStatus, EngineType
from hse_doc_studio.infra.compile.log_bus import CompileLogBus
from hse_doc_studio.use_cases.compile import get_compile_stream as module
from hse_doc_studio.use_cases.compile.get_compile_stream import (
    RESULT_PREFIX,
    STATUS_PREFIX,
    GetCompileStreamInput,
    GetCompileStreamUC,
)

NOW = datetime(2026, 11, 4, tzinfo=UTC)


def _record(folder: Path, **kw: object) -> CompileRecord:
    base = CompileRecord(
        id=uuid4(),
        project_folder=folder,
        doc_id="d",
        engine=EngineType.xelatex,
        status=CompileStatus.running,
        started_at=NOW,
        finished_at=None,
        log="",
        output_path=None,
        check_results=[],
        pages=None,
    )
    return replace(base, **kw)  # type: ignore[arg-type]


def _uc(folder: Path, repo: AsyncMock, bus: CompileLogBus) -> GetCompileStreamUC:
    locator = MagicMock()
    locator.folder_of = AsyncMock(return_value=folder)
    return GetCompileStreamUC(locator, repo, bus)


async def test__running_record_without_bus__stream_waits_for_the_final_record(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(module, "RECORD_POLL_S", 0.01)
    running = _record(tmp_path)
    failed = replace(
        running,
        status=CompileStatus.failure,
        log="! boom\n[error] build_failed: text\n",
        error_code="build_failed",
        error_detail=None,
    )
    repo = AsyncMock()
    repo.get_for_project.side_effect = [running, running, running, failed, failed]
    uc = _uc(tmp_path, repo, CompileLogBus())

    lines = [line async for line in await uc.execute(GetCompileStreamInput(uuid4(), "", running.id))]

    assert lines[:2] == ["! boom", "[error] build_failed: text"]
    assert lines[2] == f"{STATUS_PREFIX}failure"
    result = json.loads(lines[3][len(RESULT_PREFIX) :])
    assert result["error"]["code"] == "build_failed"
    assert result["error"]["message"]


async def test__live_lines_then_record__no_duplicates_and_error_block_appended(tmp_path: Path) -> None:
    bus = CompileLogBus()
    record = _record(tmp_path, status=CompileStatus.failure, log="a\nb\n[error] image_missing: x\n")
    record = replace(record, error_code="image_missing", error_detail="x")
    bus.publish(record.id, "a")
    bus.publish(record.id, "b")
    bus.close(record.id)
    repo = AsyncMock()
    repo.get_for_project.return_value = record

    lines = [
        line async for line in await _uc(tmp_path, repo, bus).execute(GetCompileStreamInput(uuid4(), "", record.id))
    ]

    assert lines[:3] == ["a", "b", "[error] image_missing: x"]
    assert json.loads(lines[4][len(RESULT_PREFIX) :])["error"]["detail"] == "x"


async def test__successful_record__result_has_no_error(tmp_path: Path) -> None:
    record = _record(tmp_path, status=CompileStatus.success, log="ok\n", pages=3)
    repo = AsyncMock()
    repo.get_for_project.return_value = record

    lines = [
        line
        async for line in await _uc(tmp_path, repo, CompileLogBus()).execute(
            GetCompileStreamInput(uuid4(), "", record.id)
        )
    ]

    assert json.loads(lines[-1][len(RESULT_PREFIX) :]) == {"pages": 3, "warnings": 0, "errors": 0, "error": None}


async def test__wait_is_capped__stream_ends_with_the_current_status(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(module, "RECORD_POLL_S", 0.01)
    monkeypatch.setattr(module, "MAX_WAIT_S", 0.03)
    record = _record(tmp_path)
    repo = AsyncMock()
    repo.get_for_project.return_value = record

    lines = await asyncio.wait_for(
        _collect(await _uc(tmp_path, repo, CompileLogBus()).execute(GetCompileStreamInput(uuid4(), "", record.id))), 5
    )

    assert f"{STATUS_PREFIX}running" in lines


async def _collect(stream) -> list[str]:  # noqa: ANN001
    return [line async for line in stream]
