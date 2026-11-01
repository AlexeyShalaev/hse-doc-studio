"""GetProjectUC на серверном индексе: проект ищет каталог, перебор папок не нужен."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.infra.projects.catalog_index import CatalogProjectIndex
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC


class _Locator:
    def __init__(self, found: tuple[Path, Project] | None) -> None:
        self.found = found

    async def locate(self, project_id: object) -> tuple[Path, Project] | None:
        return self.found


async def test__get_project__catalog_index__returns_located_project() -> None:
    project = MagicMock(spec=Project)
    index = CatalogProjectIndex(_Locator((Path("/srv/p"), project)))  # type: ignore[arg-type]
    repo = MagicMock()

    out = await GetProjectUC(repo, index).execute(GetProjectInput(project_id=uuid4()))

    assert out.project is project
    repo.get.assert_not_called()


async def test__get_project__catalog_index_without_row__not_found() -> None:
    index = CatalogProjectIndex(_Locator(None))  # type: ignore[arg-type]

    with pytest.raises(NotFoundError):
        await GetProjectUC(MagicMock(), index).execute(GetProjectInput(project_id=uuid4()))
