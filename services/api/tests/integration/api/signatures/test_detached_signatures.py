from __future__ import annotations

import base64
import io
import shutil
import zipfile
from pathlib import Path

import pytest
from httpx import AsyncClient
from pypdf import PdfReader
from reportlab.pdfgen import canvas

from tests.factories import project_api_payload
from tests.unit.infra.signatures.gost_fixture import make_detached_cms, make_identity

_PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
_DOC = "annotation"
_SLOT = "supervisor"


def _make_pdf(path: Path, text: str = "annotation") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path))
    c.drawString(100, 700, text)
    c.save()


async def _project_with_pdf(client: AsyncClient, folder: Path) -> tuple[str, Path]:
    folder.mkdir(exist_ok=True)
    resp = await client.post("/api/v1/projects", json=project_api_payload(str(folder)))
    assert resp.status_code == 201, resp.text
    project = resp.json()
    doc = (await client.get(f"/api/v1/projects/{project['id']}/documents/{_DOC}")).json()
    output = doc["output_file"]
    pdf = Path(project["folder"]) / output
    _make_pdf(pdf)
    return project["id"], pdf


async def _enable_detached_slot(client: AsyncClient, project_id: str) -> None:
    resp = await client.patch(
        f"/api/v1/projects/{project_id}/signatures/slots/{_SLOT}/config",
        json={"sign_mode": "detached_text"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["sign_mode"] == "detached_text"
    resp = await client.patch(
        f"/api/v1/projects/{project_id}/signatures/placements/{_DOC}/{_SLOT}",
        json={"enabled": True, "page": 1, "x_mm": 20.0, "y_mm": 30.0, "width_mm": 70.0},
    )
    assert resp.status_code == 200, resp.text


async def _freeze(client: AsyncClient, project_id: str) -> dict:
    resp = await client.post(f"/api/v1/projects/{project_id}/docs/{_DOC}/frozen")
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _frozen_bytes(client: AsyncClient, project_id: str) -> bytes:
    resp = await client.get(f"/api/v1/projects/{project_id}/docs/{_DOC}/frozen/pdf")
    assert resp.status_code == 200, resp.text
    return resp.content


def _attach(client: AsyncClient, project_id: str, content: bytes, name: str = "sig.p7s"):  # noqa: ANN202
    return client.post(
        f"/api/v1/projects/{project_id}/docs/{_DOC}/detached/{_SLOT}",
        files={"file": (name, content, "application/octet-stream")},
    )


async def test__api__freeze__prints_caption_and_reports_sha256(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id, _ = await _project_with_pdf(test_app, tmp_path / "proj")
    await _enable_detached_slot(test_app, project_id)

    body = await _freeze(test_app, project_id)

    assert len(body["frozen"]["sha256"]) == 64
    assert body["frozen"]["stale"] is False
    frozen = await _frozen_bytes(test_app, project_id)
    text = PdfReader(io.BytesIO(frozen)).pages[0].extract_text()
    assert "открепленной электронной подписи" in text.replace("\n", " ")
    state = (await test_app.get(f"/api/v1/projects/{project_id}/signatures")).json()
    assert state["frozen"][_DOC]["sha256"] == body["frozen"]["sha256"]


async def test__api__attach_gost_signature__verified_for_frozen_pdf(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id, _ = await _project_with_pdf(test_app, tmp_path / "proj")
    await _enable_detached_slot(test_app, project_id)
    await _freeze(test_app, project_id)
    sig = make_detached_cms(make_identity("Петрова Анна Сергеевна"), await _frozen_bytes(test_app, project_id))

    resp = await _attach(test_app, project_id, sig)

    assert resp.status_code == 200, resp.text
    out = resp.json()["signature"]
    assert out["verdict"] == "valid"
    assert out["format"] == "cms"
    assert out["signer"] == "Петрова Анна Сергеевна"
    assert "chain_untrusted_root" in out["notes"]
    state = (await test_app.get(f"/api/v1/projects/{project_id}/signatures")).json()
    stored = state["detached"][_DOC][_SLOT]
    assert stored["verdict"] == "valid"
    assert stored["current"] is True


async def test__api__attach_signature_of_another_file__stored_as_invalid(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id, _ = await _project_with_pdf(test_app, tmp_path / "proj")
    await _enable_detached_slot(test_app, project_id)
    await _freeze(test_app, project_id)

    resp = await _attach(test_app, project_id, make_detached_cms(make_identity(), b"some other file"))

    assert resp.status_code == 200, resp.text
    assert resp.json()["signature"]["verdict"] == "invalid"


async def test__api__attach_signature__not_a_signature__400(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id, _ = await _project_with_pdf(test_app, tmp_path / "proj")
    await _enable_detached_slot(test_app, project_id)
    await _freeze(test_app, project_id)

    resp = await _attach(test_app, project_id, b"just some text")

    assert resp.status_code == 400, resp.text


async def test__api__attach_signature__without_freeze__400(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id, _ = await _project_with_pdf(test_app, tmp_path / "proj")
    await _enable_detached_slot(test_app, project_id)

    resp = await _attach(test_app, project_id, make_detached_cms(make_identity(), b"x"))

    assert resp.status_code == 400, resp.text


async def test__api__rebuild_after_freeze__marks_signature_stale_and_blocks_new_ones(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    project_id, pdf = await _project_with_pdf(test_app, tmp_path / "proj")
    await _enable_detached_slot(test_app, project_id)
    await _freeze(test_app, project_id)
    sig = make_detached_cms(make_identity(), await _frozen_bytes(test_app, project_id))
    assert (await _attach(test_app, project_id, sig)).status_code == 200

    _make_pdf(pdf, "annotation, rebuilt")

    state = (await test_app.get(f"/api/v1/projects/{project_id}/signatures")).json()
    assert state["frozen"][_DOC]["stale"] is True
    assert state["detached"][_DOC][_SLOT]["current"] is False
    assert (await _attach(test_app, project_id, sig)).status_code == 400

    # Freezing again drops the signature that covered the old bytes.
    again = await _freeze(test_app, project_id)
    assert again["dropped_slots"] == [_SLOT]
    state = (await test_app.get(f"/api/v1/projects/{project_id}/signatures")).json()
    assert state["detached"] == {}


async def test__api__delete_signature_and_unfreeze(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id, _ = await _project_with_pdf(test_app, tmp_path / "proj")
    await _enable_detached_slot(test_app, project_id)
    await _freeze(test_app, project_id)
    sig = make_detached_cms(make_identity(), await _frozen_bytes(test_app, project_id))
    await _attach(test_app, project_id, sig)

    resp = await test_app.delete(f"/api/v1/projects/{project_id}/docs/{_DOC}/detached/{_SLOT}")
    assert resp.status_code == 204
    resp = await test_app.delete(f"/api/v1/projects/{project_id}/docs/{_DOC}/frozen")
    assert resp.status_code == 204
    state = (await test_app.get(f"/api/v1/projects/{project_id}/signatures")).json()
    assert state["frozen"] == {}
    assert state["detached"] == {}


async def test__api__signing_package__request_contains_pdf_and_instructions(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    project_id, _ = await _project_with_pdf(test_app, tmp_path / "proj")
    await _enable_detached_slot(test_app, project_id)
    frozen = await _freeze(test_app, project_id)

    resp = await test_app.get(f"/api/v1/projects/{project_id}/docs/{_DOC}/signing-package?mode=request")

    assert resp.status_code == 200, resp.text
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = zf.namelist()
        assert any(n.endswith(".pdf") for n in names)
        assert "README.txt" in names
        assert frozen["frozen"]["sha256"] in zf.read("SHA256SUMS.txt").decode()


@pytest.mark.skipif(shutil.which("gpg") is None, reason="gpg is not installed")
async def test__api__sign_in_studio__openpgp_key_signs_and_verifies(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id, _ = await _project_with_pdf(test_app, tmp_path / "proj")
    await _enable_detached_slot(test_app, project_id)
    await _freeze(test_app, project_id)
    resp = await test_app.post(
        "/api/v1/signing-identities/openpgp/generate",
        json={"name": "Иван Иванов", "email": "ivan@example.org"},
    )
    assert resp.status_code == 201, resp.text
    identity = resp.json()
    assert identity["kind"] == "openpgp"
    assert identity["protected"] is False

    resp = await test_app.post(
        f"/api/v1/projects/{project_id}/docs/{_DOC}/detached/{_SLOT}/sign",
        json={"identity_id": identity["id"]},
    )

    assert resp.status_code == 200, resp.text
    sig = resp.json()["signature"]
    assert sig["verdict"] == "valid"
    assert sig["format"] == "openpgp"
    assert sig["origin"] == "studio"
    assert sig["signer_id"] == identity["fingerprint"]

    resp = await test_app.get(f"/api/v1/projects/{project_id}/docs/{_DOC}/signing-package?mode=signed")
    assert resp.status_code == 200, resp.text
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = zf.namelist()
        assert any(n.endswith(".asc") and ".pdf" not in n.split(".")[-1] for n in names)
        assert any(n.startswith("public-key.") for n in names)
        assert "gpg --verify" in zf.read("README.txt").decode()

    resp = await test_app.get(f"/api/v1/signing-identities/{identity['id']}/public-key")
    assert resp.status_code == 200
    assert b"BEGIN PGP PUBLIC KEY BLOCK" in resp.content

    resp = await test_app.delete(f"/api/v1/signing-identities/{identity['id']}")
    assert resp.status_code == 204
    keys = (await test_app.get("/api/v1/signing-identities/openpgp/keys")).json()
    assert identity["fingerprint"] not in [k["fingerprint"] for k in keys["keys"]]


async def test__api__submission__detached_slot_requires_signature_then_packages_frozen_pdf(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    project_id, _ = await _project_with_pdf(test_app, tmp_path / "proj")
    await _enable_detached_slot(test_app, project_id)
    resp = await test_app.post(
        f"/api/v1/projects/{project_id}/signatures/slots/author/png",
        files={"file": ("sig.png", _PNG_1PX, "image/png")},
    )
    assert resp.status_code == 200, resp.text
    resp = await test_app.patch(
        f"/api/v1/projects/{project_id}/signatures/placements/{_DOC}/author", json={"enabled": True}
    )
    assert resp.status_code == 200, resp.text
    body = {"profile_id": "checkpoint-1", "items": [], "extra_items": [], "archive_format": "zip"}

    # No signature file yet: the gate refuses the package.
    resp = await test_app.post(f"/api/v1/projects/{project_id}/submissions", json=body)
    assert resp.status_code == 400, resp.text

    await _freeze(test_app, project_id)
    frozen_bytes = await _frozen_bytes(test_app, project_id)
    assert (await _attach(test_app, project_id, make_detached_cms(make_identity(), frozen_bytes))).status_code == 200

    resp = await test_app.post(f"/api/v1/projects/{project_id}/submissions", json=body)
    assert resp.status_code == 201, resp.text
    resp = await test_app.get(f"/api/v1/projects/{project_id}/submissions/{resp.json()['id']}/download")
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = zf.namelist()
        pdfs = [n for n in names if n.endswith(".pdf")]
        sigs = [n for n in names if n.endswith(".p7s")]
        assert len(sigs) == 1
        assert any(zf.read(n) == frozen_bytes for n in pdfs)
        assert any(n.endswith(".README.txt") for n in names)


async def test__api__refreeze_of_unchanged_document__keeps_signature(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id, _ = await _project_with_pdf(test_app, tmp_path / "proj")
    await _enable_detached_slot(test_app, project_id)
    first = await _freeze(test_app, project_id)
    sig = make_detached_cms(make_identity(), await _frozen_bytes(test_app, project_id))
    assert (await _attach(test_app, project_id, sig)).status_code == 200

    again = await _freeze(test_app, project_id)

    assert again["frozen"]["sha256"] == first["frozen"]["sha256"]
    assert again["dropped_slots"] == []
    state = (await test_app.get(f"/api/v1/projects/{project_id}/signatures")).json()
    assert state["detached"][_DOC][_SLOT]["current"] is True
