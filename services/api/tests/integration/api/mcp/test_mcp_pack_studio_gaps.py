"""MCP: возможности интерфейса Студии шаблонов, которых не было у тулов (pack-studio-mcp.md, срез A).

Клиент SDK против локальной Студии с настоящим git-пространством (тот же стенд, что `test_mcp_pack_parity.py`):
панель «Изменения» и следующий шаг (`pack_changes`), находки линтера результата словами интерфейса, что можно
собрать (`pack_read`, блок `preview`) и варианты новой версии без записи (`pack_new_version`, `dry_run`).
"""

from __future__ import annotations

from tests.integration.api.mcp.test_mcp_pack_parity import (
    _DRAFT,
    _DRAFT_DIR,
    Studio,
    _client,
    _connect,
    _json,
    _text,
    studio,
)
from tests.integration.api.pack_studio.outcome_support import DRAFT_MANIFEST

__all__ = ["studio"]

_RELEASED = "hse-cs-se/vkr/2026.1.2"


async def test__changes__draft_edit_then_released_points_to_the_draft(studio: Studio) -> None:
    async with _client(studio) as client:
        _, ws = await _connect(studio, client)
        clean = await _json(client, "pack_changes", {"workspace_id": ws, "version": _DRAFT})
        await _json(
            client,
            "pack_patch_yaml",
            {
                "workspace_id": ws,
                "path": DRAFT_MANIFEST,
                "ops": [{"op": "set", "pointer": "/summary/en", "value": "X"}],
            },
        )
        edited = await _json(client, "pack_changes", {"workspace_id": ws, "version": _DRAFT})
        guessed = await _json(client, "pack_changes", {"workspace_id": ws})
        released = await _json(client, "pack_changes", {"workspace_id": ws, "version": _RELEASED})
        text = await _text(client, "pack_changes", {"workspace_id": ws})

    assert clean["connection"] == "ready"
    assert clean["changed_files"] == 0
    assert clean["next_step"] is None
    assert edited["changed_in_version"] == 1
    assert edited["files"] == [f"M {DRAFT_MANIFEST}"]
    assert edited["checked"] == [_DRAFT_DIR]
    assert edited["next_step"]["kind"] in {"submit", "describe", "fixErrors"}
    assert edited["next_step"]["tools"]
    assert guessed["version"] == _DRAFT_DIR
    assert released["released"] is True
    assert released["changed_elsewhere"] == _DRAFT_DIR
    assert released["next_step"]["kind"] == "toDraft"
    assert released["next_step"]["label"] == "К моему черновику 2026.1.9"
    assert "Следующий шаг:" in text


async def test__outcome_lint__plain_words_by_default_tech_on_request(studio: Studio) -> None:
    async with _client(studio) as client:
        _, ws = await _connect(studio, client)
        plain = await _text(client, "pack_outcome_lint", {"workspace_id": ws, "version": _DRAFT, "severity": "info"})
        tech = await _text(client, "pack_outcome_lint", {"workspace_id": ws, "version": _DRAFT, "wording": "tech"})
        data = await _json(client, "pack_outcome_lint", {"workspace_id": ws, "version": _DRAFT})

    assert plain.startswith("Проверка шаблона. Ошибок:")
    assert "Правил проверено готовыми случаями:" in plain
    assert "{{" not in plain
    assert tech.startswith("Линтер результата")
    assert all("plain" in f and f["plain"]["title"] for f in data["findings"])


async def test__read_preview_block_and_new_version_dry_run(studio: Studio) -> None:
    async with _client(studio) as client:
        _, ws = await _connect(studio, client)
        model = await _json(client, "pack_read", {"workspace_id": ws, "version": _DRAFT})
        options = await _json(
            client, "pack_new_version", {"workspace_id": ws, "pack": "hse-cs-se", "template": "vkr", "dry_run": True}
        )
        tree = await _json(client, "pack_read", {"workspace_id": ws})

    preview = model["preview"]
    assert preview["documents"]
    assert preview["default_example"]
    assert {s["id"] for s in preview["switches"]} >= {"lang"}
    assert set(options["numbers"]) == {"patch", "minor", "major"}
    assert options["default_base"]
    versions = [v["version"] for p in tree["packs"] for t in p["templates"] if t["id"] == "vkr" for v in t["versions"]]
    assert options["numbers"]["patch"] not in versions
