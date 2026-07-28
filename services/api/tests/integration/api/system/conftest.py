from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path

import pytest_asyncio
from hse_doc_studio.core.update.entities import ReleaseEntry, UpdateFeedProbe
from httpx import ASGITransport, AsyncClient

from tests.fixtures.app import UnsupportedSelfUpdateGateway, create_test_app, create_test_container


class FakeUpdateFeed:
    """Stand-in for the real GitHub Releases gateway — no network in tests.

    Records how many times it was asked, so tests can prove the check runs on
    demand rather than on every page load.
    """

    def __init__(
        self,
        releases: tuple[ReleaseEntry, ...] = (),
        *,
        checked: bool = True,
        reason: str = "",
    ) -> None:
        self.probe_result = UpdateFeedProbe(releases=releases, checked=checked, reason=reason)
        self.calls = 0

    async def probe(self) -> UpdateFeedProbe:
        self.calls += 1
        return self.probe_result


async def _client(
    tmp_path: Path,
    feed: FakeUpdateFeed | None = None,
    self_updater: UnsupportedSelfUpdateGateway | None = None,
) -> AsyncGenerator[AsyncClient]:
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    container = create_test_container(data_dir, update_feed=feed, self_updater=self_updater)
    app = create_test_app(container)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    await container.close()


def updatable_client(
    tmp_path: Path,
    self_updater: UnsupportedSelfUpdateGateway,
) -> AsyncGenerator[AsyncClient]:
    """Приложение, которое умеет подменять себя (шлюз — фейковый)."""
    return _client(tmp_path, self_updater=self_updater)


@pytest_asyncio.fixture
async def newer_release_feed() -> FakeUpdateFeed:
    # 999.0.0 заведомо больше любой реальной версии продукта — сравнение обязано
    # сказать «обновление есть», не завися от текущего номера в __init__.py.
    # Ниже — версии, на которые можно откатиться.
    return FakeUpdateFeed(
        releases=(
            ReleaseEntry(version="999.0.0", date="2026-08-01", notes=("Что-то новое",)),
            ReleaseEntry(version="0.0.2", date="2026-05-02", notes=("Постарше",)),
            ReleaseEntry(version="0.0.1", date="2026-05-01", notes=("Самая ранняя",)),
        )
    )


@pytest_asyncio.fixture
async def unreachable_feed() -> FakeUpdateFeed:
    return FakeUpdateFeed(checked=False, reason="feed is unreachable")


@pytest_asyncio.fixture
async def app_with_newer_release(tmp_path: Path, newer_release_feed: FakeUpdateFeed) -> AsyncGenerator[AsyncClient]:
    async for client in _client(tmp_path, newer_release_feed):
        yield client


@pytest_asyncio.fixture
async def app_with_unreachable_feed(tmp_path: Path, unreachable_feed: FakeUpdateFeed) -> AsyncGenerator[AsyncClient]:
    async for client in _client(tmp_path, unreachable_feed):
        yield client


@pytest_asyncio.fixture
async def self_updater() -> UnsupportedSelfUpdateGateway:
    return UnsupportedSelfUpdateGateway(can_update=True)


@pytest_asyncio.fixture
async def updatable_app(tmp_path: Path, self_updater: UnsupportedSelfUpdateGateway) -> AsyncGenerator[AsyncClient]:
    async for client in updatable_client(tmp_path, self_updater):
        yield client
