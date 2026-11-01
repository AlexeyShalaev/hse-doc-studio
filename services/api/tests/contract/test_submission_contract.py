"""Контрактный набор IPackSubmissionRepository: Json и InMemory ведут себя одинаково."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from hse_doc_studio.core.catalog import ExtraSubmissionItem, SubmissionDocItem
from hse_doc_studio.core.entities import PackSubmissionRecord
from hse_doc_studio.infra.persistence.submission import JsonPackSubmissionRepository

from tests.contract.base import PortContract
from tests.fakes.submission import InMemoryPackSubmissionRepository

_FACTORIES: dict[str, Callable[[Path], Any]] = {
    "inmemory": lambda _root: InMemoryPackSubmissionRepository(),
    "json": lambda _root: JsonPackSubmissionRepository(),
}
_T0 = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def make_submission(folder: Path, *, minutes: int = 0, **changes: Any) -> PackSubmissionRecord:
    submission_id = uuid4()
    record = PackSubmissionRecord(
        id=submission_id,
        project_folder=folder,
        profile_id="final",
        created_at=_T0 + timedelta(minutes=minutes),
        doc_items=[SubmissionDocItem(doc_id="vkr", signatures=("student",))],
        extra_items=[ExtraSubmissionItem(source="readme.txt", output_name="README.txt", format=None)],
        output_path=folder / "submissions" / f"final-{submission_id.hex[:8]}.zip",
        output_dir=folder / "submissions" / f"final-{submission_id.hex[:8]}",
    )
    return replace(record, **changes)


class TestSubmissionContract(PortContract):
    implementations = _FACTORIES

    async def test__get__unknown_id__none(self, port: Any, tmp_path: Path) -> None:
        assert await port.get(tmp_path, uuid4()) is None

    async def test__save__then_get__round_trips(self, port: Any, tmp_path: Path) -> None:
        record = make_submission(tmp_path)
        await port.save(record)
        assert await port.get(tmp_path, record.id) == record

    async def test__save__artifact_key_without_output_dir__round_trips(self, port: Any, tmp_path: Path) -> None:
        record = make_submission(tmp_path, output_dir=None, artifact_key="artifacts/p/submissions/s/final.zip")
        await port.save(record)
        loaded = await port.get(tmp_path, record.id)
        assert loaded is not None
        assert (loaded.artifact_key, loaded.output_dir) == ("artifacts/p/submissions/s/final.zip", None)

    async def test__list_for_project__oldest_first(self, port: Any, tmp_path: Path) -> None:
        late, early, middle = (make_submission(tmp_path, minutes=m) for m in (20, 1, 10))
        for record in (late, early, middle):
            await port.save(record)
        assert [r.id for r in await port.list_for_project(tmp_path)] == [early.id, middle.id, late.id]

    async def test__list_for_project__nothing_saved__empty(self, port: Any, tmp_path: Path) -> None:
        assert await port.list_for_project(tmp_path) == []

    async def test__records__are_isolated_between_projects(self, port: Any, tmp_path: Path) -> None:
        mine, theirs = tmp_path / "a", tmp_path / "b"
        mine.mkdir()
        theirs.mkdir()
        record = make_submission(mine)
        await port.save(record)
        assert await port.get(theirs, record.id) is None
        assert await port.list_for_project(theirs) == []
