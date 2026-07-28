from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest_asyncio
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from hse_doc_studio.api.routers.v1 import api_router
from hse_doc_studio.core.agent.entities import NormalizedTurn
from httpx import ASGITransport, AsyncClient

from tests.factories import project_api_payload
from tests.fixtures.app import create_test_container


async def create_project(client: AsyncClient, folder: Path) -> str:
    folder.mkdir()
    resp = await client.post("/api/v1/projects", json=project_api_payload(str(folder)))
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


class FakeAgentProvider:
    """Queue of canned turns — swapped in for the real SDK-backed provider so
    chat/agent integration tests exercise the real router/DI/use-case/JSON
    persistence chain without ever calling a real AI provider over the network.
    """

    def __init__(self) -> None:
        self._turns: list[NormalizedTurn] = []
        self._i = 0

    def queue_turn(self, turn: NormalizedTurn) -> None:
        self._turns.append(turn)

    async def run_turn(self, *, sink: Any = None, **_: Any) -> NormalizedTurn:
        turn = self._turns[self._i]
        self._i += 1
        if sink is not None and turn.text:
            sink.on_text_delta(turn.text)
        return turn


@pytest_asyncio.fixture
async def agent_provider() -> FakeAgentProvider:
    return FakeAgentProvider()


@pytest_asyncio.fixture
async def test_app(tmp_path: Path, agent_provider: FakeAgentProvider) -> AsyncClient:
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    container = create_test_container(data_dir, agent_provider=agent_provider)

    app = FastAPI()
    app.include_router(api_router)
    setup_dishka(container, app)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    await container.close()
