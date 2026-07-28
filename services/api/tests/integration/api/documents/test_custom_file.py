from __future__ import annotations

import pytest
from httpx import AsyncClient


async def _first_doc_id(client: AsyncClient, project_id: str) -> str:
    resp = await client.get(f"/api/v1/projects/{project_id}/documents")
    assert resp.status_code == 200, resp.text
    return resp.json()[0]["id"]


async def test__api__upload_custom_file__pdf__marks_signable_and_supersedes_variant(
    test_app: AsyncClient, project: dict
) -> None:
    project_id = project["id"]
    doc_id = await _first_doc_id(test_app, project_id)

    resp = await test_app.post(
        f"/api/v1/projects/{project_id}/documents/{doc_id}/custom-file",
        files={"file": ("my-doc.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["custom_file"] is not None
    assert data["custom_file"]["original_filename"] == "my-doc.pdf"
    assert data["custom_file"]["ext"] == ".pdf"
    assert data["signing_available"] is True
    assert data["status"] == "draft"

    # The upload response itself doesn't carry a full template resolution
    # (see _map_doc_detail — PATCH/upload/revert responses omit it, the
    # frontend re-fetches after the mutation), but the very next GET/list must
    # repoint output_file at the uploaded file — not the stale template path —
    # since that's what the download link / PDF stamper / file tree read.
    stored_path = data["custom_file"]["stored_path"]

    get_resp = await test_app.get(f"/api/v1/projects/{project_id}/documents/{doc_id}")
    assert get_resp.status_code == 200, get_resp.text
    assert get_resp.json()["output_file"] == stored_path

    list_resp = await test_app.get(f"/api/v1/projects/{project_id}/documents")
    assert list_resp.status_code == 200, list_resp.text
    listed = next(d for d in list_resp.json() if d["id"] == doc_id)
    assert listed["output_file"] == stored_path


async def test__api__upload_custom_file__unknown_format__unsignable_but_accepted(
    test_app: AsyncClient, project: dict
) -> None:
    project_id = project["id"]
    doc_id = await _first_doc_id(test_app, project_id)

    resp = await test_app.post(
        f"/api/v1/projects/{project_id}/documents/{doc_id}/custom-file",
        files={"file": ("notes.xyz", b"arbitrary bytes", "application/octet-stream")},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["custom_file"]["ext"] == ".xyz"
    assert data["signing_available"] is False


async def test__api__revert_custom_file__clears_override(test_app: AsyncClient, project: dict) -> None:
    project_id = project["id"]
    doc_id = await _first_doc_id(test_app, project_id)
    upload_resp = await test_app.post(
        f"/api/v1/projects/{project_id}/documents/{doc_id}/custom-file",
        files={"file": ("my-doc.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    assert upload_resp.status_code == 200, upload_resp.text

    revert_resp = await test_app.delete(f"/api/v1/projects/{project_id}/documents/{doc_id}/custom-file")

    assert revert_resp.status_code == 200, revert_resp.text
    data = revert_resp.json()
    assert data["custom_file"] is None
    assert data["signing_available"] is True


async def test__api__revert_custom_file__none_set__returns_400(test_app: AsyncClient, project: dict) -> None:
    project_id = project["id"]
    doc_id = await _first_doc_id(test_app, project_id)

    resp = await test_app.delete(f"/api/v1/projects/{project_id}/documents/{doc_id}/custom-file")

    assert resp.status_code == 400


async def test__api__upload_custom_file__nonexistent_project__returns_404(test_app: AsyncClient) -> None:
    fake_id = "00000000-0000-0000-0000-000000000000"

    resp = await test_app.post(
        f"/api/v1/projects/{fake_id}/documents/vkr/custom-file",
        files={"file": ("x.pdf", b"%PDF-1.4", "application/pdf")},
    )

    assert resp.status_code == 404


async def test__api__get_submission_preflight__no_custom_docs__returns_empty_list(
    test_app: AsyncClient, project: dict
) -> None:
    project_id = project["id"]
    profiles_resp = await test_app.get(f"/api/v1/projects/{project_id}/submissions/profiles")
    assert profiles_resp.status_code == 200, profiles_resp.text
    profiles = profiles_resp.json()
    if not profiles:
        pytest.skip("template has no submission profiles configured")
    profile_id = profiles[0]["id"]

    resp = await test_app.get(f"/api/v1/projects/{project_id}/submissions/preflight", params={"profile_id": profile_id})

    assert resp.status_code == 200, resp.text
    assert resp.json() == []


async def test__api__get_submission_preflight__ignores_missing_required_signatures(
    test_app: AsyncClient, project: dict
) -> None:
    """Preflight must not fail just because a profile's required signatures
    (author/supervisor) aren't filled in yet — that validation belongs to the
    actual package-build call, not to this "any custom docs to ask about?"
    probe, which must stay usable at any point in the project's lifecycle.
    """
    project_id = project["id"]
    profiles_resp = await test_app.get(f"/api/v1/projects/{project_id}/submissions/profiles")
    profiles = profiles_resp.json()
    signed_profile = next((p for p in profiles if any(i["signatures"] for i in p["items"])), None)
    if signed_profile is None:
        pytest.skip("template has no profile with required signatures")

    resp = await test_app.get(
        f"/api/v1/projects/{project_id}/submissions/preflight",
        params={"profile_id": signed_profile["id"]},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json() == []


async def test__api__get_submission_preflight__custom_doc_in_unsigned_profile__still_listed(
    test_app: AsyncClient, project: dict
) -> None:
    project_id = project["id"]
    profiles_resp = await test_app.get(f"/api/v1/projects/{project_id}/submissions/profiles")
    profiles = profiles_resp.json()
    signed_profile = next((p for p in profiles if any(i["signatures"] for i in p["items"])), None)
    if signed_profile is None:
        pytest.skip("template has no profile with required signatures")
    doc_id = next(i["doc_id"] for i in signed_profile["items"] if i["signatures"])
    docs_resp = await test_app.get(f"/api/v1/projects/{project_id}/documents")
    if not any(d["id"] == doc_id for d in docs_resp.json()):
        pytest.skip(f"document {doc_id!r} not instantiated for this project kind")
    upload_resp = await test_app.post(
        f"/api/v1/projects/{project_id}/documents/{doc_id}/custom-file",
        files={"file": ("report.docx", b"not really a docx", "application/octet-stream")},
    )
    assert upload_resp.status_code == 200, upload_resp.text

    resp = await test_app.get(
        f"/api/v1/projects/{project_id}/submissions/preflight",
        params={"profile_id": signed_profile["id"]},
    )

    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert any(i["doc_id"] == doc_id for i in items)
    listed = next(i for i in items if i["doc_id"] == doc_id)
    assert listed["convertible"] is True
