from __future__ import annotations

import base64
import io
import zipfile
from pathlib import Path

import pytest
from httpx import AsyncClient

from tests.factories import project_api_payload

_FAKE_ID = "00000000-0000-0000-0000-000000000000"
# Real submission profile from packs/hse-cs-se/templates/vkr/versions/2026.1/version.yaml
# (pack_submission.profiles) — КТ1, the thesis-topic-defense checkpoint.
_CHECKPOINT_1 = "checkpoint-1"
_CREATE_BODY = {"profile_id": _CHECKPOINT_1, "items": [], "extra_items": [], "archive_format": "zip"}
# 1×1 transparent PNG — enough for the signature-slot upload validation.
_PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


async def _create_project(client: AsyncClient, folder: Path) -> dict:
    folder.mkdir(exist_ok=True)
    resp = await client.post("/api/v1/projects", json=project_api_payload(str(folder)))
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _sign_annotation(client: AsyncClient, project_id: str) -> None:
    """Place author + supervisor signatures on the annotation.

    Инструкция защиты тем ВКР 2025/26: на КТ1 титул Аннотации research-проекта
    подписывают студент И руководитель, поэтому checkpoint-1 требует оба слота
    и без размещённых PNG сборка пакета честно отклоняется (400).
    """
    for slot in ("author", "supervisor"):
        resp = await client.post(
            f"/api/v1/projects/{project_id}/signatures/slots/{slot}/png",
            files={"file": ("sig.png", _PNG_1PX, "image/png")},
        )
        assert resp.status_code == 200, resp.text
        resp = await client.patch(
            f"/api/v1/projects/{project_id}/signatures/placements/annotation/{slot}",
            json={"enabled": True},
        )
        assert resp.status_code == 200, resp.text


async def _create_submission(client: AsyncClient, project_id: str) -> dict:
    resp = await client.post(f"/api/v1/projects/{project_id}/submissions", json=_CREATE_BODY)
    assert resp.status_code == 201, resp.text
    return resp.json()


# --- profiles ----------------------------------------------------------------


async def test__api__get_submission_profiles__real_pack__includes_checkpoint_1(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    project = await _create_project(test_app, tmp_path / "proj")

    resp = await test_app.get(f"/api/v1/projects/{project['id']}/submissions/profiles")

    assert resp.status_code == 200, resp.text
    profiles = resp.json()
    assert isinstance(profiles, list)
    checkpoint = next(p for p in profiles if p["id"] == _CHECKPOINT_1)
    assert "ru" in checkpoint["name"]
    assert isinstance(checkpoint["items"], list)
    assert len(checkpoint["items"]) >= 1
    assert all("doc_id" in item and "signatures" in item for item in checkpoint["items"])


async def test__api__get_submission_profiles__real_pack__serialises_composition_gates(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    # Гейты применяет build_item_list, но клиент считает готовность точки сам и
    # без них показывает блокеры, которых при сборке пакета не будет: thesis на
    # КТ2 сдаёт только проектный формат, Текст программы снимается под NDA.
    project = await _create_project(test_app, tmp_path / "proj")

    resp = await test_app.get(f"/api/v1/projects/{project['id']}/submissions/profiles")

    assert resp.status_code == 200, resp.text
    profiles = resp.json()
    items = [item for profile in profiles for item in profile["items"]]
    assert all("skip_if_nda" in item and "supported_kinds" in item for item in items)
    extras = [extra for profile in profiles for extra in profile["extra_items"]]
    assert all("supported_kinds" in extra for extra in extras)

    kind_gated = [item for item in items if item["supported_kinds"] != ["research", "project"]]
    assert kind_gated, "в паке vkr пункт thesis на КТ2/КТ3 гейтится supported_kinds"
    assert all(item["doc_id"] == "thesis" for item in kind_gated)


# --- preflight -----------------------------------------------------------


async def test__api__get_submission_preflight__pristine_project__no_custom_docs_to_decide(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    project = await _create_project(test_app, tmp_path / "proj")

    resp = await test_app.get(
        f"/api/v1/projects/{project['id']}/submissions/preflight",
        params={"profile_id": _CHECKPOINT_1},
    )

    # A freshly-created project has no custom_file documents, so there is
    # nothing that needs a convert-to-PDF decision yet.
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


async def test__api__get_submission_preflight__unknown_profile__returns_404(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    project = await _create_project(test_app, tmp_path / "proj")

    resp = await test_app.get(
        f"/api/v1/projects/{project['id']}/submissions/preflight",
        params={"profile_id": "no-such-profile"},
    )

    assert resp.status_code == 404


# --- create / list / download: end-to-end flow --------------------------


async def test__api__create_submission__checkpoint_1__unsigned_annotation__returns_400(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    # Инструкция 2025/26: на КТ1 Аннотация research-проекта сдаётся с
    # ПОДПИСАННЫМ титулом — без размещённых подписей сборка отклоняется.
    project = await _create_project(test_app, tmp_path / "proj")

    resp = await test_app.post(f"/api/v1/projects/{project['id']}/submissions", json=_CREATE_BODY)

    assert resp.status_code == 400, resp.text
    assert "annotation" in resp.json()["detail"]


async def test__api__create_submission__checkpoint_1__returns_201_with_expected_shape(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    project = await _create_project(test_app, tmp_path / "proj")
    await _sign_annotation(test_app, project["id"])

    resp = await test_app.post(f"/api/v1/projects/{project['id']}/submissions", json=_CREATE_BODY)

    assert resp.status_code == 201, resp.text
    record = resp.json()
    assert record["profile_id"] == _CHECKPOINT_1
    assert record["archive_format"] == "zip"
    assert record["output_path"].endswith(".zip")
    # checkpoint-1 resolves to real documents this (research/solo) project
    # actually has — topic defence presentation + signed annotation —
    # regardless of items in the body.
    assert record["doc_count"] >= 1
    assert "id" in record


async def test__api__create_submission__then_list__shows_the_new_submission(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    project = await _create_project(test_app, tmp_path / "proj")
    project_id = project["id"]
    await _sign_annotation(test_app, project_id)
    created = await _create_submission(test_app, project_id)

    resp = await test_app.get(f"/api/v1/projects/{project_id}/submissions")

    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert [i["id"] for i in items] == [created["id"]]
    assert items[0]["size_bytes"] is not None
    assert items[0]["profile_name"] is not None


async def test__api__list_submissions__pristine_project__returns_empty_list(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    project = await _create_project(test_app, tmp_path / "proj")

    resp = await test_app.get(f"/api/v1/projects/{project['id']}/submissions")

    assert resp.status_code == 200, resp.text
    assert resp.json() == []


async def test__api__download_submission__streams_a_real_zip_archive(test_app: AsyncClient, tmp_path: Path) -> None:
    project = await _create_project(test_app, tmp_path / "proj")
    project_id = project["id"]
    await _sign_annotation(test_app, project_id)
    created = await _create_submission(test_app, project_id)

    resp = await test_app.get(f"/api/v1/projects/{project_id}/submissions/{created['id']}/download")

    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/zip"
    assert "attachment" in resp.headers["content-disposition"]
    assert zipfile.is_zipfile(io.BytesIO(resp.content))


# --- error paths -----------------------------------------------------------


async def test__api__create_submission__unknown_profile__returns_404(test_app: AsyncClient, tmp_path: Path) -> None:
    project = await _create_project(test_app, tmp_path / "proj")

    resp = await test_app.post(
        f"/api/v1/projects/{project['id']}/submissions",
        json={**_CREATE_BODY, "profile_id": "no-such-profile"},
    )

    assert resp.status_code == 404


async def test__api__download_submission__nonexistent_submission_id__returns_404(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    project = await _create_project(test_app, tmp_path / "proj")

    resp = await test_app.get(f"/api/v1/projects/{project['id']}/submissions/{_FAKE_ID}/download")

    assert resp.status_code == 404


@pytest.mark.parametrize(
    ("method", "path_suffix", "json_body"),
    [
        ("GET", "/submissions/profiles", None),
        ("GET", f"/submissions/preflight?profile_id={_CHECKPOINT_1}", None),
        ("GET", "/submissions", None),
        ("GET", f"/submissions/{_FAKE_ID}/download", None),
        ("POST", "/submissions", _CREATE_BODY),
    ],
)
async def test__api__submission_endpoints__nonexistent_project__returns_404(
    test_app: AsyncClient, method: str, path_suffix: str, json_body: dict | None
) -> None:
    resp = await test_app.request(method, f"/api/v1/projects/{_FAKE_ID}{path_suffix}", json=json_body)

    assert resp.status_code == 404
