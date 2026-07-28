from __future__ import annotations

from pathlib import Path

from httpx import AsyncClient

from tests.factories import project_api_payload


async def _create_project(client: AsyncClient, folder: Path) -> dict:
    folder.mkdir(exist_ok=True)
    resp = await client.post("/api/v1/projects", json=project_api_payload(str(folder)))
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test__api__get_signatures__returns_slots_placements_and_runtime_slots(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    project = await _create_project(test_app, tmp_path / "proj")

    resp = await test_app.get(f"/api/v1/projects/{project['id']}/signatures")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["slots"] == {}
    assert data["placements"] == {}
    assert any(s["id"] == "author" for s in data["runtime_slots"])


async def test__api__get_signatures__nonexistent_project__returns_404(test_app: AsyncClient) -> None:
    fake_id = "00000000-0000-0000-0000-000000000000"

    resp = await test_app.get(f"/api/v1/projects/{fake_id}/signatures")

    assert resp.status_code == 404


# 1x1 px transparent PNG (smallest valid PNG payload)
_MIN_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)

# A `kind=research` VKR project (as created by `project_api_payload`) has three
# documents: annotation, thesis, presentation. The pack's `author` signature
# slot applies to the first two but not the presentation.
_DOCS_WITH_AUTHOR_SLOT = ["annotation", "thesis"]
_DOC_WITHOUT_AUTHOR_SLOT = "presentation"


async def test__api__upload_signature_png__valid_png__saves_file_and_seeds_placements(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    project = await _create_project(test_app, tmp_path / "proj")
    project_id = project["id"]
    folder = Path(project["folder"])

    resp = await test_app.post(
        f"/api/v1/projects/{project_id}/signatures/slots/author/png",
        files={"file": ("author.png", _MIN_PNG, "image/png")},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["png_path"] == ".hse-studio/signatures/author.png"

    on_disk = folder / ".hse-studio" / "signatures" / "author.png"
    assert on_disk.exists()
    assert on_disk.read_bytes() == _MIN_PNG

    # A default (disabled) placement is seeded for every doc the slot applies to.
    state = (await test_app.get(f"/api/v1/projects/{project_id}/signatures")).json()
    for doc_id in _DOCS_WITH_AUTHOR_SLOT:
        assert doc_id in state["placements"], f"placement not seeded for {doc_id}"
        assert state["placements"][doc_id]["author"]["enabled"] is False
    assert state["slots"]["author"]["png_path"] == body["png_path"]


async def test__api__upload_signature_png__non_png_content__400(test_app: AsyncClient, tmp_path: Path) -> None:
    project = await _create_project(test_app, tmp_path / "proj")

    resp = await test_app.post(
        f"/api/v1/projects/{project['id']}/signatures/slots/author/png",
        files={"file": ("bogus.txt", b"not a png", "text/plain")},
    )

    assert resp.status_code == 400, resp.text
    assert "png" in resp.json()["detail"].lower()


async def test__api__upload_signature_png__slot_not_in_template__404(test_app: AsyncClient, tmp_path: Path) -> None:
    project = await _create_project(test_app, tmp_path / "proj")

    resp = await test_app.post(
        f"/api/v1/projects/{project['id']}/signatures/slots/ghost-slot/png",
        files={"file": ("x.png", _MIN_PNG, "image/png")},
    )

    assert resp.status_code == 404


async def test__api__update_placement__enabled_and_position__reflected_on_get(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    project = await _create_project(test_app, tmp_path / "proj")
    project_id = project["id"]
    doc_id = _DOCS_WITH_AUTHOR_SLOT[0]

    resp = await test_app.patch(
        f"/api/v1/projects/{project_id}/signatures/placements/{doc_id}/author",
        json={"enabled": True, "x_mm": 30.0, "y_mm": 40.0},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["enabled"] is True
    assert resp.json()["x_mm"] == 30.0

    state = (await test_app.get(f"/api/v1/projects/{project_id}/signatures")).json()
    placement = state["placements"][doc_id]["author"]
    assert placement["enabled"] is True
    assert placement["y_mm"] == 40.0


async def test__api__update_placement__partial_update__preserves_unset_fields(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    project = await _create_project(test_app, tmp_path / "proj")
    project_id = project["id"]
    doc_id = _DOCS_WITH_AUTHOR_SLOT[0]
    url = f"/api/v1/projects/{project_id}/signatures/placements/{doc_id}/author"
    await test_app.patch(url, json={"enabled": True, "x_mm": 15.0})

    resp = await test_app.patch(url, json={"y_mm": 99.0})

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["y_mm"] == 99.0
    assert data["enabled"] is True  # untouched by the second, partial patch
    assert data["x_mm"] == 15.0


async def test__api__update_placement__slot_does_not_apply_to_doc__400(test_app: AsyncClient, tmp_path: Path) -> None:
    project = await _create_project(test_app, tmp_path / "proj")
    project_id = project["id"]

    resp = await test_app.patch(
        f"/api/v1/projects/{project_id}/signatures/placements/{_DOC_WITHOUT_AUTHOR_SLOT}/author",
        json={"enabled": True},
    )

    assert resp.status_code == 400, resp.text


async def test__api__update_placement__nonexistent_project__404(test_app: AsyncClient) -> None:
    fake_id = "00000000-0000-0000-0000-000000000000"

    resp = await test_app.patch(
        f"/api/v1/projects/{fake_id}/signatures/placements/thesis/author",
        json={"enabled": True},
    )

    assert resp.status_code == 404


async def test__api__update_slot_config__no_identity__sign_mode_forced_to_image_and_reason_cleared(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    # Reason/crypto sign mode only carry meaning once a signing identity is
    # attached — without one, the slot always reports plain image mode.
    project = await _create_project(test_app, tmp_path / "proj")
    project_id = project["id"]

    resp = await test_app.patch(
        f"/api/v1/projects/{project_id}/signatures/slots/author/config",
        json={"sign_mode": "image", "sign_reason": "Автор работы"},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["sign_reason"] == ""
    assert resp.json()["sign_mode"] == "image"


async def test__api__update_slot_config__with_signing_identity__persists_mode_and_reason(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    project = await _create_project(test_app, tmp_path / "proj")
    project_id = project["id"]
    identity_resp = await test_app.post(
        "/api/v1/signing-identities/self-signed",
        json={"label": "Test identity", "subject_cn": "Ivan Ivanov", "validity_days": 365},
    )
    assert identity_resp.status_code == 201, identity_resp.text
    identity_id = identity_resp.json()["id"]

    resp = await test_app.patch(
        f"/api/v1/projects/{project_id}/signatures/slots/author/config",
        json={"signing_identity_id": identity_id, "sign_mode": "image_crypto", "sign_reason": "Автор работы"},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["signing_identity_id"] == identity_id
    assert resp.json()["sign_reason"] == "Автор работы"


async def test__api__delete_signature_png__removes_slot_from_state(test_app: AsyncClient, tmp_path: Path) -> None:
    project = await _create_project(test_app, tmp_path / "proj")
    project_id = project["id"]
    await test_app.post(
        f"/api/v1/projects/{project_id}/signatures/slots/author/png",
        files={"file": ("author.png", _MIN_PNG, "image/png")},
    )

    resp = await test_app.delete(f"/api/v1/projects/{project_id}/signatures/slots/author/png")

    assert resp.status_code == 204, resp.text
    state = (await test_app.get(f"/api/v1/projects/{project_id}/signatures")).json()
    assert "author" not in state["slots"]
