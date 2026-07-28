from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.infra.persistence.files import LocalFileRepository

repo = LocalFileRepository()


@pytest.mark.unit
def test__write_read_roundtrip(tmp_path: Path) -> None:
    repo.write(tmp_path, "a/b/main.tex", b"hello")
    assert repo.read(tmp_path, "a/b/main.tex") == b"hello"
    assert repo.exists(tmp_path, "a/b/main.tex") is True
    assert repo.exists(tmp_path, "a/b/missing.tex") is False


@pytest.mark.unit
def test__delete_file(tmp_path: Path) -> None:
    repo.write(tmp_path, "main.tex", b"x")
    repo.delete(tmp_path, "main.tex")
    assert repo.exists(tmp_path, "main.tex") is False


@pytest.mark.unit
def test__delete_directory_recursive(tmp_path: Path) -> None:
    repo.write(tmp_path, "chapters/intro.tex", b"x")
    repo.write(tmp_path, "chapters/body.tex", b"y")
    repo.delete(tmp_path, "chapters")
    assert repo.exists(tmp_path, "chapters") is False


@pytest.mark.unit
def test__delete_missing__raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        repo.delete(tmp_path, "nope.tex")


@pytest.mark.unit
def test__move_renames_file(tmp_path: Path) -> None:
    repo.write(tmp_path, "old.tex", b"data")
    repo.move(tmp_path, "old.tex", "sub/new.tex")
    assert repo.exists(tmp_path, "old.tex") is False
    assert repo.read(tmp_path, "sub/new.tex") == b"data"


@pytest.mark.unit
def test__move_to_existing__raises_file_exists(tmp_path: Path) -> None:
    repo.write(tmp_path, "a.tex", b"a")
    repo.write(tmp_path, "b.tex", b"b")
    with pytest.raises(FileExistsError):
        repo.move(tmp_path, "a.tex", "b.tex")


@pytest.mark.unit
def test__move_missing_source__raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        repo.move(tmp_path, "ghost.tex", "x.tex")


@pytest.mark.unit
def test__mkdir_creates_directory(tmp_path: Path) -> None:
    repo.mkdir(tmp_path, "images/figures")
    assert (tmp_path / "images" / "figures").is_dir()


@pytest.mark.unit
def test__mkdir_existing__raises_file_exists(tmp_path: Path) -> None:
    repo.mkdir(tmp_path, "images")
    with pytest.raises(FileExistsError):
        repo.mkdir(tmp_path, "images")


@pytest.mark.unit
def test__delete_internal_studio_dir__refused(tmp_path: Path) -> None:
    (tmp_path / ".hse-studio" / "git").mkdir(parents=True)
    with pytest.raises(PermissionError):
        repo.delete(tmp_path, ".hse-studio")
    with pytest.raises(PermissionError):
        repo.delete(tmp_path, ".hse-studio/git")


@pytest.mark.unit
def test__delete_project_root__refused(tmp_path: Path) -> None:
    with pytest.raises(PermissionError):
        repo.delete(tmp_path, "")
    with pytest.raises(PermissionError):
        repo.delete(tmp_path, ".")


@pytest.mark.unit
def test__path_traversal__refused(tmp_path: Path) -> None:
    with pytest.raises(PermissionError):
        repo.delete(tmp_path, "../escape.tex")
    with pytest.raises(PermissionError):
        repo.move(tmp_path, "../a", "b")
    with pytest.raises(PermissionError):
        repo.mkdir(tmp_path, "../../evil")


@pytest.mark.unit
def test__list_dirs__includes_empty_and_skips_studio(tmp_path: Path) -> None:
    repo.write(tmp_path, "vkr/vkr.tex", b"x")  # creates vkr/
    repo.mkdir(tmp_path, "assets/img")  # empty nested dirs
    (tmp_path / ".hse-studio" / "git").mkdir(parents=True)
    dirs = repo.list_dirs(tmp_path)
    assert "vkr" in dirs
    assert "assets" in dirs
    assert "assets/img" in dirs  # empty dir still listed
    assert all(not d.startswith(".hse-studio") for d in dirs)
