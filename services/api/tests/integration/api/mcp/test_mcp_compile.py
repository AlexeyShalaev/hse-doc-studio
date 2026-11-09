"""compile_document через MCP локальной Студии: `wait=false` и долгая сборка отвечают compile_id, а не ошибкой."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import httpx2
import pytest
import pytest_asyncio
from fastapi import FastAPI
from hse_doc_studio.api.mcp_server import install_mcp
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.infra.compile.docker_compile_executor import DockerCompileExecutor
from hse_doc_studio.infra.compile.docker_image_manager import DockerImageManager, DockerStatus, ImageInfo
from httpx import ASGITransport, AsyncClient
from mcp.client.client import Client
from mcp.client.streamable_http import streamable_http_client
from pytest_mock import MockerFixture

from tests.factories import project_api_payload
from tests.fixtures.app import create_test_app, create_test_container

_BASE = "http://127.0.0.1"
# Сколько «идёт» подменённая сборка: дольше ожидания тула в тесте, но тест её не ждёт до конца.
_BUILD_S = 1.5


@dataclass
class Studio:
    app: FastAPI
    project_id: str
    doc_id: str


@pytest_asyncio.fixture
async def studio(tmp_path: Path, mocker: MockerFixture) -> AsyncIterator[Studio]:
    # Докер и образ подменены на швах, как в tests/integration/api/compile/test_trigger_compile.py.
    mocker.patch.object(
        DockerImageManager, "docker_status", return_value=DockerStatus(available=True, version="fake", detail=None)
    )
    mocker.patch.object(
        DockerImageManager,
        "inspect",
        return_value=ImageInfo(image="texlive/texlive:latest", id="sha256:fake", size_bytes=1, created="2026-01-01"),
    )

    def _slow_logs(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
        async def logs() -> AsyncIterator[str]:
            await asyncio.sleep(_BUILD_S)
            yield "compile stubbed: no docker in tests"

        return logs()

    mocker.patch.object(DockerCompileExecutor, "run", side_effect=_slow_logs)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    container = create_test_container(data_dir)
    app = create_test_app(container)
    install_mcp(app, mode=StudioMode.local)
    folder = tmp_path / "vkr"
    folder.mkdir()
    async with AsyncClient(transport=ASGITransport(app=app), base_url=_BASE) as rest:
        created = await rest.post("/api/v1/projects", json=project_api_payload(str(folder)))
        assert created.status_code == 201, created.text
        project_id = created.json()["id"]
        doc_id = (await rest.get(f"/api/v1/projects/{project_id}/documents")).json()[0]["id"]
        resp = await rest.put("/api/v1/mcp/settings", json={"enabled": True})
        assert resp.status_code == 200, resp.text
        yield Studio(app=app, project_id=project_id, doc_id=doc_id)
        # Подменённая сборка доигрывает до закрытия контейнера.
        await asyncio.sleep(_BUILD_S)
    await container.close()


def _client(studio: Studio) -> Client:
    http = httpx2.AsyncClient(transport=httpx2.ASGITransport(app=studio.app), base_url=_BASE)
    return Client(streamable_http_client(f"{_BASE}/mcp", http_client=http), mode="legacy")


def _compile_id(text: str) -> str:
    match = re.search(r"compile_id: ([0-9a-f-]{36})", text)
    assert match is not None, text
    return match.group(1)


async def test__list_tools__compile_document__has_wait_flag(studio: Studio) -> None:
    async with _client(studio) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}

    schema = tools["compile_document"].input_schema
    assert schema["required"] == ["project_id", "doc_id"]
    assert schema["properties"]["wait"]["type"] == "boolean"
    assert schema["properties"]["wait"]["default"] is True


async def test__compile_document__wait_false__answers_at_once_and_get_compile_finds_the_build(
    studio: Studio,
) -> None:
    async with _client(studio) as client:
        async with asyncio.timeout(_BUILD_S):
            started = await client.call_tool(
                "compile_document", {"project_id": studio.project_id, "doc_id": studio.doc_id, "wait": False}
            )
        text = started.content[0].text  # type: ignore[union-attr]
        found = await client.call_tool(
            "get_compile", {"project_id": studio.project_id, "compile_id": _compile_id(text)}
        )

    assert started.is_error is False, text
    assert "status: in_progress" in text
    assert found.is_error is False, found.content
    record = json.loads(found.content[0].text)  # type: ignore[union-attr]
    assert record["id"] == _compile_id(text)
    assert record["status"] in {"pending", "running"}


async def test__compile_document__build_outlives_the_wait__in_progress_not_timeout_error(
    studio: Studio, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("hse_doc_studio.use_cases.mcp.tools.compile_document.COMPILE_WAIT_S", 0.2)

    async with _client(studio) as client:
        result = await client.call_tool("compile_document", {"project_id": studio.project_id, "doc_id": studio.doc_id})

    text = result.content[0].text  # type: ignore[union-attr]
    assert result.is_error is False, text
    assert text.startswith("Сборка")
    assert "ещё идёт" in text
    _compile_id(text)
