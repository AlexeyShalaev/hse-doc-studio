"""Две Студии для сквозных тестов Git-синхронизации: у каждой свой data_dir, профиль и папки проектов."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
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


@pytest.fixture
def remote_not_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Тестовый git-сервер слушает 127.0.0.1, а http к localhost пускается без согласия (локальная Студия).

    Чтобы проверить отказ для обычного открытого http, loopback в тесте не считается своим компьютером.
    """
    monkeypatch.setattr("hse_doc_studio.core.git_sync.url.LOOPBACK_HOSTS", frozenset())
