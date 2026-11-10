"""Версия на подписи как источник подписи документа (docs/design/signing-route.md, 12.3 и 12.4).

Версию на подписи пишут сценарии маршрута; здесь она записана в состояние подписей напрямую, как это сделала бы
отправка: план, фиксация и «С подписями» берут её, а не рабочую сборку, а «Подписывать текущую сборку» снимает её.
"""

from __future__ import annotations

import hashlib
import io
import shutil
from dataclasses import replace
from pathlib import Path

from hse_doc_studio.core.value_objects import PinnedPdf
from hse_doc_studio.infra.persistence.signature import JsonSignatureRepository
from hse_doc_studio.use_cases.signatures.signing_source import pinned_rel
from httpx import AsyncClient
from pypdf import PdfReader

from tests.integration.api.signatures.test_signature_plan import (
    _DOC,
    _image_author_detached_supervisor,
    _make_pdf,
    _plan,
    _project,
    _slots,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _text(pdf: bytes) -> str:
    return "".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)


async def _sent_then_edited(client: AsyncClient, root: Path) -> tuple[str, Path, PinnedPdf]:
    """Проект, документ отправлен на подпись (версия «sent»), затем автор пересобрал его («edited»)."""
    project_id, pdf = await _project(client, root / "proj")
    _make_pdf(pdf, "sent")
    await _image_author_detached_supervisor(client, project_id)
    folder = Path((await client.get(f"/api/v1/projects/{project_id}")).json()["folder"])
    source = folder / pinned_rel(_DOC)
    source.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(pdf, source)
    pinned = PinnedPdf(
        path=pinned_rel(_DOC),
        sha256=_sha(source),
        size=source.stat().st_size,
        pinned_at="2026-11-10T14:32:00+00:00",
        route_id="00000000-0000-4000-8000-000000000001",
        round=1,
    )
    repo = JsonSignatureRepository()
    repo.save_state(folder, replace(repo.get_state(folder), pinned={_DOC: pinned}))
    _make_pdf(pdf, "edited")
    return project_id, folder, pinned


def _doc(plan: dict) -> dict:
    (doc,) = [d for d in plan["docs"] if d["doc_id"] == _DOC]
    return doc


async def test__pinned__plan_shows_the_version_and_the_changes(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id, _, pinned = await _sent_then_edited(test_app, tmp_path)

    doc = _doc(await _plan(test_app, project_id))

    assert doc["pinned"] == {
        "sha256": pinned.sha256,
        "pinned_at": "2026-11-10T14:32:00+00:00",
        "route_id": "00000000-0000-4000-8000-000000000001",
        "round": 1,
    }
    assert doc["working_differs"] is True
    assert doc["built"] is True
    assert _slots({"docs": [doc]})["supervisor"]["reason"] == "not_frozen"


async def test__pinned__signed_preview_and_freeze_use_the_version_sent(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id, folder, pinned = await _sent_then_edited(test_app, tmp_path)
    base = f"/api/v1/projects/{project_id}/docs/{_DOC}"

    preview = await test_app.get(f"{base}/pdf/signed")
    frozen = await test_app.post(f"{base}/frozen")
    plan = await _plan(test_app, project_id)
    signatures = (await test_app.get(f"/api/v1/projects/{project_id}/signatures")).json()

    assert preview.status_code == 200, preview.text
    assert "sent" in _text(preview.content)
    assert "edited" not in _text(preview.content)
    assert frozen.status_code == 200, frozen.text
    frozen_pdf = (await test_app.get(f"{base}/frozen/pdf")).content
    assert "sent" in _text(frozen_pdf)
    # Фиксация сделана из версии на подписи: рабочая сборка новее, но фиксация не устарела.
    state = JsonSignatureRepository().get_state(folder)
    assert state.frozen[_DOC].source_sha256 == pinned.sha256
    assert _doc(plan)["frozen"]["outdated"] is None
    assert _doc(plan)["working_differs"] is True
    assert _slots(plan)["supervisor"]["reason"] == "no_signature_file"
    assert signatures["frozen"][_DOC]["stale"] is False


async def test__pinned__sign_the_current_build__unpins(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id, folder, pinned = await _sent_then_edited(test_app, tmp_path)
    base = f"/api/v1/projects/{project_id}/docs/{_DOC}"
    assert (await test_app.post(f"{base}/frozen")).status_code == 200

    unpinned = await test_app.delete(f"{base}/pinned")
    again = await test_app.delete(f"{base}/pinned")
    plan = await _plan(test_app, project_id)
    preview = await test_app.get(f"{base}/pdf/signed")

    assert unpinned.status_code == 204, unpinned.text
    assert again.status_code == 404
    assert not (folder / pinned.path).exists()
    assert JsonSignatureRepository().get_state(folder).pinned == {}
    doc = _doc(plan)
    assert (doc["pinned"], doc["working_differs"]) == (None, False)
    # Зафиксированный PDF и подписи остаются, но сделаны из прежней версии: план показывает их устаревшими.
    assert doc["frozen"]["outdated"] == "rebuilt"
    assert "edited" in _text(preview.content)


async def test__pinned__file_missing__freeze_explains_instead_of_signing_the_build(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    project_id, folder, pinned = await _sent_then_edited(test_app, tmp_path)
    (folder / pinned.path).unlink()

    resp = await test_app.post(f"/api/v1/projects/{project_id}/docs/{_DOC}/frozen")

    assert resp.status_code == 400
    assert "Версия на подписи не найдена" in resp.json()["detail"]
