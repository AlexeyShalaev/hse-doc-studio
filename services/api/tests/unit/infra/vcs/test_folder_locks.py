from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from hse_doc_studio.infra.vcs.folder_locks import VcsFolderLocks

pytestmark = pytest.mark.unit


def test__for_folder__same_resolved_path__same_lock_object(tmp_path: Path) -> None:
    locks = VcsFolderLocks()
    (tmp_path / "proj").mkdir()
    direct = locks.for_folder(tmp_path / "proj")
    roundabout = locks.for_folder(tmp_path / "proj" / ".." / "proj")
    assert direct is roundabout


def test__for_folder__different_paths__different_locks(tmp_path: Path) -> None:
    locks = VcsFolderLocks()
    assert locks.for_folder(tmp_path / "a") is not locks.for_folder(tmp_path / "b")


async def test__for_folder__gather__is_mutually_exclusive(tmp_path: Path) -> None:
    locks = VcsFolderLocks()
    inside = 0
    max_inside = 0

    async def worker() -> None:
        nonlocal inside, max_inside
        async with locks.for_folder(tmp_path):
            inside += 1
            max_inside = max(max_inside, inside)
            await asyncio.sleep(0.01)
            inside -= 1

    await asyncio.gather(*(worker() for _ in range(5)))
    assert max_inside == 1
