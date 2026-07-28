from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient

from tests.factories import project_api_payload


async def _create_project(client: AsyncClient, folder: Path) -> dict:
    folder.mkdir(exist_ok=True)
    resp = await client.post("/api/v1/projects", json=project_api_payload(str(folder)))
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _get_documents(client: AsyncClient, project_id: str) -> list[dict]:
    resp = await client.get(f"/api/v1/projects/{project_id}/documents")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _doc_source_path(proj_folder: Path, documents: list[dict], doc_id: str) -> Path:
    doc = next(d for d in documents if d["id"] == doc_id)
    return proj_folder / doc["source_file"]


def _presentation_beamer_path(proj_folder: Path) -> Path:
    # The "presentation" doc's *chosen* variant is pptx (binary, not scanned for
    # requirements), but the pack always materializes every variant, so its real
    # beamer/*.tex sits on disk too. We use it (rather than e.g. "annotation") as
    # the second .tex document for cross-doc reference tests because "annotation"
    # is a kind-split doc (declared under research/ in the pack) whose instance
    # folder never resolves to a doc id in get_requirements' scan — a real
    # instance_dir_map bug (see core/services.py) that silently drops any
    # requirement reference written inside a kind-split document.
    return proj_folder / "presentation" / "beamer" / "presentation.tex"


def _append(path: Path, text: str) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(text)


async def test__get_requirements__fresh_project__returns_default_macro_format_with_no_items(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    project = await _create_project(test_app, tmp_path / "proj")

    resp = await test_app.get(f"/api/v1/projects/{project['id']}/requirements")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["items"] == []
    assert body["format"]["kind"] == "macro"
    assert body["format_overridden"] is False


async def test__get_requirements__nonexistent_project__returns_404(test_app: AsyncClient) -> None:
    fake_id = "00000000-0000-0000-0000-000000000000"

    resp = await test_app.get(f"/api/v1/projects/{fake_id}/requirements")

    assert resp.status_code == 404


async def test__get_requirements__macro_definition_written_to_real_doc__appears_unreferenced(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    proj_folder = tmp_path / "proj"
    project = await _create_project(test_app, proj_folder)
    documents = await _get_documents(test_app, project["id"])
    thesis_path = _doc_source_path(proj_folder, documents, "thesis")

    _append(thesis_path, "\n\\req{REQ-001}{Test requirement}\n")

    resp = await test_app.get(f"/api/v1/projects/{project['id']}/requirements")

    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == "REQ-001"
    assert items[0]["title"] == "Test requirement"
    assert items[0]["source"] == "thesis"
    assert items[0]["referenced_in"] == []
    assert items[0]["status"] == "warn"


async def test__get_requirements__macro_reference_in_another_doc__marks_status_ok(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    proj_folder = tmp_path / "proj"
    project = await _create_project(test_app, proj_folder)
    documents = await _get_documents(test_app, project["id"])
    thesis_path = _doc_source_path(proj_folder, documents, "thesis")
    presentation_path = _presentation_beamer_path(proj_folder)

    _append(thesis_path, "\n\\req{REQ-001}{Test requirement}\n")
    _append(presentation_path, "\n\\reqref{REQ-001}\n")

    resp = await test_app.get(f"/api/v1/projects/{project['id']}/requirements")

    assert resp.status_code == 200, resp.text
    item = resp.json()["items"][0]
    assert item["status"] == "ok"
    assert item["referenced_in"] == ["presentation"]


async def test__get_requirements__reference_without_definition__reported_as_error(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    proj_folder = tmp_path / "proj"
    project = await _create_project(test_app, proj_folder)
    presentation_path = _presentation_beamer_path(proj_folder)

    _append(presentation_path, "\n\\reqref{REQ-ORPHAN}\n")

    resp = await test_app.get(f"/api/v1/projects/{project['id']}/requirements")

    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == "REQ-ORPHAN"
    assert items[0]["status"] == "err"
    assert items[0]["referenced_in"] == ["presentation"]


async def test__get_requirements__reference_in_kind_split_doc__is_attributed_not_dropped(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    # Regression test: instance_dir_map used to compute a kind-split document's
    # (e.g. "annotation", declared under research/ in the pack) top-level dir
    # from its pack-level source_file without remapping it to the flattened
    # on-disk layout, so references written inside it were silently dropped
    # from the matrix instead of being attributed to that document.
    proj_folder = tmp_path / "proj"
    project = await _create_project(test_app, proj_folder)
    documents = await _get_documents(test_app, project["id"])
    thesis_path = _doc_source_path(proj_folder, documents, "thesis")
    annotation_path = _doc_source_path(proj_folder, documents, "annotation")

    _append(thesis_path, "\n\\req{REQ-001}{Test requirement}\n")
    _append(annotation_path, "\n\\reqref{REQ-001}\n")

    resp = await test_app.get(f"/api/v1/projects/{project['id']}/requirements")

    assert resp.status_code == 200, resp.text
    item = resp.json()["items"][0]
    assert item["status"] == "ok"
    assert item["referenced_in"] == ["annotation"]


async def test__update_requirements_format__id_kind__changes_subsequent_get_matrix_and_marks_overridden(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    proj_folder = tmp_path / "proj"
    project = await _create_project(test_app, proj_folder)
    documents = await _get_documents(test_app, project["id"])
    thesis_path = _doc_source_path(proj_folder, documents, "thesis")
    presentation_path = _presentation_beamer_path(proj_folder)
    put_body = {
        "format": {
            "kind": "id",
            "id_pattern": r"REQ-\d+",
            "definition_docs": ["thesis"],
            "def_pattern": None,
            "ref_pattern": None,
        }
    }

    put_resp = await test_app.put(f"/api/v1/projects/{project['id']}/requirements/format", json=put_body)

    assert put_resp.status_code == 200, put_resp.text
    put_data = put_resp.json()
    assert put_data["format"]["kind"] == "id"
    assert put_data["format"]["id_pattern"] == r"REQ-\d+"
    assert put_data["format_overridden"] is True

    _append(thesis_path, "\nREQ-042 -- Some feature\n")
    _append(presentation_path, "\nREQ-042\n")
    get_resp = await test_app.get(f"/api/v1/projects/{project['id']}/requirements")

    assert get_resp.status_code == 200, get_resp.text
    items = get_resp.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == "REQ-042"
    assert items[0]["source"] == "thesis"
    assert items[0]["referenced_in"] == ["presentation"]


async def test__update_requirements_format__null_format__clears_override_back_to_pack_default(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    project = await _create_project(test_app, tmp_path / "proj")
    custom_body = {
        "format": {
            "kind": "id",
            "id_pattern": r"REQ-\d+",
            "definition_docs": ["thesis"],
            "def_pattern": None,
            "ref_pattern": None,
        }
    }
    set_resp = await test_app.put(f"/api/v1/projects/{project['id']}/requirements/format", json=custom_body)
    assert set_resp.status_code == 200, set_resp.text
    assert set_resp.json()["format_overridden"] is True

    clear_resp = await test_app.put(f"/api/v1/projects/{project['id']}/requirements/format", json={"format": None})

    assert clear_resp.status_code == 200, clear_resp.text
    clear_data = clear_resp.json()
    assert clear_data["format"]["kind"] == "macro"
    assert clear_data["format_overridden"] is False


async def test__update_requirements_format__nonexistent_project__returns_404(test_app: AsyncClient) -> None:
    fake_id = "00000000-0000-0000-0000-000000000000"

    resp = await test_app.put(
        f"/api/v1/projects/{fake_id}/requirements/format",
        json={"format": {"kind": "macro"}},
    )

    assert resp.status_code == 404


@pytest.mark.parametrize(
    "format_body",
    [
        pytest.param(
            {"kind": "id", "id_pattern": None, "definition_docs": [], "def_pattern": None, "ref_pattern": None},
            id="id_kind_missing_id_pattern",
        ),
        pytest.param(
            {
                "kind": "id",
                "id_pattern": "REQ-(unclosed",
                "definition_docs": [],
                "def_pattern": None,
                "ref_pattern": None,
            },
            id="id_kind_invalid_regex",
        ),
        pytest.param(
            {"kind": "custom", "id_pattern": None, "definition_docs": [], "def_pattern": None, "ref_pattern": None},
            id="custom_kind_missing_patterns",
        ),
        pytest.param(
            {
                "kind": "custom",
                "id_pattern": None,
                "definition_docs": [],
                # Valid regex but missing the required (?P<id>...) named group.
                "def_pattern": r"(\d+)",
                "ref_pattern": r"(?P<ids>\d+)",
            },
            id="custom_kind_def_pattern_missing_named_group",
        ),
    ],
)
async def test__update_requirements_format__invalid_format__returns_400(
    test_app: AsyncClient, tmp_path: Path, format_body: dict[str, Any]
) -> None:
    project = await _create_project(test_app, tmp_path / "proj")

    resp = await test_app.put(
        f"/api/v1/projects/{project['id']}/requirements/format",
        json={"format": format_body},
    )

    assert resp.status_code == 400, resp.text
