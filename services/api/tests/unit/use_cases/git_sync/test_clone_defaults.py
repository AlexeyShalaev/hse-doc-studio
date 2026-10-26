from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from hse_doc_studio.use_cases.git_sync.clone_project import GetCloneDefaultsUC

pytestmark = pytest.mark.unit


def _uc(root: Path, known: list[Path] | None = None) -> GetCloneDefaultsUC:
    index = MagicMock()
    index.list_known.return_value = known or []
    return GetCloneDefaultsUC(root, index)


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
        ("x" * 200, "x" * 60),
    ],
)
async def test__execute__unsafe_symbols_removed(tmp_path: Path, name: str | None, expected: str) -> None:
    assert await _uc(tmp_path).execute(name) == tmp_path / expected


async def test__execute__name_taken__gets_numeric_suffix(tmp_path: Path) -> None:
    (tmp_path / "course-paper").mkdir()
    (tmp_path / "course-paper-2").mkdir()

    assert await _uc(tmp_path).execute("course-paper") == tmp_path / "course-paper-3"


async def test__execute__folder_known_to_index__is_skipped(tmp_path: Path) -> None:
    known = tmp_path / "course-paper"

    assert await _uc(tmp_path, [known]).execute("course-paper") == tmp_path / "course-paper-2"
