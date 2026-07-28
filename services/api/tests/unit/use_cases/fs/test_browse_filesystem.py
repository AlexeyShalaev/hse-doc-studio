"""Границы файлового браузера, когда приложение работает в контейнере.

Пользователю смонтирована одна папка; всё, что выше неё, — файловая система
образа, и попадать туда он не должен ни «наверх», ни ручным вводом пути.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.core.paths import Mount, PathMapping
from hse_doc_studio.infra.persistence.filesystem_browser import LocalFilesystemBrowser
from hse_doc_studio.use_cases.fs.browse_filesystem import (
    BrowseFilesystemInput,
    BrowseFilesystemUC,
)


@pytest.fixture
def mounted(tmp_path: Path) -> Path:
    root = tmp_path / "projects"
    (root / "vkr-ru").mkdir(parents=True)
    (tmp_path / "app").mkdir()  # «файловая система образа» рядом с маунтом
    return root


@pytest.fixture
def uc(mounted: Path) -> BrowseFilesystemUC:
    mapping = PathMapping([Mount(container=str(mounted), host="D:/study")])
    return BrowseFilesystemUC(browser=LocalFilesystemBrowser(), paths=mapping)


async def test__browse__no_path__opens_the_mounted_folder(uc: BrowseFilesystemUC, mounted: Path) -> None:
    out = await uc.execute(BrowseFilesystemInput(path=None))

    assert out.path == mounted.resolve()
    assert out.is_root is True


async def test__browse__mount_root__offers_no_way_up(uc: BrowseFilesystemUC, mounted: Path) -> None:
    out = await uc.execute(BrowseFilesystemInput(path=str(mounted)))

    assert out.parent is None, "выше корня маунта — файлы образа, туда ходить незачем"


async def test__browse__inside_the_mount__is_not_a_root_and_has_a_parent(uc: BrowseFilesystemUC, mounted: Path) -> None:
    out = await uc.execute(BrowseFilesystemInput(path=str(mounted / "vkr-ru")))

    assert out.is_root is False
    assert out.parent == mounted.resolve()


async def test__browse__path_outside_the_mount__falls_back_to_the_mount(
    uc: BrowseFilesystemUC, mounted: Path, tmp_path: Path
) -> None:
    # Ручной ввод пути не должен быть лазейкой наружу.
    out = await uc.execute(BrowseFilesystemInput(path=str(tmp_path / "app")))

    assert out.path == mounted.resolve()


async def test__browse__without_mounts__keeps_walking_the_whole_filesystem(tmp_path: Path) -> None:
    # Нативный запуск: ограничивать нечем и незачем — это машина пользователя.
    (tmp_path / "sub").mkdir()
    uc = BrowseFilesystemUC(browser=LocalFilesystemBrowser())

    out = await uc.execute(BrowseFilesystemInput(path=str(tmp_path / "sub")))

    assert out.path == (tmp_path / "sub").resolve()
    assert out.parent == tmp_path.resolve()
    assert out.is_root is False
