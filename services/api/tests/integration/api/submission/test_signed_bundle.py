"""Комплект для LMS со смешанными подписями: проверка внешними gpg и pyHanko (docs/design/signature-plan.md, 8)."""

from __future__ import annotations

import io
import shutil
import zipfile
from pathlib import Path

import pytest
from httpx import AsyncClient

from tests.integration.api.signatures.test_sign_submission import (
    _PROFILE,
    _api,
    _cms_intact,
    _gpg_verify,
    _pades_fields,
    _pgp_key,
    _x509_key,
    gnupg_home,  # noqa: F401 — фикстура
)

_PDF = "Аннотация.pdf"
_BASE = "Аннотация.для-открепленных-подписей.pdf"


async def _bundle(client: AsyncClient, project_id: str) -> dict[str, bytes]:
    resp = await client.post(
        f"/api/v1/projects/{project_id}/submissions",
        json={"profile_id": _PROFILE, "items": [], "extra_items": [], "archive_format": "zip"},
    )
    assert resp.status_code == 201, resp.text
    with zipfile.ZipFile(io.BytesIO(Path(resp.json()["output_path"]).read_bytes())) as zf:
        return {name: zf.read(name) for name in zf.namelist()}


@pytest.mark.skipif(shutil.which("gpg") is None, reason="gpg is not installed")
async def test__bundle__openpgp_detached_and_pades__both_files_verify_outside_studio(
    test_app: AsyncClient,
    tmp_path: Path,
    gnupg_home: Path,  # noqa: F811
) -> None:
    api = await _api(test_app, tmp_path)
    student = await _pgp_key(test_app, "Иван Иванов")
    supervisor = await _x509_key(test_app, "Petr Petrov")
    await api.mode("author", "detached_text")
    await api.mode("supervisor", "crypto_invisible")
    await api.plate_from_key("supervisor", supervisor)
    await api.sign(identity_id=student["id"])
    await api.sign(identity_id=supervisor)

    files = await _bundle(test_app, api.pid)

    signature = "Аннотация.для-открепленных-подписей.Иван_Иванов.openpgp.asc"
    assert {_PDF, _BASE, signature, "КАК_ПРОВЕРИТЬ.txt"} <= set(files)
    assert files[_PDF].startswith(files[_BASE])
    assert await _gpg_verify(test_app, gnupg_home, student["id"], files[signature], files[_BASE])
    assert await _pades_fields(files[_PDF], tmp_path) == [("Sig_supervisor", True)]
    guide = files["КАК_ПРОВЕРИТЬ.txt"].decode("utf-8")
    assert f'gpg --verify "{signature}" "{_BASE}"' in guide
    assert f'pyhanko sign validate --pretty-print "{_PDF}"' in guide
    assert f'cmp -n {len(files[_BASE])} "{_BASE}" "{_PDF}"' in guide
    assert any(name.startswith("public-key.") for name in files)


async def test__bundle__cms_detached_and_image__single_pdf_and_graphic_marked(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    api = await _api(test_app, tmp_path)
    student = await _x509_key(test_app, "Ivan Ivanov")
    await api.mode("author", "detached_text")
    await api.png("supervisor")
    await api.mode("supervisor", "image")
    await api.sign(identity_id=student)

    files = await _bundle(test_app, api.pid)

    signature = "Аннотация.Ivan_Ivanov.cades.p7s"
    assert _BASE not in files
    assert await _cms_intact(files[signature], files[_PDF])
    guide = files["КАК_ПРОВЕРИТЬ.txt"].decode("utf-8")
    assert "Научный руководитель: графическая подпись (картинка, не ЭП)" in guide
    assert "открепленная ЭП" in guide


async def test__bundle__pades_slot_not_signed__refused_with_hint(test_app: AsyncClient, tmp_path: Path) -> None:
    api = await _api(test_app, tmp_path)
    await api.png("author")
    await api.png("supervisor")
    await api.mode("author", "image")
    await api.mode("supervisor", "image_crypto")

    resp = await test_app.post(
        f"/api/v1/projects/{api.pid}/submissions",
        json={"profile_id": _PROFILE, "items": [], "extra_items": [], "archive_format": "zip"},
    )

    # Раньше слот PAdES проходил по одной картинке: картинка выдавала себя за ЭП.
    assert resp.status_code == 400, resp.text
    assert "supervisor" in resp.json()["detail"]
