"""Сроки контрольных точек в локальной Студии (docs/design/signing-route.md, раздел 16): REST и MCP.

`PUT .../submissions/profiles/{profile_id}/deadline` ставит и снимает срок, профили сдачи отдают срок, состояние и
подсказку, список проектов ближайший срок; MCP читает срок в `list_submission_profiles` и `get_project` и пишет его
`set_checkpoint_deadline`.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx2
import pytest_asyncio
from fastapi import FastAPI
from hse_doc_studio.api.mcp_server import install_mcp
from hse_doc_studio.core.mode import StudioMode
from httpx import ASGITransport, AsyncClient
from mcp.client.client import Client
from mcp.client.streamable_http import streamable_http_client

from tests.factories import project_api_payload
from tests.fixtures.app import create_test_app, create_test_container

_BASE = "http://127.0.0.1"
MSK = timezone(timedelta(hours=3))
TOPIC = "topic-approval"


@dataclass
class Studio:
    app: FastAPI
    rest: AsyncClient
    project_id: str
    folder: Path

    @property
    def profiles(self) -> str:
        return f"/api/v1/projects/{self.project_id}/submissions/profiles"

    def deadline(self, profile_id: str = TOPIC) -> str:
        return f"{self.profiles}/{profile_id}/deadline"


@pytest_asyncio.fixture
async def studio(tmp_path: Path) -> AsyncIterator[Studio]:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    container = create_test_container(data_dir)
    app = create_test_app(container)
    install_mcp(app, mode=StudioMode.local)
    folder = tmp_path / "kp"
    payload = {
        **project_api_payload(str(folder)),
        "name": "Курсовая",
        "pack_id": "hse-cs-sse",
        "template_id": "coursework",
        "version": "2026.1.3",
        "kind": "project",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url=_BASE) as rest:
        created = await rest.post("/api/v1/projects", json=payload)
        assert created.status_code == 201, created.text
        yield Studio(app=app, rest=rest, project_id=created.json()["id"], folder=folder)
    await container.close()


def _in_days(days: int) -> datetime:
    day = datetime.now(MSK).date() + timedelta(days=days)
    return datetime(day.year, day.month, day.day, 23, 59, tzinfo=MSK)


def _profile(profiles: list[dict[str, Any]], profile_id: str = TOPIC) -> dict[str, Any]:
    return next(p for p in profiles if p["id"] == profile_id)


async def test__deadline__set_shown_on_the_checkpoint_and_in_the_list_then_cleared(studio: Studio) -> None:
    deadline = _in_days(2)
    before = (await studio.rest.get(studio.profiles)).json()

    put = await studio.rest.put(studio.deadline(), json={"deadline": deadline.isoformat()})
    profiles = (await studio.rest.get(studio.profiles)).json()
    listed = (await studio.rest.get("/api/v1/projects")).json()
    project_json = json.loads((studio.folder / ".hse-studio" / "project.json").read_text(encoding="utf-8"))

    # До срока точка «не указан», подсказки у пака 2026.1.3 ещё нет (придёт в 2026.1.4).
    topic_before = _profile(before)
    assert (topic_before["deadline"], topic_before["deadline_state"], topic_before["packaged_at"]) == (
        None,
        "none",
        None,
    )
    assert topic_before["deadline_hint"] is None
    assert put.status_code == 200, put.text
    assert put.json() == {
        "profile_id": TOPIC,
        "deadline": deadline.isoformat(),
        "state": "soon",
        "packaged_at": None,
    }
    assert (_profile(profiles)["deadline"], _profile(profiles)["deadline_state"]) == (deadline.isoformat(), "soon")
    assert _profile(profiles, "final")["deadline_state"] == "none"
    assert project_json["deadlines"] == {TOPIC: deadline.isoformat()}
    item = next(p for p in listed if p["id"] == studio.project_id)
    assert item["next_deadline"] == {
        "profile_id": TOPIC,
        "name": _profile(profiles)["name"],
        "deadline": deadline.isoformat(),
        "state": "soon",
    }

    cleared = await studio.rest.put(studio.deadline(), json={"deadline": None})
    listed = (await studio.rest.get("/api/v1/projects")).json()

    assert cleared.json() == {"profile_id": TOPIC, "deadline": None, "state": "none", "packaged_at": None}
    assert next(p for p in listed if p["id"] == studio.project_id)["next_deadline"] is None


async def test__deadline__bad_value_unknown_checkpoint_and_missing_field(studio: Studio) -> None:
    naive = await studio.rest.put(studio.deadline(), json={"deadline": "2026-11-15T23:59:00"})
    old = await studio.rest.put(studio.deadline(), json={"deadline": "1999-11-15T23:59:00+03:00"})
    unknown = await studio.rest.put(studio.deadline("defence"), json={"deadline": _in_days(2).isoformat()})
    missing = await studio.rest.put(studio.deadline(), json={})
    past = await studio.rest.put(studio.deadline(), json={"deadline": "2025-11-15T23:59:00+03:00"})

    assert (naive.status_code, naive.json()["code"]) == (400, "bad_deadline")
    assert (old.status_code, old.json()["code"]) == (400, "bad_deadline")
    assert unknown.status_code == 404
    assert missing.status_code == 422
    # Срок задним числом можно: пакета к нему нет, значит «просрочено».
    assert (past.status_code, past.json()["state"]) == (200, "overdue")


def _client(studio: Studio) -> Client:
    http = httpx2.AsyncClient(transport=httpx2.ASGITransport(app=studio.app), base_url=_BASE)
    return Client(streamable_http_client(f"{_BASE}/mcp", http_client=http), mode="legacy")


def _json(result: Any) -> Any:
    assert result.is_error is False, result.content
    return json.loads(result.content[0].text)


async def test__mcp__set_checkpoint_deadline_and_read_it_back(studio: Studio) -> None:
    resp = await studio.rest.put("/api/v1/mcp/settings", json={"enabled": True})
    assert resp.status_code == 200, resp.text
    deadline = _in_days(10)

    async with _client(studio) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
        written = _json(
            await client.call_tool(
                "set_checkpoint_deadline",
                {"project_id": studio.project_id, "profile_id": TOPIC, "deadline": deadline.isoformat()},
            )
        )
        bad = await client.call_tool(
            "set_checkpoint_deadline", {"project_id": studio.project_id, "profile_id": TOPIC, "deadline": "завтра"}
        )
        profiles = _json(await client.call_tool("list_submission_profiles", {"project_id": studio.project_id}))
        project = _json(await client.call_tool("get_project", {"project_id": studio.project_id}))
        cleared = _json(
            await client.call_tool(
                "set_checkpoint_deadline", {"project_id": studio.project_id, "profile_id": TOPIC, "deadline": None}
            )
        )

    assert tools["set_checkpoint_deadline"].input_schema["required"] == ["project_id", "profile_id", "deadline"]
    assert written == {"profile_id": TOPIC, "deadline": deadline.isoformat(), "state": "upcoming", "packaged_at": None}
    assert bad.is_error is True
    topic = _profile(profiles)
    assert (topic["deadline"], topic["deadline_state"], topic["packaged_at"], topic["deadline_hint"]) == (
        deadline.isoformat(),
        "upcoming",
        None,
        None,
    )
    assert project["deadlines"] == {TOPIC: deadline.isoformat()}
    assert cleared["state"] == "none"
