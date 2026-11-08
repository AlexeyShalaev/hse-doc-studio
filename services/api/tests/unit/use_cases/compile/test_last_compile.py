"""Ссылка на последнюю сборку документа: своя, чужая (пришла синхронизацией), нечитаемый журнал."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from hse_doc_studio.core.entities import Document
from hse_doc_studio.core.enums import DocumentStatus
from hse_doc_studio.core.value_objects import ChecksOverride
from hse_doc_studio.use_cases.compile.last_compile import effective_last_compile_id, with_effective_last_compile

_FOLDER = Path("/p")
_T0 = datetime(2026, 11, 7, tzinfo=UTC)


class _Compiles:
    def __init__(self, *records: Any, broken: bool = False) -> None:
        self.records = list(records)
        self.broken = broken

    async def get_for_project(self, _folder: Path, compile_id: uuid.UUID) -> Any:
        if self.broken:
            raise OSError("disk")
        return next((r for r in self.records if r.id == compile_id), None)

    async def list_for_document(self, _folder: Path, doc_id: str) -> list[Any]:
        return [r for r in self.records if r.doc_id == doc_id]


def _record(doc_id: str, minutes: int) -> Any:
    return SimpleNamespace(id=uuid.uuid4(), doc_id=doc_id, started_at=_T0 + timedelta(minutes=minutes))


def _doc(pointer: uuid.UUID | None) -> Document:
    return Document(
        id="report",
        status=DocumentStatus.ok,
        chosen_variant=None,
        last_compile_id=pointer,
        checks_override=ChecksOverride(),
    )


async def test__own_pointer__kept() -> None:
    own = _record("report", 0)
    newer = _record("report", 10)
    doc = _doc(own.id)

    assert await effective_last_compile_id(_Compiles(own, newer), _FOLDER, doc) == own.id
    assert await with_effective_last_compile(_Compiles(own, newer), _FOLDER, doc) is doc


async def test__foreign_pointer__replaced_by_the_newest_local_build_of_this_document() -> None:
    old, newest, other_doc = _record("report", 0), _record("report", 30), _record("slides", 60)
    doc = _doc(uuid.uuid4())

    fixed = await with_effective_last_compile(_Compiles(newest, old, other_doc), _FOLDER, doc)

    assert fixed.last_compile_id == newest.id
    assert doc.last_compile_id != newest.id  # исходный документ не меняется


async def test__foreign_pointer_without_local_builds__is_none() -> None:
    assert await effective_last_compile_id(_Compiles(_record("slides", 0)), _FOLDER, _doc(uuid.uuid4())) is None


async def test__no_pointer_or_no_journal__left_as_is() -> None:
    pointer = uuid.uuid4()

    assert await effective_last_compile_id(_Compiles(_record("report", 0)), _FOLDER, _doc(None)) is None
    assert await effective_last_compile_id(None, _FOLDER, _doc(pointer)) == pointer


async def test__journal_unreadable__pointer_left_as_is() -> None:
    pointer = uuid.uuid4()

    assert await effective_last_compile_id(_Compiles(broken=True), _FOLDER, _doc(pointer)) == pointer
