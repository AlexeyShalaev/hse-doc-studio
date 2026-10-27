"""Две Студии для сквозных тестов Git-синхронизации: у каждой свой data_dir, профиль и папки проектов."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio

from tests.integration.api.git_sync.studios import ANNA, BORIS, Studio


@pytest_asyncio.fixture
async def anna(tmp_path: Path) -> AsyncIterator[Studio]:
    studio = await Studio.open(tmp_path / "anna", "anna", ANNA)
    yield studio
    await studio.close()


@pytest_asyncio.fixture
async def boris(tmp_path: Path) -> AsyncIterator[Studio]:
    studio = await Studio.open(tmp_path / "boris", "boris", BORIS)
    yield studio
    await studio.close()
