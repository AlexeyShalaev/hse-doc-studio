from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.infra.persistence.project import JsonProjectRepository

from tests.factories import make_document, make_project

repo = JsonProjectRepository()


@pytest.mark.unit
def test__project_repository__file_not_exists__returns_none(tmp_path: Path) -> None:
    assert repo.get(tmp_path) is None


@pytest.mark.unit
def test__project_repository__save_creates_hse_studio_dir(tmp_path: Path) -> None:
    project = make_project(folder=tmp_path)
    repo.save(project)
    assert (tmp_path / ".hse-studio" / "project.json").exists()


@pytest.mark.unit
def test__project_repository__save_and_get_roundtrip(tmp_path: Path) -> None:
    project = make_project(folder=tmp_path, name="My VKR")
    repo.save(project)
    restored = repo.get(tmp_path)
    assert restored is not None
    assert restored.id == project.id
    assert restored.name == "My VKR"
    assert restored.folder == tmp_path


@pytest.mark.unit
def test__project_repository__save_with_documents_and_get(tmp_path: Path) -> None:
    project = make_project(folder=tmp_path, documents=[make_document("vkr"), make_document("pres")])
    repo.save(project)
    restored = repo.get(tmp_path)
    assert restored is not None
    assert len(restored.documents) == 2
    assert restored.documents[0].id == "vkr"


@pytest.mark.unit
def test__project_repository__corrupted_json__returns_none(tmp_path: Path) -> None:
    studio = tmp_path / ".hse-studio"
    studio.mkdir()
    (studio / "project.json").write_text("not valid json{{{", encoding="utf-8")
    assert repo.get(tmp_path) is None


@pytest.mark.unit
def test__project_repository__save_overwrites_existing(tmp_path: Path) -> None:
    project = make_project(folder=tmp_path, name="Original")
    repo.save(project)
    project.name = "Updated"
    repo.save(project)
    restored = repo.get(tmp_path)
    assert restored is not None
    assert restored.name == "Updated"


@pytest.mark.unit
def test__project_repository__get_from_nonexistent_dir__returns_none(tmp_path: Path) -> None:
    nonexistent = tmp_path / "does-not-exist"
    assert repo.get(nonexistent) is None


@pytest.mark.unit
def test__project_repository__survives_folder_move(tmp_path: Path) -> None:
    # The scenario that motivated dropping the persisted "folder" field: user
    # moves the project directory on disk; project.json must still describe
    # the project correctly at the new location.
    original = tmp_path / "original-name"
    original.mkdir()
    project = make_project(folder=original, name="Moved Project")
    repo.save(project)

    moved = tmp_path / "renamed"
    original.rename(moved)

    restored = repo.get(moved)
    assert restored is not None
    assert restored.id == project.id
    assert restored.folder == moved
    assert restored.name == "Moved Project"


@pytest.mark.unit
def test__project_repository__save_does_not_persist_folder_field(tmp_path: Path) -> None:
    project = make_project(folder=tmp_path)
    repo.save(project)
    raw = (tmp_path / ".hse-studio" / "project.json").read_text(encoding="utf-8")
    assert '"folder"' not in raw
