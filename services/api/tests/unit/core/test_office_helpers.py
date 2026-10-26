from __future__ import annotations

import pytest
from hse_doc_studio.core.catalog import SubmissionDocItem
from hse_doc_studio.core.office import (
    ConvertRequest,
    custom_docs_to_convert,
    resolve_custom_doc_decision,
    sibling_pdf_path,
)

from tests.factories import make_custom_file_override, make_document, make_project


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("tz/_custom/ТЗ.docx", "tz/_custom/ТЗ.pdf"),
        ("presentation/slides.pptx", "presentation/slides.pdf"),
        ("a.b/c.tar.docx", "a.b/c.tar.pdf"),
        ("noext", "noext.pdf"),
    ],
)
def test__sibling_pdf_path__replaces_suffix_posix(path: str, expected: str) -> None:
    assert sibling_pdf_path(path) == expected


@pytest.mark.parametrize(
    ("remembered", "decisions", "expected"),
    [
        (None, None, None),
        (True, None, True),
        (True, {}, True),
        (True, {"tz": False}, False),
        (False, {"tz": True}, True),
        (None, {"tz": True}, True),
        (True, {"other": False}, True),
    ],
)
def test__resolve_custom_doc_decision__explicit_beats_remembered(
    remembered: bool | None, decisions: dict[str, bool] | None, expected: bool | None
) -> None:
    assert resolve_custom_doc_decision("tz", remembered, decisions) == expected


def _doc(doc_id: str, ext: str, *, remembered: bool | None = None):  # noqa: ANN202
    return make_document(
        doc_id,
        custom_file=make_custom_file_override(
            original_filename=f"{doc_id}{ext}",
            stored_path=f"{doc_id}/_custom/{doc_id}{ext}",
            ext=ext,
            convert_to_pdf_at_package=remembered,
        ),
    )


def _items(*doc_ids: str) -> list[SubmissionDocItem]:
    return [SubmissionDocItem(doc_id=d, signatures=()) for d in doc_ids]


def test__custom_docs_to_convert__decision_sibling_and_source_matrix() -> None:
    project = make_project(
        documents=[
            _doc("convert", ".docx"),
            _doc("remembered", ".pptx", remembered=True),
            _doc("declined", ".docx", remembered=True),
            _doc("undecided", ".docx"),
            _doc("has_sibling", ".docx"),
            _doc("no_source", ".docx"),
            _doc("pdf", ".pdf"),
            _doc("not_office", ".zip"),
            make_document("template_only"),
        ]
    )
    files = {
        "convert/_custom/convert.docx",
        "remembered/_custom/remembered.pptx",
        "declined/_custom/declined.docx",
        "undecided/_custom/undecided.docx",
        "has_sibling/_custom/has_sibling.docx",
        "has_sibling/_custom/has_sibling.pdf",
        "pdf/_custom/pdf.pdf",
        "not_office/_custom/not_office.zip",
    }
    decisions = {
        "convert": True,
        "declined": False,
        "has_sibling": True,
        "no_source": True,
        "pdf": True,
        "not_office": True,
        "template_only": True,
        "unknown_doc": True,
    }

    result = custom_docs_to_convert(
        project,
        _items(
            "convert",
            "remembered",
            "declined",
            "undecided",
            "has_sibling",
            "no_source",
            "pdf",
            "not_office",
            "template_only",
            "unknown_doc",
        ),  # fmt: skip
        decisions,
        files.__contains__,
    )

    assert result == [
        ConvertRequest("convert", "convert/_custom/convert.docx", "convert/_custom/convert.pdf"),
        ConvertRequest("remembered", "remembered/_custom/remembered.pptx", "remembered/_custom/remembered.pdf"),
    ]


def test__custom_docs_to_convert__keeps_doc_items_order_and_skips_duplicates() -> None:
    project = make_project(documents=[_doc("a", ".docx"), _doc("b", ".docx")])
    files = {"a/_custom/a.docx", "b/_custom/b.docx"}

    result = custom_docs_to_convert(project, _items("b", "a", "b"), {"a": True, "b": True}, files.__contains__)

    assert [r.doc_id for r in result] == ["b", "a"]
