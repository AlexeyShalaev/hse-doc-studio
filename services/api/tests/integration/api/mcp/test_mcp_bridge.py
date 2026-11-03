"""Мост stdio ↔ HTTP: тот же сервер SDK в процессе, запросы уходят в настоящее приложение Студии."""

from __future__ import annotations

import httpx2
import pytest
from hse_doc_studio.cli_mcp import Bridge, endpoint, headers_for
from mcp.client.client import Client

from tests.integration.api.mcp.test_mcp_local import _BASE, Studio, _enable, studio

__all__ = ["studio"]


def _bridge(studio: Studio) -> Bridge:
    http = httpx2.AsyncClient(transport=httpx2.ASGITransport(app=studio.app), base_url=_BASE)
    return Bridge(_BASE, {}, http=http)


async def test__bridge__forwards_tools_and_calls(studio: Studio) -> None:
    await _enable(studio)

    async with Client(_bridge(studio).server("test"), mode="legacy") as client:
        names = {t.name for t in (await client.list_tools()).tools}
        listed = await client.call_tool("list_projects", {})

    assert "read_tex" in names
    assert "Test VKR" in listed.content[0].text  # type: ignore[union-attr]


async def test__bridge__forwards_prompts(studio: Studio) -> None:
    await _enable(studio)

    async with Client(_bridge(studio).server("test"), mode="legacy") as client:
        prompts = {p.name for p in (await client.list_prompts()).prompts}

    assert "fix_build" in prompts


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://studio.example.org", "https://studio.example.org/mcp"),
        ("https://studio.example.org/", "https://studio.example.org/mcp"),
        ("http://127.0.0.1:17240/mcp", "http://127.0.0.1:17240/mcp"),
    ],
)
def test__endpoint__adds_mcp_once(url: str, expected: str) -> None:
    assert endpoint(url) == expected


def test__headers_for__token_and_language() -> None:
    assert headers_for("t", "en") == {"Authorization": "Bearer t", "X-Interface-Language": "en"}
    assert headers_for(None, "de") == {}
