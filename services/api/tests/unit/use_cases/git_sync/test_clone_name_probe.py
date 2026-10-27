"""Проба файловой системы при клонировании не оставляет следов."""

from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.use_cases.git_sync.clone_project import _folds_names

pytestmark = pytest.mark.unit


def test__folds_names__leaves_the_folder_untouched(tmp_path: Path) -> None:
    assert isinstance(_folds_names(tmp_path), bool)
    assert list(tmp_path.iterdir()) == []


def test__folds_names__unwritable_folder__is_false(tmp_path: Path) -> None:
    assert _folds_names(tmp_path / "missing") is False
