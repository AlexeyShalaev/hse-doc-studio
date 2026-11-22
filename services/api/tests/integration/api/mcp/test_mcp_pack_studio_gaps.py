"""MCP: возможности интерфейса Студии шаблонов, которых не было у тулов (pack-studio-mcp.md, срез A).

Клиент SDK против локальной Студии с настоящим git-пространством (тот же стенд, что `test_mcp_pack_parity.py`):
панель «Изменения» и следующий шаг (`pack_changes`), находки линтера результата словами интерфейса, что можно
собрать (`pack_read`, блок `preview`) и варианты новой версии без записи (`pack_new_version`, `dry_run`).
"""

from __future__ import annotations

from typing import Any

from tests.integration.api.mcp.test_mcp_pack_parity import (
    _DRAFT,
    _DRAFT_DIR,
    Studio,
    _client,
    _connect,
    _json,
    _refused,
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


# ── срез B: правила проверки, номер версии, отмена сборки ─────────────────────

_CHECKS = """\
label: { ru: Демо, en: Demo }
ref: { ru: Демо, en: Demo }
rules:
  - id: demo/a
    title: { ru: Поля, en: Margins }
    default_severity: warn
    engine: structural
    params: { check: page_geometry }
"""


def _demo(view: dict[str, Any]) -> dict[str, Any]:
    return dict(next(f for f in view["files"] if f["name"] == "demo.yaml"))


async def test__checks__read_add_rule_config_and_released_refused(studio: Studio) -> None:
    async with _client(studio) as client:
        _, ws = await _connect(studio, client)
        await _json(
            client,
            "pack_write_file",
            {"workspace_id": ws, "path": f"{_DRAFT_DIR}/checks/demo.yaml", "content": _CHECKS},
        )
        read = await _json(client, "pack_checks", {"workspace_id": ws, "version": _DRAFT})
        added = await _json(
            client,
            "pack_checks",
            {
                "workspace_id": ws,
                "version": _DRAFT,
                "file": "demo.yaml",
                "if_match": _demo(read)["etag"],
                "ops": [
                    {
                        "op": "add_rule",
                        "rule": {
                            "id": "demo/b",
                            "title": {"ru": "Интервал", "en": "Spacing"},
                            "default_severity": "info",
                            "engine": "structural",
                            "params": {"check": "line_spacing", "expected": 1.5},
                        },
                    }
                ],
            },
        )
        configured = await _json(
            client,
            "pack_checks",
            {
                "workspace_id": ws,
                "version": _DRAFT,
                "config": {"disabled": ["demo/b"], "severity_override": {"demo/a": "err"}},
            },
        )
        stale = await _refused(
            client,
            "pack_checks",
            {
                "workspace_id": ws,
                "version": _DRAFT,
                "file": "demo.yaml",
                "if_match": _demo(read)["etag"],
                "ops": [{"op": "remove_rule", "index": 0}],
            },
        )
        released = await _refused(
            client, "pack_checks", {"workspace_id": ws, "version": _RELEASED, "config": {"disabled": ["x"]}}
        )
        text = await _text(client, "pack_checks", {"workspace_id": ws, "version": _DRAFT})

    assert len(read["files"]) > 1
    assert [r["id"] for r in _demo(read)["rules"]] == ["demo/a"]
    assert [r["id"] for r in _demo(added)["rules"]] == ["demo/a", "demo/b"]
    assert configured["config"]["disabled"] == ["demo/b"]
    assert configured["config"]["severity_override"] == {"demo/a": "err"}
    assert stale["code"] == "stale_file"
    assert released["code"] == "version_released"
    assert "demo/b (structural, info): Интервал" in text


async def test__version_number__renumber_by_class_and_cancel_unknown_build(studio: Studio) -> None:
    async with _client(studio) as client:
        _, ws = await _connect(studio, client)
        state = await _json(client, "pack_classify", {"workspace_id": ws, "version": _DRAFT})
        moved = await _json(
            client,
            "pack_version_number",
            {"workspace_id": ws, "version": _DRAFT, "action": "renumber", "update_class": "minor"},
        )
        missing = await _refused(
            client,
            "pack_preview_build",
            {"workspace_id": ws, "build_id": "00000000-0000-0000-0000-000000000001", "cancel": True},
        )

    assert moved["previous"] == "2026.1.9"
    assert moved["version"].endswith("/" + state["numbers"]["minor"])
    assert moved["state"]["version"] == moved["version"]
    assert missing["code"] == "preview_not_found"
