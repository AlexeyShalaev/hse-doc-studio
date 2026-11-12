"""Пакет сдачи из версии на подписи (docs/design/signing-route.md, 12.8).

Версия на подписи записана в состояние подписей напрямую, как это сделала бы отправка маршрута, затем автор
пересобрал документ: пакет собирается из версии на подписи, а расхождение приходит предупреждением в ответе.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path

from httpx import AsyncClient
from pypdf import PdfReader

from tests.integration.api.signatures.test_pinned_version import _sent_then_edited
from tests.integration.api.signatures.test_signature_plan import _PNG_1PX, _PROFILE

_PDF = "Аннотация.pdf"


async def _image_supervisor(client: AsyncClient, project_id: str) -> None:
    """Руководитель подписывает картинкой: пакет собирается без фиксации и ЭП."""
    base = f"/api/v1/projects/{project_id}/signatures/slots/supervisor"
    resp = await client.post(f"{base}/png", files={"file": ("supervisor.png", _PNG_1PX, "image/png")})
    assert resp.status_code == 200, resp.text
    resp = await client.patch(f"{base}/config", json={"sign_mode": "image"})
    assert resp.status_code == 200, resp.text


async def _create(client: AsyncClient, project_id: str) -> dict:
    resp = await client.post(
        f"/api/v1/projects/{project_id}/submissions",
        json={"profile_id": _PROFILE, "items": [], "extra_items": [], "archive_format": "zip"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _pdf_text(record: dict) -> str:
    with zipfile.ZipFile(io.BytesIO(Path(record["output_path"]).read_bytes())) as zf:
        pdf = zf.read(_PDF)
    return "".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)


async def test__pinned_pack__working_build_moved_ahead__version_packed_and_warning_returned(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    project_id, folder, pinned = await _sent_then_edited(test_app, tmp_path)
    await _image_supervisor(test_app, project_id)
    doc = (await test_app.get(f"/api/v1/projects/{project_id}/documents/annotation")).json()
    working = folder / doc["output_file"]

    record = await _create(test_app, project_id)

    assert "sent" in _pdf_text(record)
    assert "edited" not in _pdf_text(record)
    [warning] = record["warnings"]
    assert warning == {
        "code": "changed_after_sent",
        "doc_id": "annotation",
        "sent_at": "2026-11-10T14:32:00+00:00",
        "file": _PDF,
        "message": (
            "Документ «Аннотация» изменён после отправки на подпись: в пакет попала версия на подписи от 10.11.2026"
        ),
        "pinned": {
            "sha256": pinned.sha256,
            "pinned_at": "2026-11-10T14:32:00+00:00",
            "route_id": "00000000-0000-4000-8000-000000000001",
            "round": 1,
        },
        "working_sha256": hashlib.sha256(working.read_bytes()).hexdigest(),
        "slot_id": None,
    }


async def test__pinned_pack__list_of_submissions__has_no_warnings(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id, _, _ = await _sent_then_edited(test_app, tmp_path)
    await _image_supervisor(test_app, project_id)
    await _create(test_app, project_id)

    listed = (await test_app.get(f"/api/v1/projects/{project_id}/submissions")).json()

    assert [r["warnings"] for r in listed] == [[]]
