from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.infra.persistence.project import JsonProjectRepository
from hse_doc_studio.infra.persistence.project_index import JsonProjectIndexRepository
from hse_doc_studio.infra.persistence.project_locator import LocalProjectLocator

from tests.factories import make_project


@pytest.mark.unit
async def test__locate__unreadable_project_before_target__is_skipped(tmp_path: Path) -> None:
    projects = JsonProjectRepository()
    index = JsonProjectIndexRepository(tmp_path / "data")
    broken = tmp_path / "broken"
    (broken / ".hse-studio").mkdir(parents=True)
    (broken / ".hse-studio" / "project.json").write_text("{not json", encoding="utf-8")
    good = tmp_path / "good"
    good.mkdir()
    project = make_project(folder=good)
    projects.save(project)
    index.register(broken)
    index.register(good)

    found = await LocalProjectLocator(index, projects).locate(project.id)

    assert found is not None
    assert found[0] == good


@pytest.mark.unit
async def test__list_all__unknown_folder_in_index__is_kept(tmp_path: Path) -> None:
    index = JsonProjectIndexRepository(tmp_path / "data")
    missing = tmp_path / "missing"
    index.register(missing)

    assert await LocalProjectLocator(index, JsonProjectRepository()).list_all() == [missing]
