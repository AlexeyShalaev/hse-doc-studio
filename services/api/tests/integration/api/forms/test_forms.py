from __future__ import annotations

from pathlib import Path

from httpx import AsyncClient

from tests.factories import project_api_payload

_AI = "ai_declaration"


async def _create_project(client: AsyncClient, folder: Path) -> dict:
    folder.mkdir(exist_ok=True)
    resp = await client.post("/api/v1/projects", json=project_api_payload(str(folder)))
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test__api__list_forms__includes_ai_declaration(test_app: AsyncClient, tmp_path: Path) -> None:
    project = await _create_project(test_app, tmp_path / "proj")

    resp = await test_app.get(f"/api/v1/projects/{project['id']}/forms")

    assert resp.status_code == 200, resp.text
    forms = resp.json()["forms"]
    ai = next(f for f in forms if f["id"] == _AI)
    assert ai["icon"] == "bot"  # pack-declared per-form icon
    assert ai["required_for_pack"] is True
    # Fresh project: nothing filled in yet.
    assert ai["complete"] is False


async def test__api__get_form__returns_schema_and_empty_answers(test_app: AsyncClient, tmp_path: Path) -> None:
    project = await _create_project(test_app, tmp_path / "proj")

    resp = await test_app.get(f"/api/v1/projects/{project['id']}/forms/{_AI}")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["id"] == _AI
    assert data["answers"] == {}
    section_ids = [s["id"] for s in data["sections"]]
    assert section_ids == ["usage", "confirmation"]
    field_ids = [f["id"] for s in data["sections"] for f in s["fields"]]
    assert "used_ai" in field_ids
    assert "usage_table" in field_ids
    # used_ai (required) is unfilled → incomplete with an error keyed to it.
    assert data["complete"] is False
    assert any(e["field_id"] == "used_ai" for e in data["errors"])


async def test__api__get_form__unknown_form__returns_404(test_app: AsyncClient, tmp_path: Path) -> None:
    project = await _create_project(test_app, tmp_path / "proj")

    resp = await test_app.get(f"/api/v1/projects/{project['id']}/forms/does_not_exist")

    assert resp.status_code == 404


async def test__api__get_form__nonexistent_project__returns_404(test_app: AsyncClient) -> None:
    fake = "00000000-0000-0000-0000-000000000000"

    resp = await test_app.get(f"/api/v1/projects/{fake}/forms/{_AI}")

    assert resp.status_code == 404


async def test__api__update_form__did_not_use_ai__is_complete(test_app: AsyncClient, tmp_path: Path) -> None:
    project = await _create_project(test_app, tmp_path / "proj")
    body = {"completed": True, "answers": {"used_ai": "no", "consent": True}}

    resp = await test_app.put(f"/api/v1/projects/{project['id']}/forms/{_AI}", json=body)

    assert resp.status_code == 200, resp.text
    data = resp.json()
    # Hidden branch (tools/table/pct/details) must not be required.
    assert data["complete"] is True
    assert data["errors"] == []
    assert data["completed"] is True


async def test__api__update_form__used_ai_invalid__reports_errors(test_app: AsyncClient, tmp_path: Path) -> None:
    project = await _create_project(test_app, tmp_path / "proj")
    body = {"answers": {"used_ai": "yes", "details": "too short", "pct": 250}}

    resp = await test_app.put(f"/api/v1/projects/{project['id']}/forms/{_AI}", json=body)

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["complete"] is False
    error_fields = {e["field_id"] for e in data["errors"]}
    assert "details" in error_fields  # min_length unmet
    assert "pct" in error_fields  # above max
    assert "consent" in error_fields  # required, unchecked


async def test__api__update_form__answers_persisted_and_reflected(test_app: AsyncClient, tmp_path: Path) -> None:
    project = await _create_project(test_app, tmp_path / "proj")
    answers = {
        "used_ai": "yes",
        "tools": ["chatgpt", "claude"],
        "usage_table": [{"tool": "ChatGPT", "version": "GPT-4o", "kind": "редактура", "scope": "глава 2"}],
        "pct": 20,
        "details": "ИИ использовался для редактуры формулировок и поиска источников по теме." * 2,
        "consent": True,
    }

    put = await test_app.put(
        f"/api/v1/projects/{project['id']}/forms/{_AI}", json={"completed": True, "answers": answers}
    )
    assert put.status_code == 200, put.text
    assert put.json()["complete"] is True

    get = await test_app.get(f"/api/v1/projects/{project['id']}/forms/{_AI}")
    assert get.status_code == 200
    data = get.json()
    assert data["answers"]["tools"] == ["chatgpt", "claude"]
    assert data["answers"]["usage_table"][0]["tool"] == "ChatGPT"
    assert data["completed"] is True


async def test__api__update_form__is_patch_style(test_app: AsyncClient, tmp_path: Path) -> None:
    project = await _create_project(test_app, tmp_path / "proj")
    await test_app.put(
        f"/api/v1/projects/{project['id']}/forms/{_AI}",
        json={"completed": False, "answers": {"used_ai": "no", "consent": True}},
    )

    # Omitting answers must keep the previously saved ones.
    resp = await test_app.put(f"/api/v1/projects/{project['id']}/forms/{_AI}", json={"completed": True})

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["completed"] is True
    assert data["answers"]["used_ai"] == "no"


async def test__api__preview_form__renders_markdown(test_app: AsyncClient, tmp_path: Path) -> None:
    project = await _create_project(test_app, tmp_path / "proj")
    await test_app.put(
        f"/api/v1/projects/{project['id']}/forms/{_AI}",
        json={
            "completed": True,
            "answers": {
                "used_ai": "yes",
                "usage_table": [{"tool": "ChatGPT", "version": "GPT-4o", "kind": "редактура", "scope": "гл. 2"}],
                "pct": 20,
                "details": "x" * 90,
                "consent": True,
            },
        },
    )

    resp = await test_app.get(f"/api/v1/projects/{project['id']}/forms/{_AI}/preview")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["format"] == "markdown"
    assert data["output_name"] == "Декларация ИИ.md"
    assert "ChatGPT" in data["content"]
    assert "Декларация" in data["content"]


async def test__api__preview_form__unknown_project__returns_404(test_app: AsyncClient) -> None:
    fake = "00000000-0000-0000-0000-000000000000"

    resp = await test_app.get(f"/api/v1/projects/{fake}/forms/{_AI}/preview")

    assert resp.status_code == 404
