"""Контрактный набор IProjectLocator: Json (перебор projects.json) и InMemory ведут себя одинаково."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.projects.locator import IProjectLocator
from hse_doc_studio.infra.persistence.project import JsonProjectRepository
from hse_doc_studio.infra.persistence.project_index import JsonProjectIndexRepository
from hse_doc_studio.infra.persistence.project_locator import LocalProjectLocator

from tests.contract.base import PortContract
from tests.factories import make_project
from tests.fakes.project_locator import InMemoryProjectLocator
from tests.fixtures.actors import as_actor


class _InMemoryHarness:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._impl = InMemoryProjectLocator()
        self.locator: IProjectLocator = self._impl

    def add(self, name: str) -> Project:
        project = make_project(folder=self._root / name, name=name)
        self._impl.add(project)
        return project


class _JsonHarness:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._projects = JsonProjectRepository()
        self._index = JsonProjectIndexRepository(root / "data")
        self.locator: IProjectLocator = LocalProjectLocator(self._index, self._projects)

    def add(self, name: str) -> Project:
        folder = self._root / name
        folder.mkdir(parents=True)
        project = make_project(folder=folder, name=name)
        self._projects.save(project)
        self._index.register(folder)
        return project


def _folder_and_id(harness: Any, name: str) -> tuple[Path, UUID]:
    project = harness.add(name)
    return project.folder, project.id


_FACTORIES: dict[str, Callable[[Path], Any]] = {"inmemory": _InMemoryHarness, "json": _JsonHarness}


class TestProjectLocatorContract(PortContract):
    implementations = _FACTORIES

    async def test__folder_of__known_project__returns_folder(self, port: Any) -> None:
        folder, project_id = _folder_and_id(port, "alpha")
        assert await port.locator.folder_of(project_id) == folder

    async def test__folder_of__unknown_id__returns_none(self, port: Any) -> None:
        _folder_and_id(port, "alpha")
        assert await port.locator.folder_of(uuid4()) is None

    async def test__locate__known_project__returns_folder_and_project(self, port: Any) -> None:
        folder, project_id = _folder_and_id(port, "alpha")
        found = await port.locator.locate(project_id)
        assert found is not None
        assert found[0] == folder
        assert found[1].id == project_id

    async def test__locate__picks_matching_among_several(self, port: Any) -> None:
        _folder_and_id(port, "alpha")
        folder, project_id = _folder_and_id(port, "beta")
        _folder_and_id(port, "gamma")
        assert await port.locator.folder_of(project_id) == folder

    async def test__list_visible__keeps_registration_order(self, port: Any) -> None:
        folders = [_folder_and_id(port, name)[0] for name in ("c", "a", "b")]
        assert await port.locator.list_visible(None) == folders
        assert await port.locator.list_all() == folders

    async def test__list_visible__any_actor__same_list_in_local_mode(self, port: Any, two_actors: Any) -> None:
        owner, stranger = two_actors
        folder, _ = _folder_and_id(port, "alpha")
        with as_actor(owner):
            assert await port.locator.list_visible(owner) == [folder]
        with as_actor(stranger):
            assert await port.locator.list_visible(stranger) == [folder]

    async def test__unregister__removes_folder_from_lists_and_lookup(self, port: Any) -> None:
        folder, project_id = _folder_and_id(port, "alpha")
        await port.locator.unregister(folder)
        assert await port.locator.list_all() == []
        assert await port.locator.folder_of(project_id) is None

    async def test__register__twice__lists_folder_once(self, port: Any) -> None:
        folder, project_id = _folder_and_id(port, "alpha")
        await port.locator.register(folder)
        assert await port.locator.list_all() == [folder]
        assert await port.locator.folder_of(project_id) == folder
