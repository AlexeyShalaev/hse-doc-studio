from __future__ import annotations

import os
from pathlib import Path

import pytest
from hse_doc_studio.use_cases.template_update.planning import read_project_files

pytestmark = pytest.mark.unit


@pytest.fixture
def case_insensitive_is_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """Имитация APFS и NTFS: `is_file` находит файл по имени в любом регистре."""

    def is_file(self: Path) -> bool:
        return any(
            name.casefold() == self.name.casefold() and os.path.isfile(self.parent / name)
            for name in os.listdir(self.parent)
        )

    monkeypatch.setattr(Path, "is_file", is_file)


def test__read_project_files__exact_spelling__is_read(tmp_path: Path) -> None:
    (tmp_path / "NewFile.txt").write_bytes(b"x")

    assert read_project_files(tmp_path, ["NewFile.txt", "missing.txt"]) == {"NewFile.txt": b"x"}


def test__read_project_files__other_case_of_the_name__is_not_the_same_file(
    tmp_path: Path, case_insensitive_is_file: None
) -> None:
    # Переименование одной буквы регистра: файла с новым написанием на диске нет, иначе удаление старого стёрло бы его.
    (tmp_path / "NewFile.txt").write_bytes(b"x")

    assert read_project_files(tmp_path, ["newfile.txt"]) == {}
