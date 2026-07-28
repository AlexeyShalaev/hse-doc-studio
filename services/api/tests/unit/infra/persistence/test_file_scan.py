"""Обход дерева проекта: что в него попадает, а что отсекается на входе."""

from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.infra.persistence.files import LocalFileRepository


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Проект с пользовательским содержимым и служебными каталогами рядом."""
    (tmp_path / "thesis").mkdir()
    (tmp_path / "thesis" / "thesis.tex").write_text("x", encoding="utf-8")
    (tmp_path / "images").mkdir()  # пустая пользовательская папка

    # Промежуточные файлы latexmk — пересоздаются на каждой сборке.
    build = tmp_path / "thesis" / ".build" / "thesis"
    build.mkdir(parents=True)
    (build / "thesis.aux").write_text("x", encoding="utf-8")
    (build / "thesis.log").write_text("x", encoding="utf-8")

    # Служебное хранилище Студии: git версий, записи сборок.
    studio = tmp_path / ".hse-studio" / "git"
    studio.mkdir(parents=True)
    (studio / "HEAD").write_text("x", encoding="utf-8")
    return tmp_path


@pytest.mark.unit
def test__scan__lists_user_files_and_folders(project: Path) -> None:
    paths = {e.path for e in LocalFileRepository().scan(project)}

    assert "thesis/thesis.tex" in paths
    assert "thesis" in paths
    assert "images" in paths, "пустая пользовательская папка обязана быть узлом дерева"


@pytest.mark.unit
def test__scan__build_artifacts_are_not_user_content(project: Path) -> None:
    paths = {e.path for e in LocalFileRepository().scan(project)}

    assert not any(p.startswith("thesis/.build") for p in paths)


@pytest.mark.unit
def test__scan__internal_studio_folder_is_never_exposed(project: Path) -> None:
    paths = {e.path for e in LocalFileRepository().scan(project)}

    assert not any(p.startswith(".hse-studio") for p in paths)


@pytest.mark.unit
def test__scan__carries_stat_so_callers_need_no_second_syscall(project: Path) -> None:
    entry = next(e for e in LocalFileRepository().scan(project) if e.path == "thesis/thesis.tex")

    assert entry.is_dir is False
    assert entry.size == 1
    assert entry.mtime > 0


@pytest.mark.unit
def test__scan__missing_folder__is_empty_not_an_error(tmp_path: Path) -> None:
    assert LocalFileRepository().scan(tmp_path / "nope") == []


@pytest.mark.unit
def test__list_files_and_list_dirs__agree_with_scan(project: Path) -> None:
    repo = LocalFileRepository()
    entries = repo.scan(project)

    assert repo.list_files(project) == [e.path for e in entries if not e.is_dir]
    assert repo.list_dirs(project) == [e.path for e in entries if e.is_dir]
