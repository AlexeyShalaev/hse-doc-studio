"""План подписей по профилю сдачи: счётчик «k из n» и подсказка, чего не хватает (docs/design/signature-plan.md)."""

from __future__ import annotations

import base64
import json
from pathlib import Path

from httpx import AsyncClient
from reportlab.pdfgen import canvas

from tests.factories import project_api_payload
from tests.unit.infra.signatures.gost_fixture import make_detached_cms, make_identity

_PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
_DOC = "annotation"
# КТ1 исследовательской ВКР: аннотацию подписывают автор и руководитель.
_PROFILE = "checkpoint-1"


def _make_pdf(path: Path, text: str = "annotation") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path))
    c.drawString(100, 700, text)
    c.save()


async def _project(client: AsyncClient, folder: Path) -> tuple[str, Path]:
    folder.mkdir(exist_ok=True)
    payload = project_api_payload(str(folder))
    payload["supervisor"] = {"name": "Петров Пётр Петрович", "role": "university"}
    resp = await client.post("/api/v1/projects", json=payload)
    assert resp.status_code == 201, resp.text
    project = resp.json()
    doc = (await client.get(f"/api/v1/projects/{project['id']}/documents/{_DOC}")).json()
    pdf = Path(project["folder"]) / doc["output_file"]
    _make_pdf(pdf)
    return project["id"], pdf


async def _place(client: AsyncClient, project_id: str, slot: str, y_mm: float) -> None:
    resp = await client.patch(
        f"/api/v1/projects/{project_id}/signatures/placements/{_DOC}/{slot}",
        json={"enabled": True, "page": 1, "x_mm": 20.0, "y_mm": y_mm, "width_mm": 60.0},
    )
    assert resp.status_code == 200, resp.text


async def _image_author_detached_supervisor(client: AsyncClient, project_id: str) -> None:
    resp = await client.post(
        f"/api/v1/projects/{project_id}/signatures/slots/author/png",
        files={"file": ("author.png", _PNG_1PX, "image/png")},
    )
    assert resp.status_code == 200, resp.text
    await _place(client, project_id, "author", 30.0)
    resp = await client.patch(
        f"/api/v1/projects/{project_id}/signatures/slots/supervisor/config", json={"sign_mode": "detached_text"}
    )
    assert resp.status_code == 200, resp.text
    await _place(client, project_id, "supervisor", 80.0)


async def _plan(client: AsyncClient, project_id: str) -> dict:
    resp = await client.get(f"/api/v1/projects/{project_id}/signature-plan", params={"profile_id": _PROFILE})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _slots(plan: dict) -> dict[str, dict]:
    return {s["slot_id"]: s for doc in plan["docs"] for s in doc["slots"]}


async def test__plan__frozen_without_signature_file__counts_and_explains(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id, _ = await _project(test_app, tmp_path / "proj")
    await _image_author_detached_supervisor(test_app, project_id)
    resp = await test_app.post(f"/api/v1/projects/{project_id}/docs/{_DOC}/frozen")
    assert resp.status_code == 200, resp.text

    plan = await _plan(test_app, project_id)

    assert (plan["total"], plan["signed"]) == (2, 1)
    slots = _slots(plan)
    assert slots["author"]["status"] == "signed"
    assert slots["author"]["crypto"] is False
    assert slots["author"]["method"] == "image"
    supervisor = slots["supervisor"]
    assert (supervisor["status"], supervisor["reason"]) == ("pending", "no_signature_file")
    assert supervisor["crypto"] is True
    assert ".asc" in supervisor["hint"]
    assert supervisor["signer"] == {"persona": "supervisor", "name": "Петров Пётр Петрович"}
    assert supervisor["required_by"] == [_PROFILE]


async def test__plan__signature_attached__all_signed_with_check(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id, _ = await _project(test_app, tmp_path / "proj")
    await _image_author_detached_supervisor(test_app, project_id)
    await test_app.post(f"/api/v1/projects/{project_id}/docs/{_DOC}/frozen")
    frozen = (await test_app.get(f"/api/v1/projects/{project_id}/docs/{_DOC}/frozen/pdf")).content
    sig = make_detached_cms(make_identity("Петров Пётр Петрович"), frozen)
    resp = await test_app.post(
        f"/api/v1/projects/{project_id}/docs/{_DOC}/detached/supervisor",
        files={"file": ("sig.p7s", sig, "application/octet-stream")},
    )
    assert resp.status_code == 200, resp.text

    plan = await _plan(test_app, project_id)

    assert (plan["total"], plan["signed"], plan["crypto_total"], plan["crypto_signed"]) == (2, 2, 1, 1)
    check = _slots(plan)["supervisor"]["check"]
    assert (check["format"], check["verdict"], check["signer"]) == ("cms", "valid", "Петров Пётр Петрович")


async def test__plan__rebuilt_after_signing__signature_stale(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id, pdf = await _project(test_app, tmp_path / "proj")
    await _image_author_detached_supervisor(test_app, project_id)
    await test_app.post(f"/api/v1/projects/{project_id}/docs/{_DOC}/frozen")
    frozen = (await test_app.get(f"/api/v1/projects/{project_id}/docs/{_DOC}/frozen/pdf")).content
    await test_app.post(
        f"/api/v1/projects/{project_id}/docs/{_DOC}/detached/supervisor",
        files={"file": ("sig.p7s", make_detached_cms(make_identity(), frozen), "application/octet-stream")},
    )
    _make_pdf(pdf, "annotation, second edition")

    plan = await _plan(test_app, project_id)

    supervisor = _slots(plan)["supervisor"]
    assert (supervisor["status"], supervisor["reason"]) == ("stale", "rebuilt")
    assert plan["docs"][0]["frozen"]["outdated"] == "rebuilt"


async def test__plan__not_frozen__pending_not_frozen(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id, _ = await _project(test_app, tmp_path / "proj")
    await _image_author_detached_supervisor(test_app, project_id)

    plan = await _plan(test_app, project_id)

    assert _slots(plan)["supervisor"]["reason"] == "not_frozen"


async def test__plan__project_wide_without_profile__lists_required_pairs(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id, _ = await _project(test_app, tmp_path / "proj")

    resp = await test_app.get(f"/api/v1/projects/{project_id}/signature-plan", params={"doc_id": _DOC})

    assert resp.status_code == 200, resp.text
    slots = _slots(resp.json())
    assert {"author", "supervisor"} <= set(slots)
    assert _PROFILE in slots["supervisor"]["required_by"]


async def test__plan__local_actor__author_slot_is_mine(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id, _ = await _project(test_app, tmp_path / "proj")
    await _image_author_detached_supervisor(test_app, project_id)

    plan = await _plan(test_app, project_id)

    slots = _slots(plan)
    assert slots["author"]["is_mine"] is True
    assert slots["supervisor"]["is_mine"] is False
    assert plan["waiting_for_me"] == 0


async def test__plan__unknown_profile__404(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id, _ = await _project(test_app, tmp_path / "proj")

    resp = await test_app.get(f"/api/v1/projects/{project_id}/signature-plan", params={"profile_id": "nope"})

    assert resp.status_code == 404


async def test__signatures_json__embedded_section_round_trips(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id, _ = await _project(test_app, tmp_path / "proj")
    await _image_author_detached_supervisor(test_app, project_id)
    folder = Path((await test_app.get(f"/api/v1/projects/{project_id}")).json()["folder"])
    path = folder / ".hse-studio" / "signatures.json"
    data = json.loads(path.read_text(encoding="utf-8"))

    assert data["embedded"] == {}
