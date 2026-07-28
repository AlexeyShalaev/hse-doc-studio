from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """Temporary data directory with required subdirs."""
    (tmp_path / "projects").mkdir()
    return tmp_path


@pytest.fixture
def tmp_project_folder(tmp_path: Path) -> Path:
    """A temporary project folder with .hse-studio/ created."""
    (tmp_path / ".hse-studio").mkdir()
    return tmp_path
