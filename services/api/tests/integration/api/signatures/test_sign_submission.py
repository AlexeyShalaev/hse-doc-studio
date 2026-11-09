"""Смешанные подписи на одном PDF и «Подписать комплект» (docs/design/signature-plan.md, разделы 4, 5 и 7).

Каждая проверка подписей здесь внешняя: gpg с отдельным GNUPGHOME и pyHanko над файлами, которые отдаёт API, а не
вердикты Студии.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import shutil
import subprocess
import tempfile
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from asn1crypto import cms
from hse_doc_studio.core.signatures.stamps import legacy_stamps_digest, stamps_for_doc
from hse_doc_studio.infra.persistence.signature import JsonSignatureRepository
from httpx import AsyncClient
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign.validation import async_validate_detached_cms, async_validate_pdf_signature
from pyhanko_certvalidator import ValidationContext
from reportlab.pdfgen import canvas

from tests.factories import project_api_payload
from tests.unit.infra.signatures.gost_fixture import make_detached_cms, make_identity

_PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
_DOC = "annotation"
_PROFILE = "checkpoint-1"
_GPG = pytest.mark.skipif(shutil.which("gpg") is None, reason="gpg is not installed")


def _make_pdf(path: Path, text: str = "annotation") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path))
    c.drawString(100, 700, text)
    c.save()


class Api:
    def __init__(self, client: AsyncClient, project_id: str, pdf: Path, folder: Path) -> None:
        self.client = client
        self.pid = project_id
        self.pdf = pdf
        self.folder = folder

    @property
    def base(self) -> str:
        return f"/api/v1/projects/{self.pid}"

    async def mode(self, slot: str, mode: str, identity_id: str | None = None) -> None:
        resp = await self.client.patch(
            f"{self.base}/signatures/slots/{slot}/config", json={"sign_mode": mode, "signing_identity_id": identity_id}
        )
        assert resp.status_code == 200, resp.text
        y = 40.0 if slot == "author" else 90.0
        resp = await self.client.patch(
            f"{self.base}/signatures/placements/{_DOC}/{slot}",
            json={"enabled": True, "page": 1, "x_mm": 20.0, "y_mm": y, "width_mm": 60.0},
        )
        assert resp.status_code == 200, resp.text

    async def png(self, slot: str) -> None:
        resp = await self.client.post(
            f"{self.base}/signatures/slots/{slot}/png", files={"file": ("s.png", _PNG_1PX, "image/png")}
        )
        assert resp.status_code == 200, resp.text

    async def plate_from_key(self, slot: str, identity_id: str) -> None:
        resp = await self.client.put(f"{self.base}/signatures/slots/{slot}/signer", json={"identity_id": identity_id})
        assert resp.status_code == 200, resp.text

    async def preview(self, **body: object) -> dict:
        resp = await self.client.post(f"{self.base}/signature-plan/sign-preview", json={"profile_id": _PROFILE, **body})
        assert resp.status_code == 200, resp.text
        return resp.json()

    async def sign(self, expected: dict | None = None, **body: object) -> dict:
        preview = await self.preview(**{k: v for k, v in body.items() if k == "identity_id"})
        tokens = expected if expected is not None else {d["doc_id"]: d["token"] for d in preview["docs"]}
        resp = await self.client.post(
            f"{self.base}/signature-plan/sign", json={"profile_id": _PROFILE, "expected": tokens, **body}
        )
        assert resp.status_code == 200, resp.text
        return resp.json()

    async def plan(self) -> dict[str, dict]:
        resp = await self.client.get(f"{self.base}/signature-plan", params={"profile_id": _PROFILE})
        assert resp.status_code == 200, resp.text
        return {s["slot_id"]: s for d in resp.json()["docs"] for s in d["slots"]}

    def state(self) -> dict:
        return json.loads((self.folder / ".hse-studio" / "signatures.json").read_text(encoding="utf-8"))

    def frozen_bytes(self) -> bytes:
        return (self.folder / self.state()["frozen"][_DOC]["path"]).read_bytes()

    def final_bytes(self) -> bytes:
        frozen = self.state()["frozen"][_DOC]
        return (self.folder / (frozen.get("signed_path") or frozen["path"])).read_bytes()

    def detached(self, slot: str) -> bytes:
        return (self.folder / self.state()["detached"][_DOC][slot]["file"]).read_bytes()


async def _api(client: AsyncClient, tmp_path: Path) -> Api:
    folder = tmp_path / "proj"
    folder.mkdir()
    payload = project_api_payload(str(folder))
    payload["supervisor"] = {"name": "Петров Пётр Петрович", "role": "university"}
    resp = await client.post("/api/v1/projects", json=payload)
    assert resp.status_code == 201, resp.text
    project = resp.json()
    doc = (await client.get(f"/api/v1/projects/{project['id']}/documents/{_DOC}")).json()
    pdf = Path(project["folder"]) / doc["output_file"]
    _make_pdf(pdf)
    return Api(client, project["id"], pdf, Path(project["folder"]))


async def _x509_key(client: AsyncClient, cn: str) -> str:
    resp = await client.post("/api/v1/signing-identities/self-signed", json={"label": cn, "subject_cn": cn})
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


async def _pgp_key(client: AsyncClient, name: str, passphrase: str = "") -> dict:
    resp = await client.post(
        "/api/v1/signing-identities/openpgp/generate",
        json={"name": name, "email": "student@example.org", "passphrase": passphrase},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture
def gnupg_home() -> Iterator[Path]:
    # Короткий путь: сокеты gpg-agent и keyboxd не помещаются в длинный tmp_path.
    home = Path(tempfile.mkdtemp(prefix="g", dir="/tmp"))
    home.chmod(0o700)
    yield home
    subprocess.run(["gpgconf", "--homedir", str(home), "--kill", "all"], check=False, capture_output=True)  # noqa: S607
    shutil.rmtree(home, ignore_errors=True)


async def _gpg_verify(client: AsyncClient, home: Path, key_id: str, signature: bytes, data: bytes) -> bool:
    pub = (await client.get(f"/api/v1/signing-identities/{key_id}/public-key")).content
    work = home / "w"
    work.mkdir(exist_ok=True)
    (work / "pub.asc").write_bytes(pub)
    (work / "doc.pdf").write_bytes(data)
    (work / "doc.pdf.asc").write_bytes(signature)
    gpg = ["gpg", "--homedir", str(home), "--batch"]
    subprocess.run([*gpg, "--import", str(work / "pub.asc")], check=True, capture_output=True)  # noqa: S603
    done = subprocess.run(  # noqa: S603
        [*gpg, "--verify", str(work / "doc.pdf.asc"), str(work / "doc.pdf")], capture_output=True, check=False
    )
    return done.returncode == 0


async def _cms_intact(signature: bytes, data: bytes) -> bool:
    signed_data = cms.ContentInfo.load(signature)["content"]
    status = await async_validate_detached_cms(data, signed_data)
    return bool(status.intact and status.valid)


async def _pades_fields(data: bytes, tmp_path: Path) -> list[tuple[str, bool]]:
    path = tmp_path / "final.pdf"
    path.write_bytes(data)
    result: list[tuple[str, bool]] = []
    with path.open("rb") as fh:
        reader = PdfFileReader(fh, strict=False)
        for sig in reader.embedded_regular_signatures:
            cert = sig.signer_cert
            status = await async_validate_pdf_signature(
                sig, ValidationContext(trust_roots=[cert], allow_fetching=False)
            )
            result.append((sig.field_name, bool(status.intact and status.valid and status.docmdp_ok is not False)))
    return result


# --- смеси на одном PDF -------------------------------------------------------------------------------------------


@_GPG
async def test__mix__detached_openpgp_and_image__both_count_and_gpg_verifies(
    test_app: AsyncClient, tmp_path: Path, gnupg_home: Path
) -> None:
    api = await _api(test_app, tmp_path)
    key = await _pgp_key(test_app, "Иван Иванов")
    await api.mode("author", "detached_text")
    await api.png("supervisor")
    await api.mode("supervisor", "image")

    preview = await api.preview()
    (doc,) = preview["docs"]
    assert doc["needs_freeze"] is True
    assert [(s["slot_id"], s["action"]) for s in doc["slots"]] == [("author", "sign")]
    assert preview["key"]["auto"] is True
    result = await api.sign()

    assert [r["ok"] for r in result["results"]] == [True]
    assert (result["plan"]["total"], result["plan"]["signed"]) == (2, 2)
    plan = await api.plan()
    assert (plan["supervisor"]["method"], plan["supervisor"]["crypto"]) == ("image", False)
    assert plan["author"]["check"]["format"] == "openpgp"
    assert await _gpg_verify(test_app, gnupg_home, key["id"], api.detached("author"), api.frozen_bytes())


async def test__mix__detached_and_pades__pades_first__both_stay_valid(test_app: AsyncClient, tmp_path: Path) -> None:
    api = await _api(test_app, tmp_path)
    student = await _x509_key(test_app, "Ivan Ivanov")
    supervisor = await _x509_key(test_app, "Petr Petrov")
    await api.mode("author", "detached_text")
    await api.png("supervisor")
    await api.mode("supervisor", "image_crypto")
    await api.plate_from_key("supervisor", supervisor)
    await api.plate_from_key("author", student)

    first = await api.sign(identity_id=supervisor)
    second = await api.sign(identity_id=student)

    assert [r["ok"] for r in first["results"] if r["slot_id"] == "supervisor"] == [True]
    assert [r["ok"] for r in second["results"] if r["slot_id"] == "author"] == [True]
    final, base = api.final_bytes(), api.frozen_bytes()
    assert final.startswith(base)
    assert await _pades_fields(final, tmp_path) == [("Sig_supervisor", True)]
    assert await _cms_intact(api.detached("author"), base)
    plan = await api.plan()
    assert (plan["author"]["status"], plan["supervisor"]["status"]) == ("signed", "signed")


async def test__mix__detached_then_pades__detached_still_covers_frozen(test_app: AsyncClient, tmp_path: Path) -> None:
    api = await _api(test_app, tmp_path)
    student = await _x509_key(test_app, "Ivan Ivanov")
    supervisor = await _x509_key(test_app, "Petr Petrov")
    await api.mode("author", "detached_text")
    await api.mode("supervisor", "crypto_invisible")
    await api.plate_from_key("supervisor", supervisor)
    await api.plate_from_key("author", student)

    await api.sign(identity_id=student)
    detached_before = api.detached("author")
    await api.sign(identity_id=supervisor)

    assert api.detached("author") == detached_before
    assert await _cms_intact(api.detached("author"), api.frozen_bytes())
    assert await _pades_fields(api.final_bytes(), tmp_path) == [("Sig_supervisor", True)]


@_GPG
async def test__mix__two_detached_formats__openpgp_and_gost_cms(
    test_app: AsyncClient, tmp_path: Path, gnupg_home: Path
) -> None:
    api = await _api(test_app, tmp_path)
    key = await _pgp_key(test_app, "Иван Иванов")
    await api.mode("author", "detached_text")
    await api.mode("supervisor", "detached_text")
    await api.sign()
    # Руководитель подписал зафиксированный PDF в КриптоПро (ГОСТ) и прислал файл: его прикладывает автор.
    resp = await test_app.post(
        f"{api.base}/docs/{_DOC}/detached/supervisor",
        files={"file": ("sig.sig", make_detached_cms(make_identity("Петров"), api.frozen_bytes()), "application/x")},
    )
    assert resp.status_code == 200, resp.text

    plan = await api.plan()

    assert (plan["author"]["check"]["format"], plan["supervisor"]["check"]["format"]) == ("openpgp", "cms")
    assert all(s["status"] == "signed" for s in plan.values())
    assert await _gpg_verify(test_app, gnupg_home, key["id"], api.detached("author"), api.frozen_bytes())


async def test__mix__pades_and_pades__second_appends_and_first_stays_valid(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    api = await _api(test_app, tmp_path)
    student = await _x509_key(test_app, "Ivan Ivanov")
    supervisor = await _x509_key(test_app, "Petr Petrov")
    await api.png("author")
    await api.png("supervisor")
    await api.mode("author", "image_crypto")
    await api.mode("supervisor", "image_crypto")
    await api.plate_from_key("author", student)
    await api.plate_from_key("supervisor", supervisor)

    await api.sign(identity_id=student)
    after_first = api.final_bytes()
    await api.sign(identity_id=supervisor)

    final = api.final_bytes()
    assert final.startswith(after_first)
    assert final.startswith(api.frozen_bytes())
    assert await _pades_fields(final, tmp_path) == [("Sig_author", True), ("Sig_supervisor", True)]


# --- права и подписант ------------------------------------------------------------------------------------------


async def test__foreign_slot__plate_names_other_signer__studio_sign_refused(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    api = await _api(test_app, tmp_path)
    key = await _x509_key(test_app, "Ivan Ivanov")
    await api.mode("supervisor", "detached_text")
    resp = await test_app.post(
        f"{api.base}/signatures/slots/supervisor/signer/file",
        files={"file": ("cert.cer", make_identity("Петров Пётр").cert_der, "application/pkix-cert")},
    )
    assert resp.status_code == 200, resp.text
    resp = await test_app.post(f"{api.base}/docs/{_DOC}/frozen")
    assert resp.status_code == 200, resp.text

    resp = await test_app.post(f"{api.base}/docs/{_DOC}/detached/supervisor/sign", json={"identity_id": key})

    assert resp.status_code == 403, resp.text
    assert "плашке" in resp.json()["detail"] or "plate" in resp.json()["detail"]
    preview = await api.preview(identity_id=key)
    assert all(s["slot_id"] != "supervisor" for d in preview["docs"] for s in d["slots"])


async def test__pades_with_openpgp_key__rejected_when_configuring_slot(test_app: AsyncClient, tmp_path: Path) -> None:
    if shutil.which("gpg") is None:
        pytest.skip("gpg is not installed")
    api = await _api(test_app, tmp_path)
    key = await _pgp_key(test_app, "Иван Иванов")

    resp = await test_app.patch(
        f"{api.base}/signatures/slots/author/config",
        json={"sign_mode": "image_crypto", "signing_identity_id": key["id"]},
    )

    assert resp.status_code == 400, resp.text
    assert "X.509" in resp.json()["detail"]


# --- пересборка, подтверждения и пароль ---------------------------------------------------------------------------


async def test__rebuild_after_partial_signing__needs_confirmation_and_fresh_tokens(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    api = await _api(test_app, tmp_path)
    student = await _x509_key(test_app, "Ivan Ivanov")
    supervisor = await _x509_key(test_app, "Petr Petrov")
    await api.mode("author", "detached_text")
    await api.mode("supervisor", "detached_text")
    await api.plate_from_key("author", student)
    await api.plate_from_key("supervisor", supervisor)
    await api.sign(identity_id=student)
    stale_tokens = {d["doc_id"]: d["token"] for d in (await api.preview(identity_id=supervisor))["docs"]}
    _make_pdf(api.pdf, "annotation, second edition")

    preview = await api.preview(identity_id=supervisor)
    (doc,) = preview["docs"]
    assert doc["needs_freeze"] is True
    assert [r["slot_id"] for r in doc["resets"]] == ["author"]
    assert (await api.plan())["author"]["status"] == "stale"
    stale = await test_app.post(
        f"{api.base}/signature-plan/sign",
        json={"profile_id": _PROFILE, "identity_id": supervisor, "expected": stale_tokens, "confirm_reset": True},
    )
    assert stale.status_code == 409, stale.text
    assert stale.json()["detail"]["code"] == "changed"
    fresh = {doc["doc_id"]: doc["token"]}
    unconfirmed = await test_app.post(
        f"{api.base}/signature-plan/sign",
        json={"profile_id": _PROFILE, "identity_id": supervisor, "expected": fresh},
    )
    assert unconfirmed.status_code == 409, unconfirmed.text
    assert unconfirmed.json()["detail"]["code"] == "reset_required"

    done = await api.sign(expected=fresh, identity_id=supervisor, confirm_reset=True)

    # Слот автора локально тоже «мой» (ключ автора есть в этой Студии), но на его плашке другой ключ.
    assert {r["slot_id"]: r["ok"] for r in done["results"]} == {"author": False, "supervisor": True}
    plan = await api.plan()
    assert (plan["author"]["status"], plan["supervisor"]["status"]) == ("pending", "signed")


@_GPG
async def test__passphrase_key__asked_once_and_never_stored(test_app: AsyncClient, tmp_path: Path) -> None:
    api = await _api(test_app, tmp_path)
    await _pgp_key(test_app, "Иван Иванов", passphrase="correct horse")
    await api.mode("author", "detached_text")

    preview = await api.preview()
    assert preview["needs_passphrase"] is True
    tokens = {d["doc_id"]: d["token"] for d in preview["docs"]}
    missing = await test_app.post(f"{api.base}/signature-plan/sign", json={"profile_id": _PROFILE, "expected": tokens})
    assert missing.status_code == 400, missing.text
    result = await api.sign(passphrase="correct horse")

    assert [r["ok"] for r in result["results"]] == [True]
    assert "correct horse" not in json.dumps(api.state())


async def test__freeze_again_without_changes__keeps_pades_chain(test_app: AsyncClient, tmp_path: Path) -> None:
    api = await _api(test_app, tmp_path)
    key = await _x509_key(test_app, "Ivan Ivanov")
    await api.png("author")
    await api.mode("author", "image_crypto")
    await api.sign(identity_id=key)
    signed = api.state()["frozen"][_DOC]["signed_sha256"]

    resp = await test_app.post(f"{api.base}/docs/{_DOC}/frozen")

    assert resp.status_code == 200, resp.text
    assert api.state()["frozen"][_DOC]["signed_sha256"] == signed
    assert (await api.plan())["author"]["status"] == "signed"
    _make_pdf(api.pdf, "rebuilt")
    resp = await test_app.post(f"{api.base}/docs/{_DOC}/frozen")
    assert resp.json()["dropped_slots"] == ["author"]
    assert api.state()["embedded"] == {}
    assert not (api.folder / ".hse-studio" / "frozen" / f"{_DOC}.signed.pdf").exists()


# --- ключ по умолчанию --------------------------------------------------------------------------------------------


async def test__default_key__single_key_auto_then_explicit_choice(test_app: AsyncClient, tmp_path: Path) -> None:
    first = await _x509_key(test_app, "Ivan Ivanov")
    auto = (await test_app.get("/api/v1/signing-identities/default")).json()
    assert (auto["identity_id"], auto["effective_id"], auto["auto"]) == (None, first, True)
    second = await _x509_key(test_app, "Ivan Ivanov 2")
    assert (await test_app.get("/api/v1/signing-identities/default")).json()["effective_id"] is None

    resp = await test_app.put("/api/v1/signing-identities/default", json={"identity_id": second})

    assert resp.status_code == 200, resp.text
    assert (resp.json()["identity_id"], resp.json()["auto"]) == (second, False)
    missing = await test_app.put(
        "/api/v1/signing-identities/default", json={"identity_id": "00000000-0000-0000-0000-000000000000"}
    )
    assert missing.status_code == 404


async def test__sign_submission__supervisor_slot_without_my_key__not_mine(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    api = await _api(test_app, tmp_path)
    await _x509_key(test_app, "Ivan Ivanov")
    await api.png("author")
    await api.mode("author", "image")
    await api.mode("supervisor", "detached_text")

    preview = await api.preview()

    assert preview["docs"] == []
    assert preview["to_sign"] == 0
    assert (await api.plan())["supervisor"]["is_mine"] is False


# --- выгрузка «С подписями» и пакет для подписанта: итоговый файл плана ------------------------------------------


def _zip_files(content: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        return {name: zf.read(name) for name in zf.namelist()}


async def _signed_pdf(api: Api) -> bytes:
    resp = await api.client.get(f"{api.base}/docs/{_DOC}/pdf/signed")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    return resp.content


async def _mixed_detached_and_pades(api: Api) -> None:
    student = await _x509_key(api.client, "Ivan Ivanov")
    supervisor = await _x509_key(api.client, "Petr Petrov")
    await api.mode("author", "detached_text")
    await api.png("supervisor")
    await api.mode("supervisor", "image_crypto")
    await api.plate_from_key("supervisor", supervisor)
    await api.plate_from_key("author", student)
    await api.sign(identity_id=supervisor)
    await api.sign(identity_id=student)


async def test__signed_pdf__final_pades_file__served_byte_for_byte(test_app: AsyncClient, tmp_path: Path) -> None:
    api = await _api(test_app, tmp_path)
    await _mixed_detached_and_pades(api)

    served = await _signed_pdf(api)

    assert served == api.final_bytes()
    assert served != api.frozen_bytes()
    assert await _pades_fields(served, tmp_path) == [("Sig_supervisor", True)]
    plan = await api.plan()
    assert (plan["author"]["status"], plan["supervisor"]["status"]) == ("signed", "signed")


async def test__signed_pdf__frozen_without_pades__serves_frozen_bytes(test_app: AsyncClient, tmp_path: Path) -> None:
    api = await _api(test_app, tmp_path)
    student = await _x509_key(test_app, "Ivan Ivanov")
    await api.mode("author", "detached_text")
    await api.plate_from_key("author", student)
    await api.sign(identity_id=student)

    assert await _signed_pdf(api) == api.frozen_bytes()


async def test__signed_pdf__not_frozen__print_preview_without_on_the_fly_signatures(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    api = await _api(test_app, tmp_path)
    key = await _x509_key(test_app, "Ivan Ivanov")
    await api.png("author")
    await api.mode("author", "image_crypto", identity_id=key)

    served = await _signed_pdf(api)

    assert served != api.pdf.read_bytes()  # картинка поставлена
    assert await _pades_fields(served, tmp_path) == []
    assert (await api.plan())["author"]["status"] == "pending"
    assert "frozen" not in api.state() or not api.state()["frozen"]


async def test__signed_pdf__rebuilt_after_pades__serves_preview_of_current_build(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    api = await _api(test_app, tmp_path)
    key = await _x509_key(test_app, "Ivan Ivanov")
    await api.png("author")
    await api.mode("author", "image_crypto")
    await api.sign(identity_id=key)
    _make_pdf(api.pdf, "annotation, second edition")

    served = await _signed_pdf(api)

    assert served != api.final_bytes()
    assert await _pades_fields(served, tmp_path) == []
    assert (await api.plan())["author"]["status"] == "stale"


async def test__signed_pdf__final_file_changed_outside_studio__400(test_app: AsyncClient, tmp_path: Path) -> None:
    api = await _api(test_app, tmp_path)
    key = await _x509_key(test_app, "Ivan Ivanov")
    await api.png("author")
    await api.mode("author", "image_crypto")
    await api.sign(identity_id=key)
    signed = api.folder / api.state()["frozen"][_DOC]["signed_path"]
    signed.write_bytes(signed.read_bytes() + b"\n%tampered\n")

    resp = await test_app.get(f"{api.base}/docs/{_DOC}/pdf/signed")

    assert resp.status_code == 400, resp.text


async def test__signing_package__with_pades__has_final_file_and_base_for_detached(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    api = await _api(test_app, tmp_path)
    await _mixed_detached_and_pades(api)
    final, base = api.final_bytes(), api.frozen_bytes()

    for mode in ("request", "signed"):
        resp = await test_app.get(f"{api.base}/docs/{_DOC}/signing-package", params={"mode": mode})
        assert resp.status_code == 200, resp.text
        files = _zip_files(resp.content)
        pdfs = {name: blob for name, blob in files.items() if name.endswith(".pdf")}
        (base_name,) = [name for name in pdfs if name.endswith(".для-открепленных-подписей.pdf")]
        (final_name,) = [name for name in pdfs if name != base_name]
        assert (pdfs[final_name], pdfs[base_name]) == (final, base)
        readme = files["README.txt"].decode()
        assert final_name in readme
        assert base_name in readme
        if mode == "request":
            assert f"{hashlib.sha256(base).hexdigest()}  {base_name}" in files["SHA256SUMS.txt"].decode()
        else:
            (sig_name,) = [name for name in files if name.endswith(".p7s") or name.endswith(".sig")]
            assert sig_name.startswith(base_name.removesuffix(".pdf"))
            assert await _cms_intact(files[sig_name], pdfs[base_name])


async def test__signing_package__without_pades__unchanged_single_pdf(test_app: AsyncClient, tmp_path: Path) -> None:
    api = await _api(test_app, tmp_path)
    student = await _x509_key(test_app, "Ivan Ivanov")
    await api.mode("author", "detached_text")
    await api.plate_from_key("author", student)
    await api.sign(identity_id=student)

    resp = await test_app.get(f"{api.base}/docs/{_DOC}/signing-package", params={"mode": "request"})

    files = _zip_files(resp.content)
    (pdf,) = [blob for name, blob in files.items() if name.endswith(".pdf")]
    assert pdf == api.frozen_bytes()
    assert "PAdES" not in files["README.txt"].decode()


# --- отпечаток видимого слоя прежнего вида ------------------------------------------------------------------------


async def test__legacy_stamps_digest__frozen_before_upgrade__stays_current(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    api = await _api(test_app, tmp_path)
    student = await _x509_key(test_app, "Ivan Ivanov")
    await api.png("supervisor")
    await api.mode("supervisor", "image")
    await api.mode("author", "detached_text")
    await api.plate_from_key("author", student)
    await api.sign(identity_id=student)
    # Фиксация, сделанная прежней Студией: отпечаток считан по repr меток с абсолютным путём картинки.
    state = JsonSignatureRepository().get_state(api.folder)
    legacy = legacy_stamps_digest(stamps_for_doc(state, _DOC, api.folder, "ru"))
    raw = api.state()
    assert raw["frozen"][_DOC]["stamps_digest"] != legacy
    raw["frozen"][_DOC]["stamps_digest"] = legacy
    (api.folder / ".hse-studio" / "signatures.json").write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    plan = await api.plan()
    frozen = (await test_app.get(f"{api.base}/signatures")).json()["frozen"][_DOC]

    assert (plan["author"]["status"], plan["supervisor"]["status"]) == ("signed", "signed")
    assert (frozen["stale"], frozen["plate_outdated"]) == (False, False)
    assert await _signed_pdf(api) == api.frozen_bytes()
