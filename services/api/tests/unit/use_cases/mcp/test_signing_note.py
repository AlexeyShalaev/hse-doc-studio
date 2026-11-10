"""Пометка `signing_note` у тулов MCP, которые правят и собирают (docs/design/signing-route.md, 12.10)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.agent.entities import ToolResult
from hse_doc_studio.core.signing_route.ports import NoSigningRoutes, SigningDoc
from hse_doc_studio.use_cases.mcp.call_tool import _edit_target
from hse_doc_studio.use_cases.mcp.catalog import MCP_TOOL_RULES, RULES_BY_NAME, Touch
from hse_doc_studio.use_cases.mcp.signing_note import (
    EditTarget,
    SigningNotes,
    affected,
    doc_of_path,
    folder_of,
    note_text,
    with_note,
)

_ROUTE = uuid4()
_SENT = datetime(2026, 11, 10, 14, 32, tzinfo=UTC)
_FOLDERS = {"topic": "topic", "vkr--ivanov": "ivanov/vkr", "report": "report", "root": ""}
_HELD = (SigningDoc("topic", _ROUTE, _SENT), SigningDoc("vkr--ivanov", _ROUTE, None))


@pytest.mark.parametrize(
    ("source", "folder"),
    [("vkr/vkr.tex", "vkr"), ("ivanov/vkr/vkr.tex", "ivanov/vkr"), ("./topic/topic.tex", "topic"), ("main.tex", "")],
)
def test__folder_of__folder_of_the_source_file(source: str, folder: str) -> None:
    assert folder_of(source) == folder


@pytest.mark.parametrize(
    ("path", "doc_id"),
    [
        ("topic/sections/intro.tex", "topic"),
        ("topic", "topic"),
        ("ivanov/vkr/img/a.png", "vkr--ivanov"),
        ("./report/report.tex", "report"),
        ("topical/x.tex", None),
        ("common/meta.tex", None),
        ("refs.bib", None),
    ],
)
def test__doc_of_path__document_folder__shared_files_have_none(path: str, doc_id: str | None) -> None:
    assert doc_of_path(path, _FOLDERS) == doc_id


def test__doc_of_path__deepest_folder_wins() -> None:
    folders = {"outer": "a", "inner": "a/b"}

    assert doc_of_path("a/b/c.tex", folders) == "inner"
    assert doc_of_path("a/c.tex", folders) == "outer"


def test__affected__file_of_a_document__only_that_document() -> None:
    hit = affected(EditTarget(paths=("topic/topic.tex",)), _HELD, _FOLDERS)

    assert [d.doc_id for d in hit] == ["topic"]


def test__affected__file_of_a_document_off_the_route__nothing() -> None:
    assert affected(EditTarget(paths=("report/report.tex",)), _HELD, _FOLDERS) == ()


def test__affected__shared_file_or_project__every_document_on_signing() -> None:
    shared = affected(EditTarget(paths=("common/meta.tex",)), _HELD, _FOLDERS)
    project = affected(EditTarget(project=True), _HELD, _FOLDERS)

    assert shared == project == _HELD


def test__affected__moved_into_a_document_folder__that_document() -> None:
    hit = affected(EditTarget(paths=("report/a.tex", "ivanov/vkr/a.tex")), _HELD, _FOLDERS)

    assert [d.doc_id for d in hit] == ["vkr--ivanov"]


def test__affected__document_by_id() -> None:
    assert [d.doc_id for d in affected(EditTarget(doc_ids=("topic",)), _HELD, _FOLDERS)] == ["topic"]
    assert affected(EditTarget(doc_ids=("report",)), _HELD, _FOLDERS) == ()


def test__note_text__one_document__version_date_and_who_sends_the_new_version() -> None:
    text = note_text(_HELD[:1])

    assert text.startswith("Документ на подписании (topic): изменения не попадут в подписываемую версию от 10.11.2026")
    assert "«Отправить новую версию»" in text


def test__note_text__several_documents__listed_with_dates() -> None:
    text = note_text(_HELD)

    assert text.startswith("Документы на подписании: topic (версия от 10.11.2026), vkr--ivanov.")
    assert "не попадут в подписываемые версии" in text


def test__with_note__json_object__field_signing_note() -> None:
    result = with_note(ToolResult.ok(json.dumps({"path": "a.tex"})), "заметка")

    assert json.loads(result.text) == {"path": "a.tex", "signing_note": "заметка"}
    assert result.is_error is False


def test__with_note__plain_text__line_at_the_end() -> None:
    result = with_note(ToolResult.ok("a.tex перемещён в b.tex"), "заметка")

    assert result.text == "a.tex перемещён в b.tex\n\nsigning_note: заметка"


class _Gate(NoSigningRoutes):
    def __init__(self, held: tuple[SigningDoc, ...]) -> None:
        self.held = held

    async def on_signing(self, project_id: UUID) -> tuple[SigningDoc, ...]:
        return self.held


class _Documents:
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, inp: Any) -> Any:
        self.calls += 1
        entries = [
            SimpleNamespace(document=SimpleNamespace(id=doc_id), source_file=f"{folder}/{doc_id}.tex")
            for doc_id, folder in _FOLDERS.items()
            if folder
        ]
        return SimpleNamespace(entries=entries)


async def test__signing_notes__nothing_on_signing__no_note_and_no_document_lookup() -> None:
    documents = _Documents()
    notes = SigningNotes(_Gate(()), documents)  # type: ignore[arg-type]

    assert await notes.note(uuid4(), EditTarget(paths=("topic/topic.tex",))) is None
    assert documents.calls == 0


async def test__signing_notes__file_of_a_document_on_signing__note() -> None:
    notes = SigningNotes(_Gate(_HELD), _Documents())  # type: ignore[arg-type]

    note = await notes.note(uuid4(), EditTarget(paths=("topic/sections/a.tex",)))
    other = await notes.note(uuid4(), EditTarget(paths=("report/report.tex",)))

    assert note is not None
    assert "(topic)" in note
    assert other is None


@pytest.mark.parametrize(
    ("tool", "args", "target"),
    [
        ("edit_tex", {"path": "topic/topic.tex"}, EditTarget(paths=("topic/topic.tex",))),
        ("move_file", {"src": "a.tex", "dst": "topic/a.tex"}, EditTarget(paths=("a.tex", "topic/a.tex"))),
        ("compile_document", {"doc_id": "topic"}, EditTarget(doc_ids=("topic",))),
        ("set_document_variant", {"doc_id": "vkr--ivanov"}, EditTarget(doc_ids=("vkr--ivanov",))),
        ("set_project_meta", {}, EditTarget(project=True)),
    ],
)
def test__edit_target__from_the_tool_arguments(tool: str, args: dict[str, object], target: EditTarget) -> None:
    rule = RULES_BY_NAME[tool]
    assert rule.touches is not None

    assert _edit_target(rule.touches, rule.path_args, args) == target


def test__catalog__tools_that_edit_or_build_carry_the_note__read_tools_do_not() -> None:
    touching = {rule.name for rule in MCP_TOOL_RULES if rule.touches is not None}

    assert {"edit_tex", "write_file", "move_file", "delete_file", "compile_document"} <= touching
    assert all(not RULES_BY_NAME[name].meta.read_only for name in touching)
    assert all(RULES_BY_NAME[name].path_args for name in touching if RULES_BY_NAME[name].touches is Touch.paths)
