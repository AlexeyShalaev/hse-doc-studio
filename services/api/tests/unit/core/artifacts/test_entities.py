from __future__ import annotations

from uuid import UUID

import pytest
from hse_doc_studio.core.artifacts.entities import artifact_key, is_safe_doc_id, safe_file_name

PROJECT = UUID("11111111-1111-1111-1111-111111111111")
ARTIFACT = UUID("22222222-2222-2222-2222-222222222222")


@pytest.mark.parametrize("doc_id", ["coursework", "coursework--anna-petrova", "doc_1.v2", "a"])
def test__is_safe_doc_id__ordinary_ids__accepted(doc_id: str) -> None:
    assert is_safe_doc_id(doc_id)


@pytest.mark.parametrize("doc_id", ["", "../x", "a/b", ".hidden", "a b", "a" * 129, "док"])
def test__is_safe_doc_id__path_like_or_odd_ids__rejected(doc_id: str) -> None:
    assert not is_safe_doc_id(doc_id)


def test__artifact_key__under_project_objects_prefix() -> None:
    key = artifact_key(PROJECT, "coursework", ARTIFACT)

    assert key == f"artifacts/{PROJECT}/uploads/coursework/{ARTIFACT}.pdf"


def test__artifact_key__unsafe_doc_id__refused() -> None:
    with pytest.raises(ValueError, match="doc_id"):
        artifact_key(PROJECT, "../escape", ARTIFACT)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        (None, "coursework.pdf"),
        ("", "coursework.pdf"),
        ("Курсовая.pdf", "Курсовая.pdf"),
        ("a/b\\c.PDF", "a_b_c.pdf"),
        ("..", "coursework.pdf"),
        ("report", "report.pdf"),
    ],
)
def test__safe_file_name__cleans_paths_and_keeps_pdf_suffix(name: str | None, expected: str) -> None:
    assert safe_file_name("coursework", name) == expected
