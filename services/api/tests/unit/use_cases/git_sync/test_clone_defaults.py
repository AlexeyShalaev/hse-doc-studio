from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.use_cases.git_sync.clone_defaults import CloneDefaultsInput, GetCloneDefaultsUC, folder_name

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("course-paper", "course-paper"),
        ("  Курсовая работа  ", "Курсовая-работа"),
        ("a/b\\c:d", "a-b-c-d"),
        ("..hidden..", "hidden"),
        ("---", "project"),
        ("", "project"),
        (None, "project"),
        ("x" * 200, "x" * 64),
    ],
)
def test__folder_name__unsafe_symbols_removed(name: str | None, expected: str) -> None:
    assert folder_name(name) == expected


async def test__execute__free_name__is_under_projects_dir(tmp_path: Path) -> None:
    folder = await GetCloneDefaultsUC(tmp_path).execute(CloneDefaultsInput(name="course-paper"))

    assert folder == tmp_path / "course-paper"


async def test__execute__name_taken__gets_numeric_suffix(tmp_path: Path) -> None:
    (tmp_path / "course-paper").mkdir()
    (tmp_path / "course-paper-2").mkdir()

    folder = await GetCloneDefaultsUC(tmp_path).execute(CloneDefaultsInput(name="course-paper"))

    assert folder == tmp_path / "course-paper-3"


async def test__execute__no_name__uses_fallback(tmp_path: Path) -> None:
    folder = await GetCloneDefaultsUC(tmp_path).execute(CloneDefaultsInput())

    assert folder == tmp_path / "project"
