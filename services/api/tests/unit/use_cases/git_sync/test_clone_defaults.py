from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from hse_doc_studio.core.paths import Mount, PathMapping
from hse_doc_studio.use_cases.git_sync.clone_project import GetCloneDefaultsUC

pytestmark = pytest.mark.unit


def _uc(root: Path, known: list[Path] | None = None) -> GetCloneDefaultsUC:
    locator = MagicMock()
    locator.list_all = AsyncMock(return_value=known or [])
    return GetCloneDefaultsUC(root, locator)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("course-paper", "course-paper"),
        ("  Курсовая работа  ", "Курсовая-работа"),
        ("a/b\\c:d", "a-b-c-d"),
        ("..hidden..", "hidden"),
        ("---", "project"),
        ("", "project"),
        (None, "project"),
        ("x" * 200, "x" * 60),
    ],
)
async def test__execute__unsafe_symbols_removed(tmp_path: Path, name: str | None, expected: str) -> None:
    assert await _uc(tmp_path).execute(name) == tmp_path / expected


async def test__execute__name_taken__gets_numeric_suffix(tmp_path: Path) -> None:
    (tmp_path / "course-paper").mkdir()
    (tmp_path / "course-paper-2").mkdir()

    assert await _uc(tmp_path).execute("course-paper") == tmp_path / "course-paper-3"


async def test__execute__folder_known_to_index__is_skipped(tmp_path: Path) -> None:
    known = tmp_path / "course-paper"

    assert await _uc(tmp_path, [known]).execute("course-paper") == tmp_path / "course-paper-2"


async def test__execute__server_names__are_free_uuid_folders_under_the_root(tmp_path: Path) -> None:
    locator = MagicMock()
    locator.list_all = AsyncMock(return_value=[])

    folder = await GetCloneDefaultsUC(tmp_path, locator, uuid_names=True).execute("Курсовая")

    assert folder.parent == tmp_path
    assert UUID(folder.name)


class _Settings:
    def __init__(self, stored: dict[str, object]) -> None:
        self.stored = stored

    async def get(self) -> dict[str, object]:
        return self.stored


def _with_settings(root: Path, stored: dict[str, object], mounts: list[Mount] | None = None) -> GetCloneDefaultsUC:
    locator = MagicMock()
    locator.list_all = AsyncMock(return_value=[])
    return GetCloneDefaultsUC(
        root,
        locator,
        settings_repo=_Settings(stored),
        paths=PathMapping(mounts or []),  # type: ignore[arg-type]
    )


async def test__execute__projects_dir_setting__replaces_the_standard_root(tmp_path: Path) -> None:
    chosen = tmp_path / "my-projects"

    folder = await _with_settings(tmp_path / "std", {"projects_dir": str(chosen)}).execute("ВКР")

    assert folder == chosen / "ВКР"


@pytest.mark.parametrize("stored", [{}, {"projects_dir": None}, {"projects_dir": "  "}, {"projects_dir": 5}])
async def test__execute__projects_dir_unset_or_broken__standard_root(tmp_path: Path, stored: dict[str, object]) -> None:
    assert await _with_settings(tmp_path, stored).execute("a") == tmp_path / "a"


async def test__execute__projects_dir_is_a_host_path__mapped_into_the_container(tmp_path: Path) -> None:
    mounts = [Mount(container="/data", host="/Users/anna/Studio")]

    folder = await _with_settings(tmp_path, {"projects_dir": "/Users/anna/Studio/work"}, mounts).execute("a")

    assert folder == Path("/data/work/a")


async def test__execute__projects_dir_outside_the_mounts__falls_back_to_the_standard_root(tmp_path: Path) -> None:
    mounts = [Mount(container="/data", host="/Users/anna/Studio")]

    assert await _with_settings(tmp_path, {"projects_dir": "/elsewhere"}, mounts).execute("a") == tmp_path / "a"
