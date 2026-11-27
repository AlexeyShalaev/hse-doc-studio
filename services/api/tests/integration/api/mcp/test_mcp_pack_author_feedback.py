"""MCP Студии паков: шероховатости, найденные автором пака при работе только через тулы.

Раздел про строку каждого автора в `pack_help`, номер версии в обоих видах у сценариев, `if_match` без кавычек и
фильтр `pack_submission` по профилю. Стенд как у `test_mcp_pack_parity.py`.
"""

from __future__ import annotations

import pytest
from hse_doc_studio.core.file_version import file_etag

from tests.integration.api.mcp.test_mcp_pack_parity import (
    _DRAFT,
    _DRAFT_DIR,
    _TEMPLATE,
    DRAFT,
    Studio,
    _client,
    _connect,
    _json,
    _refused,
    _text,
    studio,
)

__all__ = ["studio"]


async def test__help__topic_team__explains_the_line_of_every_author(studio: Studio) -> None:
    async with _client(studio) as client:
        _, ws = await _connect(studio, client)
        team = await _text(client, "pack_help", {"topic": "team"})
        team_json = await _json(client, "pack_help", {"topic": "team"})
        everything = await _text(client, "pack_help", {})
        hints = await _text(client, "pack_hints", {"workspace_id": ws, "path": f"{_DRAFT_DIR}/files/common/x.tex"})

    assert "Командный проект: строка каждого автора" in team
    assert "\\hseSignAnchor[7cm]{author__{{ a.slug }}}" in team
    assert "anchor: author" in team
    assert "pack_signature_check" in team
    assert team_json["team"]
    assert "groups" not in team_json
    assert "topic: team" in everything
    assert "pack_help (topic: team)" in hints


@pytest.mark.parametrize("version", [DRAFT, _DRAFT, f"{_DRAFT_DIR}/version.yaml"], ids=["number", "full", "path"])
async def test__scenarios__version_as_number_or_full_name(studio: Studio, version: str) -> None:
    async with _client(studio) as client:
        _, ws = await _connect(studio, client)
        base = {"workspace_id": ws, "template": _TEMPLATE}
        created = await _json(
            client,
            "pack_scenario_write",
            {
                **base,
                "id": "pinned",
                "name": "Привязан к черновику",
                "versions": [DRAFT],
                "record_snapshot": "work_tree",
                "version": version,
            },
        )
        run = await _json(client, "pack_scenario_run", {**base, "version": version})

    assert created["scenario"]["snapshot"] is not None
    assert (run["version"], run["passed"], run["unchecked"]) == (DRAFT, 1, 0)


async def test__scenarios__version_of_another_template__refused_with_the_reason(studio: Studio) -> None:
    async with _client(studio) as client:
        _, ws = await _connect(studio, client)
        base = {"workspace_id": ws, "template": _TEMPLATE}
        text = await _text(client, "pack_scenario_run", {**base, "version": f"hse-cs-se/coursework/{DRAFT}"}, ok=False)

    assert "hse-cs-se/vkr" in text
    assert "hse-cs-se/coursework" in text


async def test__if_match__etag_without_quotes_works_and_still_protects(studio: Studio) -> None:
    tex = f"{_DRAFT_DIR}/files/report/etag.tex"
    moved = f"{_DRAFT_DIR}/files/report/etag-moved.tex"
    async with _client(studio) as client:
        _, ws = await _connect(studio, client)
        base = {"workspace_id": ws, "path": tex}
        first = await _json(client, "pack_write_file", {**base, "content": "один\n"})
        bare = first["etag"].strip('"')
        second = await _json(client, "pack_write_file", {**base, "content": "два\n", "if_match": bare})
        stale = await _refused(client, "pack_write_file", {**base, "content": "три\n", "if_match": bare})
        quoted = await _json(client, "pack_write_file", {**base, "content": "три\n", "if_match": second["etag"]})
        current = quoted["etag"].strip('"')
        stale_move = await _refused(
            client, "pack_move_file", {"workspace_id": ws, "src": tex, "dst": moved, "if_match": bare}
        )
        done_move = await _json(
            client, "pack_move_file", {"workspace_id": ws, "src": tex, "dst": moved, "if_match": current}
        )
        drop = {"workspace_id": ws, "path": moved, "confirm": True}
        stale_delete = await _refused(client, "pack_delete_file", {**drop, "if_match": bare})
        deleted = await _json(client, "pack_delete_file", {**drop, "if_match": current})
        manifest = await _json(client, "pack_read_file", {"workspace_id": ws, "path": f"{_DRAFT_DIR}/version.yaml"})
        submission = await _json(client, "pack_submission", {"workspace_id": ws, "version": _DRAFT})
        patched = await _json(
            client,
            "pack_patch_yaml",
            {
                "workspace_id": ws,
                "path": f"{_DRAFT_DIR}/version.yaml",
                "if_match": manifest["etag"].strip('"'),
                "ops": [{"op": "set", "pointer": "/langs", "value": ["ru", "en"]}],
            },
        )
        renamed = await _json(
            client,
            "pack_submission_edit",
            {
                "workspace_id": ws,
                "version": _DRAFT,
                "if_match": (await _json(client, "pack_submission", {"workspace_id": ws, "version": _DRAFT}))[
                    "etag"
                ].strip('"'),
                "ops": [{"op": "remove_profile", "profile": 0}],
            },
        )
        stale_submission = await _refused(
            client,
            "pack_submission_edit",
            {
                "workspace_id": ws,
                "version": _DRAFT,
                "if_match": submission["etag"].strip('"'),
                "ops": [{"op": "remove_profile", "profile": 0}],
            },
        )
        scenario = {"workspace_id": ws, "template": _TEMPLATE, "id": "etag-one"}
        created = await _json(client, "pack_scenario_write", {**scenario, "name": "Сценарий"})
        edited = await _json(
            client, "pack_scenario_write", {**scenario, "name": "Другое", "if_match": created["etag"].strip('"')}
        )
        stale_scenario = await _refused(
            client, "pack_scenario_delete", {**scenario, "if_match": created["etag"].strip('"')}
        )
        removed = await _json(client, "pack_scenario_delete", {**scenario, "if_match": edited["etag"].strip('"')})

    assert second["etag"] == file_etag("два\n".encode())
    assert stale["code"] == "stale_file"
    assert stale_move["code"] == "stale_file"
    assert done_move
    assert stale_delete["code"] == "stale_file"
    assert deleted
    assert renamed["etag"] != submission["etag"]
    assert stale_submission["code"] == "stale_file"
    assert patched["etag"]
    assert stale_scenario["code"] == "stale_file"
    assert removed["deleted"] is True


async def test__submission__one_profile_in_data_and_text(studio: Studio) -> None:
    async with _client(studio) as client:
        _, ws = await _connect(studio, client)
        base = {"workspace_id": ws, "version": _DRAFT, "routes": True}
        full = await _json(client, "pack_submission", base)
        ids = [p["id"] for p in full["submission"]["profiles"]]
        one = await _json(client, "pack_submission", {**base, "profile": ids[1]})
        one_text = await _text(client, "pack_submission", {**base, "profile": ids[1]})
        full_text = await _text(client, "pack_submission", base)
        unknown = await _text(client, "pack_submission", {**base, "profile": "no-such"}, ok=False)

    assert len(ids) > 1
    assert [p["id"] for p in one["submission"]["profiles"]] == [ids[1]]
    assert [p["id"] for p in one["routes"]["profiles"]] == [ids[1]]
    assert f": {ids[1]}" in one_text
    assert f": {ids[0]}" not in one_text
    assert f"  {ids[0]}: " not in one_text
    assert len(one_text) < len(full_text)
    assert "no-such" in unknown
    assert ids[0] in unknown
