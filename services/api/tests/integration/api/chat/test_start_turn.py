from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from hse_doc_studio.core.agent.entities import NormalizedTurn, TokenUsage
from hse_doc_studio.core.enums import StopReason
from httpx import AsyncClient

from tests.integration.api.chat.conftest import FakeAgentProvider, create_project


async def _create_provider(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/ai-providers",
        json={"name": "Test provider", "type": "openai", "api_key": "sk-test", "models": ["gpt-4.1"]},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _create_session(client: AsyncClient, project_id: str) -> str:
    resp = await client.post(f"/api/v1/projects/{project_id}/chats", json={"title": "t"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _wait_until_run_finished(client: AsyncClient, project_id: str, session_id: str) -> dict:
    # start_turn schedules the agent loop as a background asyncio task and
    # returns 202 immediately — poll the session detail until it's no longer
    # marked as having an active run.
    for _ in range(50):
        detail = (await client.get(f"/api/v1/projects/{project_id}/chats/{session_id}")).json()
        if detail["active_run_id"] is None:
            return detail
        await asyncio.sleep(0.05)
    pytest.fail("turn did not finish within the poll window")


async def test__start_turn__simple_text_reply__persists_user_and_assistant_messages(
    test_app: AsyncClient, agent_provider: FakeAgentProvider, tmp_path: Path
) -> None:
    project_id = await create_project(test_app, tmp_path / "proj")
    provider_id = await _create_provider(test_app)
    session_id = await _create_session(test_app, project_id)
    agent_provider.queue_turn(
        NormalizedTurn(
            text="Привет! Чем могу помочь?", tool_calls=(), stop_reason=StopReason.end_turn, usage=TokenUsage()
        )
    )

    start_resp = await test_app.post(
        f"/api/v1/projects/{project_id}/chats/{session_id}/turns",
        json={"text": "Привет", "provider_id": provider_id, "model": "gpt-4.1"},
    )
    assert start_resp.status_code == 202, start_resp.text
    detail = await _wait_until_run_finished(test_app, project_id, session_id)

    roles = [m["role"] for m in detail["messages"]]
    assert roles == ["user", "assistant"]
    assert detail["messages"][0]["blocks"][0]["text"] == "Привет"
    assert detail["messages"][1]["blocks"][0]["text"] == "Привет! Чем могу помочь?"


async def test__start_turn__unknown_session__404(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id = await create_project(test_app, tmp_path / "proj")
    provider_id = await _create_provider(test_app)
    fake_session_id = "00000000-0000-0000-0000-000000000000"

    resp = await test_app.post(
        f"/api/v1/projects/{project_id}/chats/{fake_session_id}/turns",
        json={"text": "hi", "provider_id": provider_id, "model": "gpt-4.1"},
    )

    assert resp.status_code == 404
