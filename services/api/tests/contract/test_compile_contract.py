"""Контрактный набор ICompileRepository: Json и InMemory ведут себя одинаково."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from hse_doc_studio.core.entities import CompileRecord
from hse_doc_studio.core.enums import CompileStatus, EngineType
from hse_doc_studio.infra.persistence.compile import JsonCompileRepository

from tests.contract.base import PortContract
from tests.fakes.compile import InMemoryCompileRepository

_FACTORIES: dict[str, Callable[[Path], Any]] = {
    "inmemory": lambda _root: InMemoryCompileRepository(),
    "json": lambda _root: JsonCompileRepository(),
}
_T0 = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def make_record(folder: Path, *, doc_id: str = "vkr", minutes: int = 0, **changes: Any) -> CompileRecord:
    record = CompileRecord(
        id=uuid4(),
        project_folder=folder,
        doc_id=doc_id,
        engine=EngineType.xelatex,
        status=CompileStatus.success,
        started_at=_T0 + timedelta(minutes=minutes),
        finished_at=_T0 + timedelta(minutes=minutes, seconds=30),
        log="ok",
        output_path=None,
        check_results=[],
        pages=10,
        words=100,
        chars=500,
    )
    return replace(record, **changes)


class TestCompileContract(PortContract):
    implementations = _FACTORIES

    async def test__get_for_project__unknown_id__none(self, port: Any, tmp_path: Path) -> None:
        assert await port.get_for_project(tmp_path, uuid4()) is None

    async def test__save__then_get__round_trips(self, port: Any, tmp_path: Path) -> None:
        record = make_record(tmp_path, output_path=tmp_path / "vkr.pdf")
        await port.save(record)
        assert await port.get_for_project(tmp_path, record.id) == record

    async def test__save__same_id__replaces_record(self, port: Any, tmp_path: Path) -> None:
        record = make_record(tmp_path, status=CompileStatus.running, finished_at=None, log="")
        await port.save(record)
        await port.save(replace(record, status=CompileStatus.failure, log="boom"))
        loaded = await port.get_for_project(tmp_path, record.id)
        assert loaded is not None
        assert (loaded.status, loaded.log) == (CompileStatus.failure, "boom")

    async def test__list_for_document__oldest_first_and_only_that_document(self, port: Any, tmp_path: Path) -> None:
        late = make_record(tmp_path, minutes=20)
        early = make_record(tmp_path, minutes=1)
        middle = make_record(tmp_path, minutes=10)
        other_doc = make_record(tmp_path, doc_id="tz", minutes=5)
        for record in (late, early, middle, other_doc):
            await port.save(record)
        assert [r.id for r in await port.list_for_document(tmp_path, "vkr")] == [early.id, middle.id, late.id]

    async def test__list_for_document__nothing_saved__empty(self, port: Any, tmp_path: Path) -> None:
        assert await port.list_for_document(tmp_path, "vkr") == []

    async def test__list_unfinished__returns_only_pending_and_running(self, port: Any, tmp_path: Path) -> None:
        pending = make_record(tmp_path, status=CompileStatus.pending, finished_at=None)
        running = make_record(tmp_path, status=CompileStatus.running, finished_at=None, minutes=1)
        for record in (
            pending,
            running,
            make_record(tmp_path, minutes=2),
            make_record(tmp_path, status=CompileStatus.failure),
        ):
            await port.save(record)
        assert {r.id for r in await port.list_unfinished(tmp_path)} == {pending.id, running.id}

    async def test__records__are_isolated_between_projects(self, port: Any, tmp_path: Path) -> None:
        mine, theirs = tmp_path / "a", tmp_path / "b"
        mine.mkdir()
        theirs.mkdir()
        record = make_record(mine)
        await port.save(record)
        assert await port.get_for_project(theirs, record.id) is None
        assert await port.list_for_document(theirs, "vkr") == []
