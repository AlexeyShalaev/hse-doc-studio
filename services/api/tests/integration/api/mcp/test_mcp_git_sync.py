"""git_sync через MCP локальной Студии: тот же запуск, что кнопка синхронизации, итог и конфликты в ответе.

Удалённый репозиторий голый локальный (file://), «другая Студия» обычная рабочая копия рядом (как в
tests/integration/api/git_sync/test_sync.py).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
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

from tests.fixtures.app import create_test_app, create_test_container
from tests.fixtures.git_remote import BareRemote, make_bare_remote, run_git
from tests.integration.api.vcs.conftest import TRACKED_FILE, create_project

_BASE = "http://127.0.0.1"
_PROFILE = {"name": "Анна Петрова", "email": "a.petrova@edu.hse.ru"}


@dataclass
class Stand:
    app: FastAPI
    rest: AsyncClient
    project: dict[str, Any]
    remote: BareRemote
    tmp_path: Path

    @property
    def folder(self) -> Path:
        return Path(self.project["folder"])

    def git(self, *args: str) -> str:
        return run_git(*args, git_dir=self.folder / ".hse-studio" / "git", work_tree=self.folder)


@pytest_asyncio.fixture
async def stand(tmp_path: Path) -> AsyncIterator[Stand]:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    container = create_test_container(data_dir)
    app = create_test_app(container)
    install_mcp(app, mode=StudioMode.local)
    async with AsyncClient(transport=ASGITransport(app=app), base_url=_BASE) as rest:
        assert (await rest.put("/api/v1/profile", json=_PROFILE)).status_code == 200
        project = await create_project(rest, tmp_path / "proj")
        remote = make_bare_remote(tmp_path / "remotes" / "origin.git")
        yield Stand(app, rest, project, remote, tmp_path)
    await container.close()


async def _enable(stand: Stand, *, dangerous: bool = True) -> None:
    body = {"enabled": True, "enabled_dangerous": ["git_sync"] if dangerous else []}
    resp = await stand.rest.put("/api/v1/mcp/settings", json=body)
    assert resp.status_code == 200, resp.text


def _client(stand: Stand) -> Client:
    http = httpx2.AsyncClient(transport=httpx2.ASGITransport(app=stand.app), base_url=_BASE)
    return Client(streamable_http_client(f"{_BASE}/mcp", http_client=http), mode="legacy")


async def _connect(stand: Stand) -> Path:
    """Проект опубликован и подключён; рядом рабочая копия другой Студии с той же историей."""
    stand.git("push", "--quiet", stand.remote.url, "master:refs/heads/main")
    resp = await stand.rest.put(
        f"/api/v1/projects/{stand.project['id']}/git/remote", json={"url": stand.remote.url, "credential_id": None}
    )
    assert resp.status_code == 200, resp.text
    peer = stand.tmp_path / "peer"
    run_git("clone", "--quiet", "-b", "main", stand.remote.url, str(peer))
    return peer


def _peer_commit(peer: Path, rel: str, content: str, remote: BareRemote) -> None:
    (peer / rel).parent.mkdir(parents=True, exist_ok=True)
    (peer / rel).write_text(content, encoding="utf-8", newline="\n")
    who = ["-c", "user.name=Борис", "-c", "user.email=b@edu.hse.ru"]
    run_git(*who, "add", "-A", cwd=peer)
    run_git(*who, "commit", "--quiet", "-m", "peer", cwd=peer)
    run_git(*who, "push", "--quiet", remote.url, "HEAD:refs/heads/main", cwd=peer)


async def _sync(stand: Stand, **args: object) -> tuple[bool, dict[str, Any] | str]:
    async with _client(stand) as client:
        result = await client.call_tool("git_sync", {"project_id": stand.project["id"], "wait_s": 30, **args})
    text = result.content[0].text  # type: ignore[union-attr]
    try:
        return bool(result.is_error), json.loads(text)
    except ValueError:
        return bool(result.is_error), text


async def test__list_tools__git_sync__dangerous_so_off_until_enabled_by_name(stand: Stand) -> None:
    await _enable(stand, dangerous=False)
    async with _client(stand) as client:
        hidden = {t.name for t in (await client.list_tools()).tools}
    await _enable(stand)
    async with _client(stand) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}

    assert "git_sync" not in hidden
    schema = tools["git_sync"].input_schema
    assert schema["required"] == ["project_id"]
    assert set(schema["properties"]) == {"project_id", "wait_s"}
    assert "Пример" in (tools["git_sync"].description or "")


async def test__git_sync__peer_pushed__fast_forwards_and_reports_counts(stand: Stand) -> None:
    await _enable(stand)
    peer = await _connect(stand)
    _peer_commit(peer, "notes/from-peer.txt", "hello\n", stand.remote)

    is_error, report = await _sync(stand)

    assert is_error is False, report
    assert isinstance(report, dict)
    assert (report["status"], report["outcome"]) == ("succeeded", "fast_forwarded")
    assert (report["pulled_commits"], report["pushed_commits"]) == (1, 0)
    assert (stand.folder / "notes/from-peer.txt").read_text(encoding="utf-8") == "hello\n"
    assert stand.remote.url not in json.dumps(report)


async def test__git_sync__local_edit__pushes_then_up_to_date(stand: Stand) -> None:
    await _enable(stand)
    await _connect(stand)
    with (stand.folder / TRACKED_FILE).open("a", encoding="utf-8") as f:
        f.write("\n% правка через MCP\n")

    _, first = await _sync(stand)
    _, second = await _sync(stand)

    assert isinstance(first, dict)
    assert isinstance(second, dict)
    assert first["outcome"] == "pushed"
    assert first["pushed_commits"] >= 1
    assert second["outcome"] == "up_to_date"


async def test__git_sync__both_changed_the_same_line__conflict_files_listed_and_nothing_pushed(stand: Stand) -> None:
    await _enable(stand)
    peer = await _connect(stand)
    path = stand.folder / TRACKED_FILE
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join([*lines[:-1], "% mine", ""]), encoding="utf-8", newline="\n")
    _peer_commit(peer, TRACKED_FILE, "\n".join([*lines[:-1], "% theirs", ""]), stand.remote)
    remote_head = stand.remote.head()

    is_error, report = await _sync(stand)

    assert is_error is False, report
    assert isinstance(report, dict)
    assert report["outcome"] == "conflicts"
    assert report["conflicts"] == {"files_total": 1, "files_open": 1}
    assert [f["path"] for f in report["conflict_files"]] == [TRACKED_FILE]
    assert "Разобрать" in report["hint"]
    assert stand.remote.head() == remote_head
    assert "% mine" in path.read_text(encoding="utf-8")


async def test__git_sync__no_remote__explains_instead_of_failing(stand: Stand) -> None:
    await _enable(stand)

    is_error, report = await _sync(stand)

    assert is_error is True
    assert report == "Удалённый репозиторий не подключён"


async def test__git_sync__journal_records_the_call(stand: Stand) -> None:
    await _enable(stand)
    await _connect(stand)

    await _sync(stand)

    calls = (await stand.rest.get("/api/v1/mcp/calls")).json()
    assert calls[0]["tool"] == "git_sync"
    assert calls[0]["outcome"] == "ok"
