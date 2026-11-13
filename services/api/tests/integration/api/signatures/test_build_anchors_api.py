"""Якоря источника подписи в `GET .../signatures` (docs/design/signing-route.md, 15.17.14).

Сборку здесь заменяет PDF рядом с исходником и `anchors.json` в `.build`, как их оставляет публикация сборки.
"""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import replace
from pathlib import Path, PurePosixPath

from hse_doc_studio.core.signatures.anchors import AnchorKind, BuildAnchor, BuildAnchors, encode_anchors
from hse_doc_studio.core.value_objects import PinnedPdf
from hse_doc_studio.infra.persistence.signature import JsonSignatureRepository
from hse_doc_studio.use_cases.signatures.signing_source import pinned_rel
from httpx import AsyncClient

from tests.integration.api.signatures.test_signature_plan import _DOC, _make_pdf, _project


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _anchors(sha: str, anchor_id: str = "supervisor") -> bytes:
    return encode_anchors(
        BuildAnchors(
            sha,
            (
                BuildAnchor(anchor_id, AnchorKind.sign, 1, 169.5, 186.9, 25.5),
                BuildAnchor(f"{anchor_id}.day", AnchorKind.date, 1, 40.0, 250.0, 8.0),
            ),
        )
    )


async def _built(client: AsyncClient, root: Path) -> tuple[str, Path, Path]:
    """Проект, собранный документ и путь, где его сборка оставляет якоря."""
    project_id, pdf = await _project(client, root / "proj")
    project = (await client.get(f"/api/v1/projects/{project_id}")).json()
    doc = (await client.get(f"/api/v1/projects/{project_id}/documents/{_DOC}")).json()
    source = PurePosixPath(doc["source_file"])
    anchors = Path(project["folder"]) / source.parent / ".build" / _DOC / f"{source.stem}.anchors.json"
    anchors.parent.mkdir(parents=True, exist_ok=True)
    return project_id, pdf, anchors


async def _state(client: AsyncClient, project_id: str) -> dict:
    response = await client.get(f"/api/v1/projects/{project_id}/signatures")
    assert response.status_code == 200, response.text
    return response.json()


async def test__signatures__anchors_of_the_current_build(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id, pdf, anchors = await _built(test_app, tmp_path)
    anchors.write_bytes(_anchors(_sha(pdf)))

    state = await _state(test_app, project_id)

    assert state["anchors"][_DOC] == {
        "build": _sha(pdf)[:16],
        "items": [
            {"id": "supervisor", "kind": "sign", "page": 1, "x_mm": 169.5, "y_mm": 186.9, "width_mm": 25.5},
            {"id": "supervisor.day", "kind": "date", "page": 1, "x_mm": 40.0, "y_mm": 250.0, "width_mm": 8.0},
        ],
        "problems": [],
    }
    # Документы без сборки: якоря неизвестны.
    assert all(value is None for doc_id, value in state["anchors"].items() if doc_id != _DOC)


async def test__signatures__anchors_of_another_pdf__unknown(test_app: AsyncClient, tmp_path: Path) -> None:
    # Сборка раннером прежней версии или PDF из локальной Студии: якоря в `.build` от прошлой сборки.
    project_id, pdf, anchors = await _built(test_app, tmp_path)
    anchors.write_bytes(_anchors(_sha(pdf)))
    _make_pdf(pdf, "rebuilt elsewhere")

    state = await _state(test_app, project_id)

    assert state["anchors"][_DOC] is None


async def test__signatures__broken_anchors_file__unknown(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id, _, anchors = await _built(test_app, tmp_path)
    anchors.write_text("{not json", encoding="utf-8")

    assert (await _state(test_app, project_id))["anchors"][_DOC] is None


async def test__signatures__pinned_version__anchors_of_the_version_sent(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id, pdf, anchors = await _built(test_app, tmp_path)
    project = (await test_app.get(f"/api/v1/projects/{project_id}")).json()
    folder = Path(project["folder"])
    source = folder / pinned_rel(_DOC)
    source.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(pdf, source)
    sent = _sha(source)
    source.with_name(f"{_DOC}.source.anchors.json").write_bytes(_anchors(sent, "author"))
    repo = JsonSignatureRepository()
    pinned = PinnedPdf(
        path=pinned_rel(_DOC),
        sha256=sent,
        size=source.stat().st_size,
        pinned_at="2026-11-14T10:00:00+00:00",
        route_id="00000000-0000-4000-8000-000000000001",
        round=1,
    )
    repo.save_state(folder, replace(repo.get_state(folder), pinned={_DOC: pinned}))
    # Рабочая сборка новее, у неё свои якоря: источник подписи всё равно версия на подписи.
    _make_pdf(pdf, "edited")
    anchors.write_bytes(_anchors(_sha(pdf)))

    state = await _state(test_app, project_id)
    unpinned = await test_app.delete(f"/api/v1/projects/{project_id}/docs/{_DOC}/pinned")
    after = await _state(test_app, project_id)

    assert state["anchors"][_DOC]["build"] == sent[:16]
    assert [item["id"] for item in state["anchors"][_DOC]["items"]] == ["author", "author.day"]
    assert unpinned.status_code == 204, unpinned.text
    assert not source.with_name(f"{_DOC}.source.anchors.json").exists()
    assert after["anchors"][_DOC]["build"] == _sha(pdf)[:16]
