from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.infra.persistence.project_index import JsonProjectIndexRepository


@pytest.mark.unit
def test__project_index_repository__no_file__returns_empty(tmp_path: Path) -> None:
    repo = JsonProjectIndexRepository(tmp_path)
    assert repo.list_known() == []


@pytest.mark.unit
def test__project_index_repository__register__adds_folder(tmp_path: Path) -> None:
    repo = JsonProjectIndexRepository(tmp_path)
    folder = Path("/some/project")
    repo.register(folder)
    assert folder in repo.list_known()


@pytest.mark.unit
def test__project_index_repository__register_duplicate__no_duplicate_in_list(tmp_path: Path) -> None:
    repo = JsonProjectIndexRepository(tmp_path)
    folder = Path("/some/project")
    repo.register(folder)
    repo.register(folder)
    assert repo.list_known().count(folder) == 1


@pytest.mark.unit
def test__project_index_repository__unregister__removes_folder(tmp_path: Path) -> None:
    repo = JsonProjectIndexRepository(tmp_path)
    folder = Path("/some/project")
    repo.register(folder)
    repo.unregister(folder)
    assert folder not in repo.list_known()


@pytest.mark.unit
def test__project_index_repository__unregister_nonexistent__no_error(tmp_path: Path) -> None:
    repo = JsonProjectIndexRepository(tmp_path)
    repo.unregister(Path("/nonexistent/project"))


@pytest.mark.unit
def test__project_index_repository__multiple_folders__all_listed(tmp_path: Path) -> None:
    repo = JsonProjectIndexRepository(tmp_path)
    folders = [Path(f"/project/{i}") for i in range(3)]
    for f in folders:
        repo.register(f)
    listed = repo.list_known()
    for f in folders:
        assert f in listed


@pytest.mark.unit
def test__project_index_repository__corrupted_file__returns_empty(tmp_path: Path) -> None:
    repo = JsonProjectIndexRepository(tmp_path)
    (tmp_path / "projects.json").write_text("not valid json{{", encoding="utf-8")
    assert repo.list_known() == []
