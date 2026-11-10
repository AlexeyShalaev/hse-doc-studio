"""Метка подписи, которую не удалось нанести, видна пользователю отказом, и PDF без нее не появляется.

Фиксация, печатная копия «С подписями» и пакет сдачи отвечают 400 с текстом на языке интерфейса, который называет
слот (картинку загрузить заново) или страницу (сбой наложения), а зафиксированный файл не пишется и не меняется.
"""

from __future__ import annotations

import base64
from pathlib import Path

from httpx import AsyncClient
from pypdf import PageObject
from pytest_mock import MockerFixture
from reportlab.pdfgen import canvas

from tests.factories import project_api_payload

_PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
_BROKEN_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
_DOC = "annotation"
_SLOT = "author"
_EN = {"X-Interface-Language": "en"}


def _make_pdf(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path))
    c.drawString(100, 700, "annotation")
    c.save()


async def _project(client: AsyncClient, folder: Path, slots: tuple[str, ...] = (_SLOT,)) -> tuple[str, Path]:
    """Проект с собранной аннотацией и включенными картинками подписей на первой странице."""
    folder.mkdir(exist_ok=True)
    resp = await client.post("/api/v1/projects", json=project_api_payload(str(folder)))
    assert resp.status_code == 201, resp.text
    project = resp.json()
    project_id, project_folder = project["id"], Path(project["folder"])
    doc = (await client.get(f"/api/v1/projects/{project_id}/documents/{_DOC}")).json()
    _make_pdf(project_folder / doc["output_file"])
    for slot in slots:
        resp = await client.post(
            f"/api/v1/projects/{project_id}/signatures/slots/{slot}/png",
            files={"file": (f"{slot}.png", _PNG_1PX, "image/png")},
        )
        assert resp.status_code == 200, resp.text
        await _place(client, project_id, slot)
    return project_id, project_folder


async def _place(client: AsyncClient, project_id: str, slot: str, **fields: float) -> None:
    body = {"enabled": True, "page": 1, "x_mm": 20.0, "y_mm": 30.0, "width_mm": 40.0, **fields}
    resp = await client.patch(f"/api/v1/projects/{project_id}/signatures/placements/{_DOC}/{slot}", json=body)
    assert resp.status_code == 200, resp.text


def _png(folder: Path, slot: str = _SLOT) -> Path:
    return folder / ".hse-studio" / "signatures" / f"{slot}.png"


def _frozen_files(folder: Path) -> list[Path]:
    frozen_dir = folder / ".hse-studio" / "frozen"
    return sorted(frozen_dir.iterdir()) if frozen_dir.is_dir() else []


async def _frozen_state(client: AsyncClient, project_id: str) -> dict:
    resp = await client.get(f"/api/v1/projects/{project_id}/signatures")
    assert resp.status_code == 200, resp.text
    return resp.json().get("frozen", {})


async def test__api__freeze__broken_signature_png__400_naming_the_slot_and_no_frozen_file(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    project_id, folder = await _project(test_app, tmp_path / "proj")
    _png(folder).write_bytes(_BROKEN_PNG)

    resp = await test_app.post(f"/api/v1/projects/{project_id}/docs/{_DOC}/frozen")

    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert "«author»" in detail
    assert "Загрузите картинку подписи заново" in detail
    assert _frozen_files(folder) == []
    assert _DOC not in await _frozen_state(test_app, project_id)


async def test__api__freeze__broken_signature_png__english_interface__english_text(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    project_id, folder = await _project(test_app, tmp_path / "proj")
    _png(folder).write_bytes(_BROKEN_PNG)

    resp = await test_app.post(f"/api/v1/projects/{project_id}/docs/{_DOC}/frozen", headers=_EN)

    assert resp.status_code == 400, resp.text
    assert "slot «author»" in resp.json()["detail"]
    assert "Upload the signature image again" in resp.json()["detail"]


async def test__api__freeze__signature_png_deleted_from_disk__400_instead_of_freezing_without_it(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    project_id, folder = await _project(test_app, tmp_path / "proj")
    _png(folder).unlink()

    resp = await test_app.post(f"/api/v1/projects/{project_id}/docs/{_DOC}/frozen")

    assert resp.status_code == 400, resp.text
    assert "«author»" in resp.json()["detail"]
    assert _frozen_files(folder) == []


async def test__api__freeze__place_on_a_missing_page__400_and_no_frozen_file(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    project_id, folder = await _project(test_app, tmp_path / "proj")
    await _place(test_app, project_id, _SLOT, page=3)

    resp = await test_app.post(f"/api/v1/projects/{project_id}/docs/{_DOC}/frozen")

    assert resp.status_code == 400, resp.text
    assert "странице 3" in resp.json()["detail"]
    assert _frozen_files(folder) == []


async def test__api__refreeze__merge_failure__400_and_the_previous_frozen_copy_is_kept(
    test_app: AsyncClient, tmp_path: Path, mocker: MockerFixture
) -> None:
    project_id, folder = await _project(test_app, tmp_path / "proj")
    first = await test_app.post(f"/api/v1/projects/{project_id}/docs/{_DOC}/frozen")
    assert first.status_code == 200, first.text
    [frozen_file] = _frozen_files(folder)
    frozen_bytes = frozen_file.read_bytes()
    before = await _frozen_state(test_app, project_id)
    await _place(test_app, project_id, _SLOT, x_mm=60.0)
    mocker.patch.object(PageObject, "merge_page", side_effect=RuntimeError("content stream is read-only"))

    resp = await test_app.post(f"/api/v1/projects/{project_id}/docs/{_DOC}/frozen")

    assert resp.status_code == 400, resp.text
    assert "страницу 1" in resp.json()["detail"]
    assert _frozen_files(folder) == [frozen_file]
    assert frozen_file.read_bytes() == frozen_bytes
    assert (await _frozen_state(test_app, project_id))[_DOC]["sha256"] == before[_DOC]["sha256"]


async def test__api__freeze__normal_stamping__still_freezes(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id, folder = await _project(test_app, tmp_path / "proj")

    resp = await test_app.post(f"/api/v1/projects/{project_id}/docs/{_DOC}/frozen")

    assert resp.status_code == 200, resp.text
    assert [p.name for p in _frozen_files(folder)] == [f"{_DOC}.pdf"]


async def test__api__signed_pdf__broken_signature_png__400_naming_the_slot(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    project_id, folder = await _project(test_app, tmp_path / "proj")
    _png(folder).write_bytes(_BROKEN_PNG)

    resp = await test_app.get(f"/api/v1/projects/{project_id}/docs/{_DOC}/pdf/signed")

    assert resp.status_code == 400, resp.text
    assert "«author»" in resp.json()["detail"]


async def test__api__create_submission__broken_signature_png__400_naming_the_slot_and_no_pack(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    # КТ1 требует подписи автора и руководителя на аннотации; пакет штампует ее копию.
    project_id, folder = await _project(test_app, tmp_path / "proj", slots=("author", "supervisor"))
    _png(folder, "supervisor").write_bytes(_BROKEN_PNG)
    body = {"profile_id": "checkpoint-1", "items": [], "extra_items": [], "archive_format": "zip"}

    resp = await test_app.post(f"/api/v1/projects/{project_id}/submissions", json=body)

    assert resp.status_code == 400, resp.text
    assert "«supervisor»" in resp.json()["detail"]
    submissions = folder / "submissions"
    assert not submissions.is_dir() or list(submissions.iterdir()) == []
