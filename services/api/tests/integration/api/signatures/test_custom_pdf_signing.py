"""Подписи, фиксация и пакет документа со своим PDF («Заменить на свой файл»).

Свой файл замещает шаблонную сборку: подписывают, фиксируют и кладут в пакет его, даже если шаблонный PDF от сборки
до замены остался на диске. Раньше источником подписи был шаблонный путь сборки: план считал документ собранным по
старому PDF, фиксация штамповала его, а пакет брал свой файл и отказывал «пересобран после фиксации».
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path

from httpx import AsyncClient
from pypdf import PdfReader
from reportlab.pdfgen import canvas

from tests.integration.api.signatures.test_sign_submission import _DOC, _PROFILE, _api, _cms_intact, _x509_key

_PDF = "Аннотация.pdf"


def _pdf(text: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(100, 700, text)
    c.save()
    return buf.getvalue()


def _text(blob: bytes) -> str:
    return "".join(page.extract_text() for page in PdfReader(io.BytesIO(blob)).pages)


async def test__custom_pdf__plan_freeze_sign_and_pack_use_the_uploaded_file(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    # Шаблонная сборка аннотации («annotation») остаётся на диске рядом со своим файлом.
    api = await _api(test_app, tmp_path)
    custom = _pdf("my own annotation")
    uploaded = await test_app.post(
        f"{api.base}/documents/{_DOC}/custom-file", files={"file": ("Моя аннотация.pdf", custom, "application/pdf")}
    )
    assert uploaded.status_code == 200, uploaded.text
    student = await _x509_key(test_app, "Ivan Ivanov")
    await api.mode("author", "detached_text")
    await api.png("supervisor")
    await api.mode("supervisor", "image")

    preview = await api.preview(identity_id=student)
    await api.sign(identity_id=student)
    packed = await test_app.post(
        f"{api.base}/submissions",
        json={"profile_id": _PROFILE, "items": [], "extra_items": [], "archive_format": "zip"},
    )

    sha = hashlib.sha256(custom).hexdigest()
    assert [(d["doc_id"], d["token"].split(":")[1]) for d in preview["docs"]] == [(_DOC, sha)]
    assert api.state()["frozen"][_DOC]["source_sha256"] == sha
    assert "my own annotation" in _text(api.frozen_bytes())
    assert packed.status_code == 201, packed.text
    with zipfile.ZipFile(io.BytesIO(Path(packed.json()["output_path"]).read_bytes())) as zf:
        files = {name: zf.read(name) for name in zf.namelist()}
    assert "my own annotation" in _text(files[_PDF])
    assert "annotation" not in _text(files[_PDF]).replace("my own annotation", "")
    [signature] = [name for name in files if name.endswith(".p7s")]
    assert await _cms_intact(files[signature], files[_PDF])
