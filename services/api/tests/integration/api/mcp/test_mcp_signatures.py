"""MCP: план подписей и «Подписать комплект» (docs/design/signature-plan.md, раздел 9)."""

from __future__ import annotations

import base64
import json
import shutil
from pathlib import Path

import pytest

from tests.integration.api.mcp.test_mcp_local import Studio, _client, _enable, studio  # noqa: F401
from tests.integration.api.signatures.test_signature_plan import _make_pdf

_PROFILE = "checkpoint-1"
_PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


async def _prepare(studio: Studio) -> None:  # noqa: F811
    base = f"/api/v1/projects/{studio.project_id}"
    doc = (await studio.rest.get(f"{base}/documents/annotation")).json()
    _make_pdf(studio.folder / doc["output_file"])
    resp = await studio.rest.patch(f"{base}/signatures/slots/author/config", json={"sign_mode": "detached_text"})
    assert resp.status_code == 200, resp.text
    resp = await studio.rest.patch(
        f"{base}/signatures/placements/annotation/author",
        json={"enabled": True, "page": 1, "x_mm": 20.0, "y_mm": 40.0, "width_mm": 60.0},
    )
    assert resp.status_code == 200, resp.text
    resp = await studio.rest.post(
        f"{base}/signatures/slots/supervisor/png", files={"file": ("s.png", _PNG_1PX, "image/png")}
    )
    assert resp.status_code == 200, resp.text
    resp = await studio.rest.patch(
        f"{base}/signatures/placements/annotation/supervisor",
        json={"enabled": True, "page": 1, "x_mm": 20.0, "y_mm": 90.0, "width_mm": 60.0},
    )
    assert resp.status_code == 200, resp.text


def _text(result: object) -> str:
    return result.content[0].text  # type: ignore[attr-defined]


async def test__get_signature_plan__explains_what_is_missing(studio: Studio) -> None:  # noqa: F811
    await _enable(studio)
    await _prepare(studio)

    async with _client(studio) as client:
        result = await client.call_tool("get_signature_plan", {"project_id": studio.project_id, "profile_id": _PROFILE})

    assert result.is_error is False, result.content
    plan = json.loads(_text(result))
    slots = {s["slot_id"]: s for d in plan["docs"] for s in d["slots"]}
    assert (plan["signed"], plan["total"]) == (1, 2)
    assert (slots["author"]["status"], slots["author"]["reason"], slots["author"]["is_mine"]) == (
        "pending",
        "not_frozen",
        True,
    )
    assert slots["supervisor"]["crypto"] is False


async def test__sign_submission__dangerous__disabled_until_enabled_by_name(studio: Studio) -> None:  # noqa: F811
    await _enable(studio)

    async with _client(studio) as client:
        result = await client.call_tool("sign_submission", {"project_id": studio.project_id, "profile_id": _PROFILE})

    assert result.is_error is True
    assert result.meta is not None
    assert result.meta["code"] == "tool_disabled"


async def test__sign_submission__enabled__signs_with_default_key_and_reports_plan(studio: Studio) -> None:  # noqa: F811
    await _enable(studio, enabled_dangerous=["sign_submission"])
    await _prepare(studio)
    resp = await studio.rest.post(
        "/api/v1/signing-identities/self-signed", json={"label": "Ivan", "subject_cn": "Ivan Ivanov"}
    )
    assert resp.status_code == 201, resp.text

    async with _client(studio) as client:
        result = await client.call_tool("sign_submission", {"project_id": studio.project_id, "profile_id": _PROFILE})

    assert result.is_error is False, result.content
    body = json.loads(_text(result))
    assert body["frozen_docs"] == ["annotation"]
    assert [r["ok"] for r in body["results"]] == [True]
    assert (body["plan"]["signed"], body["plan"]["total"]) == (2, 2)
    assert "BEGIN" not in _text(result)


@pytest.mark.skipif(shutil.which("gpg") is None, reason="gpg is not installed")
async def test__sign_submission__passphrase_key__refuses_and_asks_for_the_interface(
    studio: Studio,  # noqa: F811
) -> None:
    await _enable(studio, enabled_dangerous=["sign_submission"])
    await _prepare(studio)
    resp = await studio.rest.post(
        "/api/v1/signing-identities/openpgp/generate",
        json={"name": "Иван Иванов", "email": "ivan@example.org", "passphrase": "secret words"},
    )
    assert resp.status_code == 201, resp.text

    async with _client(studio) as client:
        result = await client.call_tool("sign_submission", {"project_id": studio.project_id, "profile_id": _PROFILE})

    assert result.is_error is True
    assert "паролем" in _text(result) or "passphrase" in _text(result)
    state = json.loads((Path(studio.folder) / ".hse-studio" / "signatures.json").read_text(encoding="utf-8"))
    assert state.get("frozen", {}) == {}
