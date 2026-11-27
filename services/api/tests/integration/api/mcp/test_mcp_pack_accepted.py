"""MCP: версия слитого запроса до обновления пространства не черновик, а «принята, обновите пространство».

Клиент SDK из `test_mcp_pack_parity.py` над маленьким паком `pack_studio/test_git_workspace.py` (git по file://); номер
запроса и его состояние подменены, как в `pack_studio/test_git_accepted.py`.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from hse_doc_studio.core.pack_studio.git_flow import PullRequestState
from mcp.client.client import Client

from tests.integration.api.mcp.test_mcp_pack_parity import Studio, _client, _json, _text, studio
from tests.integration.api.pack_studio.conftest import DRAFT, DRAFT_DIR
from tests.integration.api.pack_studio.test_git_accepted import fake_pull_requests
from tests.integration.api.pack_studio.test_git_workspace import _remote

__all__ = ["studio"]

_LABEL = "принята, обновите пространство"
_DRAFT = f"demo/report/{DRAFT}"
_MANIFEST = f"{DRAFT_DIR}/version.yaml"


async def _connect(studio: Studio, client: Client) -> str:
    created = await _json(client, "pack_workspace_create", {"url": _remote(studio.stand.root).url})
    for _ in range(600):
        cards = (await _json(client, "pack_list_workspaces", {}))["workspaces"]
        card = next(w for w in cards if w["id"] == created["id"])
        if not card["busy"]:
            break
        await asyncio.sleep(0.05)
    assert card["state"] == "ready", card
    return str(created["id"])


async def _merged_release(client: Client, ws: str) -> None:
    """Черновик выпущен и отправлен запросом №531."""
    await _json(
        client,
        "pack_version_notes",
        {"workspace_id": ws, "version": _DRAFT, "changes": {"ru": ["Правка титула."], "en": ["Title page fix."]}},
    )
    await _json(client, "pack_release", {"workspace_id": ws, "version": _DRAFT, "confirm": True})
    await _json(client, "pack_propose", {"workspace_id": ws, "confirm": True})


async def _shown(client: Client, ws: str) -> dict[str, Any]:
    """Как версию показывают все тулы, у которых есть её состояние."""
    args = {"workspace_id": ws, "version": _DRAFT}
    tree = await _json(client, "pack_read", {"workspace_id": ws})
    versions = [v for p in tree["packs"] for t in p["templates"] for v in t["versions"]]
    return {
        "changes": (await _json(client, "pack_changes", args))["accepted"],
        "changes_text": _LABEL in await _text(client, "pack_changes", args),
        "tree_text": f"{DRAFT} {_LABEL}" in await _text(client, "pack_tree", {"workspace_id": ws}),
        "read_tree": next(v for v in versions if v["version"] == DRAFT).get("accepted", False),
        "read_version": (await _json(client, "pack_read", args))["accepted"],
        "classify": (await _json(client, "pack_classify", args))["accepted"],
    }


@pytest.mark.parametrize(
    ("state", "accepted"), [(PullRequestState.merged, True), (PullRequestState.closed, False)], ids=["merged", "closed"]
)
async def test__merged_or_closed_request__every_tool_agrees(
    studio: Studio, monkeypatch: pytest.MonkeyPatch, state: PullRequestState, accepted: bool
) -> None:
    hosting = fake_pull_requests(monkeypatch)
    async with _client(studio) as client:
        ws = await _connect(studio, client)
        await _merged_release(client, ws)
        hosting.state = state
        hosting.head_sha = (await _json(client, "pack_git_status", {"workspace_id": ws}))["head_sha"]
        shown = await _shown(client, ws)

    assert shown == dict.fromkeys(shown, accepted)


async def test__edit_after_merge__no_longer_accepted_and_start_over_stays(
    studio: Studio, monkeypatch: pytest.MonkeyPatch
) -> None:
    hosting = fake_pull_requests(monkeypatch)
    async with _client(studio) as client:
        ws = await _connect(studio, client)
        await _merged_release(client, ws)
        hosting.head_sha = (await _json(client, "pack_git_status", {"workspace_id": ws}))["head_sha"]
        before = await _json(client, "pack_changes", {"workspace_id": ws, "version": _DRAFT})
        await _json(
            client,
            "pack_patch_yaml",
            {
                "workspace_id": ws,
                "path": _MANIFEST,
                "ops": [{"op": "set", "pointer": "/summary/en", "value": "After merge"}],
            },
        )
        shown = await _shown(client, ws)
        after = await _json(client, "pack_changes", {"workspace_id": ws, "version": _DRAFT})
        tree = await _text(client, "pack_tree", {"workspace_id": ws})

    assert before["accepted"] is True
    assert before["accepted_label"] == _LABEL
    assert shown == dict.fromkeys(shown, False)
    assert f"{DRAFT} draft" in tree
    assert before["next_step"]["kind"] == after["next_step"]["kind"] == "startNew"
    assert after["version"] == DRAFT_DIR
