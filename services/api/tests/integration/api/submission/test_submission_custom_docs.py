"""Характеризация упаковки пакета с custom-файлами office-формата.

Решение «конвертировать в PDF или оставить как есть» и вызов конвертера входят в
публичное поведение, которое не должно меняться при переезде конвертации на диспетчер.
Конвертер подменён на уровне `OfficeConvertManager.convert_to_pdf`; тесты читают только
HTTP-ответы, архив и файлы проекта.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.infra.office.convert_manager import OfficeConvertManager
from httpx import AsyncClient
from pytest_mock import MockerFixture

from tests.factories import project_api_payload
from tests.integration.api.submission.test_submission import _CHECKPOINT_1, _sign_annotation

# Документ профиля checkpoint-1 без обязательных подписей: его custom-файл единственный даёт содержимое пакета.
_DOC_ID = "topic_presentation"
_DOCX = b"PK custom docx bytes"
_PREVIEW = b"%PDF-1.4 converted preview"


async def _setup_project(client: AsyncClient, tmp_path: Path) -> dict[str, Any]:
    folder = tmp_path / "proj"
    folder.mkdir()
    resp = await client.post("/api/v1/projects", json=project_api_payload(str(folder)))
    assert resp.status_code == 201, resp.text
    project = resp.json()
    await _sign_annotation(client, project["id"])
    return project


async def _upload_docx(client: AsyncClient, project: dict[str, Any]) -> dict[str, Any]:
    resp = await client.post(
        f"/api/v1/projects/{project['id']}/documents/{_DOC_ID}/custom-file",
        files={"file": ("slides.docx", _DOCX, "application/octet-stream")},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["custom_file"]


async def _create_submission(
    client: AsyncClient, project: dict[str, Any], decisions: dict[str, bool] | None
) -> dict[str, Any]:
    body: dict[str, Any] = {"profile_id": _CHECKPOINT_1, "items": [], "extra_items": [], "archive_format": "zip"}
    if decisions is not None:
        body["custom_doc_decisions"] = decisions
    resp = await client.post(f"/api/v1/projects/{project['id']}/submissions", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _archive(record: dict[str, Any]) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(Path(record["output_path"]).read_bytes())) as zf:
        return {name: zf.read(name) for name in zf.namelist()}


def _by_ext(files: dict[str, bytes], ext: str) -> dict[str, bytes]:
    return {name: data for name, data in files.items() if name.lower().endswith(ext)}


async def _remembered(client: AsyncClient, project: dict[str, Any]) -> bool | None:
    resp = await client.get(f"/api/v1/projects/{project['id']}/documents/{_DOC_ID}")
    assert resp.status_code == 200, resp.text
    return resp.json()["custom_file"]["convert_to_pdf_at_package"]


async def test__create_submission__custom_docx_convert__sibling_reused_without_converter(
    test_app: AsyncClient, tmp_path: Path, mocker: MockerFixture
) -> None:
    project = await _setup_project(test_app, tmp_path)
    convert = mocker.patch.object(OfficeConvertManager, "convert_to_pdf", autospec=True, return_value=_PREVIEW)
    stored = Path(project["folder"]) / (await _upload_docx(test_app, project))["stored_path"]
    assert stored.with_suffix(".pdf").read_bytes() == _PREVIEW
    convert.reset_mock()

    record = await _create_submission(test_app, project, {_DOC_ID: True})

    convert.assert_not_awaited()
    files = _archive(record)
    assert list(_by_ext(files, ".pdf").values()) == [_PREVIEW]
    assert not _by_ext(files, ".docx")


async def test__create_submission__custom_docx_convert__missing_sibling_converted_without_image(
    test_app: AsyncClient, tmp_path: Path, mocker: MockerFixture
) -> None:
    project = await _setup_project(test_app, tmp_path)
    convert = mocker.patch.object(OfficeConvertManager, "convert_to_pdf", autospec=True, return_value=None)
    custom = await _upload_docx(test_app, project)
    sibling = (Path(project["folder"]) / custom["stored_path"]).with_suffix(".pdf")
    assert not sibling.exists()
    convert.reset_mock()
    convert.return_value = _PREVIEW

    record = await _create_submission(test_app, project, {_DOC_ID: True})

    # Упаковка идёт на образе по умолчанию из деплоя (без активного образа): расхождение сохраняется как есть.
    convert.assert_awaited_once()
    assert convert.await_args.args == (mocker.ANY, Path(project["folder"]) / custom["stored_path"])
    assert convert.await_args.kwargs == {}
    assert sibling.read_bytes() == _PREVIEW
    files = _archive(record)
    assert list(_by_ext(files, ".pdf").values()) == [_PREVIEW]
    assert not _by_ext(files, ".docx")


async def test__create_submission__converter_unavailable__raw_file_in_archive(
    test_app: AsyncClient, tmp_path: Path, mocker: MockerFixture
) -> None:
    project = await _setup_project(test_app, tmp_path)
    convert = mocker.patch.object(OfficeConvertManager, "convert_to_pdf", autospec=True, return_value=None)
    custom = await _upload_docx(test_app, project)

    record = await _create_submission(test_app, project, {_DOC_ID: True})

    assert convert.await_count == 2  # загрузка и упаковка; обе попытки без результата  # noqa: PLR2004
    assert not (Path(project["folder"]) / custom["stored_path"]).with_suffix(".pdf").exists()
    files = _archive(record)
    assert list(_by_ext(files, ".docx").values()) == [_DOCX]
    assert not _by_ext(files, ".pdf")


async def test__create_submission__decision_false__raw_file_without_converter_and_decision_remembered(
    test_app: AsyncClient, tmp_path: Path, mocker: MockerFixture
) -> None:
    project = await _setup_project(test_app, tmp_path)
    convert = mocker.patch.object(OfficeConvertManager, "convert_to_pdf", autospec=True, return_value=None)
    await _upload_docx(test_app, project)
    assert await _remembered(test_app, project) is None
    convert.reset_mock()
    convert.return_value = _PREVIEW

    record = await _create_submission(test_app, project, {_DOC_ID: False})

    convert.assert_not_awaited()
    files = _archive(record)
    assert list(_by_ext(files, ".docx").values()) == [_DOCX]
    assert not _by_ext(files, ".pdf")
    assert await _remembered(test_app, project) is False
    stored = json.loads((Path(project["folder"]) / ".hse-studio" / "project.json").read_text(encoding="utf-8"))
    custom_file = next(d for d in stored["documents"] if d["id"] == _DOC_ID)["custom_file"]
    assert custom_file["convert_to_pdf_at_package"] is False


@pytest.mark.parametrize("remembered", [True, False])
async def test__create_submission__no_decisions__uses_remembered_decision(
    test_app: AsyncClient, tmp_path: Path, mocker: MockerFixture, remembered: bool
) -> None:
    project = await _setup_project(test_app, tmp_path)
    convert = mocker.patch.object(OfficeConvertManager, "convert_to_pdf", autospec=True, return_value=None)
    await _upload_docx(test_app, project)
    await _create_submission(test_app, project, {_DOC_ID: remembered})
    convert.reset_mock()
    convert.return_value = _PREVIEW

    record = await _create_submission(test_app, project, None)

    files = _archive(record)
    if remembered:
        convert.assert_awaited_once()
        assert list(_by_ext(files, ".pdf").values()) == [_PREVIEW]
        assert not _by_ext(files, ".docx")
    else:
        convert.assert_not_awaited()
        assert list(_by_ext(files, ".docx").values()) == [_DOCX]
        assert not _by_ext(files, ".pdf")
    assert await _remembered(test_app, project) is remembered
