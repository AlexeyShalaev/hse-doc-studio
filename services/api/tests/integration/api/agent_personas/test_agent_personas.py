from __future__ import annotations

import pytest
from httpx import AsyncClient


async def test__api__list_agent_personas__empty_by_default(test_app: AsyncClient) -> None:
    resp = await test_app.get("/api/v1/agent-personas")

    assert resp.status_code == 200, resp.text
    assert resp.json() == []


async def test__api__list_builtin_personas__returns_shipped_presets(test_app: AsyncClient) -> None:
    resp = await test_app.get("/api/v1/agent-personas/builtins")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    ids = {p["id"] for p in data}
    assert "methodologist" in ids
    assert all({"id", "label", "description", "instruction"} <= p.keys() for p in data)


async def test__api__create_agent_persona__persists_and_returns_201(test_app: AsyncClient) -> None:
    resp = await test_app.post(
        "/api/v1/agent-personas",
        json={"label": "Reviewer", "instruction": "Be strict", "description": "Custom role"},
    )

    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["label"] == "Reviewer"
    assert data["instruction"] == "Be strict"
    assert data["description"] == "Custom role"
    assert "id" in data


async def test__api__create_agent_persona__trims_whitespace_from_label_and_instruction(test_app: AsyncClient) -> None:
    resp = await test_app.post(
        "/api/v1/agent-personas",
        json={"label": "  Reviewer  ", "instruction": "  Be strict  "},
    )

    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["label"] == "Reviewer"
    assert data["instruction"] == "Be strict"


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"label": "   ", "instruction": "Be strict"}, id="blank-label"),
        pytest.param({"label": "Reviewer", "instruction": "   "}, id="blank-instruction"),
    ],
)
async def test__api__create_agent_persona__blank_required_field__returns_400(
    test_app: AsyncClient, payload: dict[str, str]
) -> None:
    resp = await test_app.post("/api/v1/agent-personas", json=payload)

    assert resp.status_code == 400, resp.text


async def test__api__create_then_list_and_get(test_app: AsyncClient) -> None:
    created = (
        await test_app.post(
            "/api/v1/agent-personas",
            json={"label": "Reviewer", "instruction": "Be strict"},
        )
    ).json()
    persona_id = created["id"]

    listed = await test_app.get("/api/v1/agent-personas")
    assert listed.status_code == 200
    assert [p["id"] for p in listed.json()] == [persona_id]

    got = await test_app.get(f"/api/v1/agent-personas/{persona_id}")
    assert got.status_code == 200
    assert got.json()["label"] == "Reviewer"


async def test__api__get_agent_persona__missing__returns_404(test_app: AsyncClient) -> None:
    resp = await test_app.get("/api/v1/agent-personas/00000000-0000-0000-0000-000000000000")

    assert resp.status_code == 404


async def test__api__update_agent_persona__partial_patch_preserves_other_fields(test_app: AsyncClient) -> None:
    persona_id = (
        await test_app.post(
            "/api/v1/agent-personas",
            json={"label": "Reviewer", "instruction": "Be strict", "description": "d"},
        )
    ).json()["id"]

    resp = await test_app.patch(f"/api/v1/agent-personas/{persona_id}", json={"label": "Renamed"})

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["label"] == "Renamed"
    assert data["instruction"] == "Be strict"  # untouched
    assert data["description"] == "d"  # untouched


async def test__api__update_agent_persona__missing__returns_404(test_app: AsyncClient) -> None:
    resp = await test_app.patch(
        "/api/v1/agent-personas/00000000-0000-0000-0000-000000000000",
        json={"label": "Renamed"},
    )

    assert resp.status_code == 404


@pytest.mark.parametrize(
    "patch",
    [
        pytest.param({"label": "   "}, id="blank-label"),
        pytest.param({"instruction": "   "}, id="blank-instruction"),
    ],
)
async def test__api__update_agent_persona__blank_required_field__returns_400(
    test_app: AsyncClient, patch: dict[str, str]
) -> None:
    persona_id = (
        await test_app.post(
            "/api/v1/agent-personas",
            json={"label": "Reviewer", "instruction": "Be strict"},
        )
    ).json()["id"]

    resp = await test_app.patch(f"/api/v1/agent-personas/{persona_id}", json=patch)

    assert resp.status_code == 400, resp.text


async def test__api__delete_agent_persona__existing__removes_it(test_app: AsyncClient) -> None:
    persona_id = (
        await test_app.post(
            "/api/v1/agent-personas",
            json={"label": "Reviewer", "instruction": "Be strict"},
        )
    ).json()["id"]

    resp = await test_app.delete(f"/api/v1/agent-personas/{persona_id}")
    assert resp.status_code == 204

    assert (await test_app.get(f"/api/v1/agent-personas/{persona_id}")).status_code == 404


async def test__api__delete_agent_persona__missing__returns_404(test_app: AsyncClient) -> None:
    resp = await test_app.delete("/api/v1/agent-personas/00000000-0000-0000-0000-000000000000")

    assert resp.status_code == 404
