from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import call

import pytest
from hse_doc_studio.infra.office.convert_manager import OfficeConvertManager
from httpx import AsyncClient
from pytest_mock import MockerFixture


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


# --- конвертация office при загрузке (характеризация перед выносом в диспетчер) ---


def _convert_image(convert_call: Any) -> object:
    """Образ из вызова `convert_to_pdf(self, source, image=None)` с autospec: None, если не передан."""
    args, kwargs = convert_call.args, convert_call.kwargs
    return kwargs["image"] if "image" in kwargs else (args[2] if len(args) > 2 else None)  # noqa: PLR2004


async def _upload(client: AsyncClient, project: dict, filename: str, content: bytes = b"office bytes") -> dict:
    doc_id = await _first_doc_id(client, project["id"])
    resp = await client.post(
        f"/api/v1/projects/{project['id']}/documents/{doc_id}/custom-file",
        files={"file": (filename, content, "application/octet-stream")},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _sibling_pdf(project: dict, data: dict) -> Path:
    return (Path(project["folder"]) / data["custom_file"]["stored_path"]).with_suffix(".pdf")


async def test__upload_custom_file__docx__preview_written_and_flag_true(
    test_app: AsyncClient, project: dict, mocker: MockerFixture
) -> None:
    done: list[str] = []

    async def _convert(self: OfficeConvertManager, source: Path, image: str | None = None) -> bytes:
        done.append(source.name)
        return b"%PDF-1.4 preview"

    convert = mocker.patch.object(OfficeConvertManager, "convert_to_pdf", autospec=True, side_effect=_convert)

    data = await _upload(test_app, project, "report.docx")

    # ответ дождался конвертации: флаг выставлен внутри корутины, а превью уже на диске
    assert done == ["report.docx"]
    assert data["custom_file"]["preview_available"] is True
    assert data["signing_available"] is True
    assert _sibling_pdf(project, data).read_bytes() == b"%PDF-1.4 preview"
    convert.assert_awaited_once()


@pytest.mark.parametrize("failure", ["none", "raises"])
async def test__upload_custom_file__converter_none_or_raises__flag_false_upload_ok(
    test_app: AsyncClient, project: dict, mocker: MockerFixture, failure: str
) -> None:
    if failure == "none":
        convert = mocker.patch.object(OfficeConvertManager, "convert_to_pdf", autospec=True, return_value=None)
    else:
        convert = mocker.patch.object(
            OfficeConvertManager, "convert_to_pdf", autospec=True, side_effect=RuntimeError("gotenberg down")
        )

    data = await _upload(test_app, project, "report.docx")

    convert.assert_awaited_once()
    assert data["custom_file"]["original_filename"] == "report.docx"
    assert data["custom_file"]["preview_available"] is False
    assert data["signing_available"] is False
    assert not _sibling_pdf(project, data).exists()
    assert (Path(project["folder"]) / data["custom_file"]["stored_path"]).read_bytes() == b"office bytes"


async def test__upload_custom_file__converter_called_without_image(
    test_app: AsyncClient, project: dict, mocker: MockerFixture
) -> None:
    # Загрузка идёт на образе по умолчанию из деплоя (в отличие от колбэка ONLYOFFICE и сборки,
    # которые передают активный образ): расхождение зафиксировано как есть.
    convert = mocker.patch.object(OfficeConvertManager, "convert_to_pdf", autospec=True, return_value=b"%PDF-1.4")

    data = await _upload(test_app, project, "slides.pptx")

    assert convert.await_args_list == [call(mocker.ANY, Path(project["folder"]) / data["custom_file"]["stored_path"])]
    assert _convert_image(convert.await_args) is None


@pytest.mark.parametrize("filename", ["doc.pdf", "notes.xyz", "archive.zip", "page.html"])
async def test__upload_custom_file__pdf_or_not_convertible__converter_never_called(
    test_app: AsyncClient, project: dict, mocker: MockerFixture, filename: str
) -> None:
    convert = mocker.patch.object(OfficeConvertManager, "convert_to_pdf", autospec=True, return_value=b"%PDF-1.4")

    data = await _upload(test_app, project, filename, b"%PDF-1.4 x")

    convert.assert_not_awaited()
    if filename != "doc.pdf":
        assert not _sibling_pdf(project, data).exists()
        assert data["custom_file"]["preview_available"] is False
