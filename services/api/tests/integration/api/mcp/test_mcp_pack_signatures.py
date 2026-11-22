"""MCP: места подписей агентом (pack-studio-mcp.md, раздел 4): картинка страницы с рамками и проверка мест.

Локальная Студия, клиент SDK, настоящие роутер, DI и сценарии; подменён только бинарник docker (как в
`test_places.py`), а собранный PDF заменяется настоящим (reportlab): титул со строкой руководителя из подчёркиваний и
строкой студента линией рисунка. Рамка руководителя закрывает фамилию, рамка автора стоит далеко от своей линии:
проверка это находит и предлагает рамки, после `pack_set_placement` с предложением всё чисто.
"""

from __future__ import annotations

import base64
import io
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx2
import pytest
import pytest_asyncio
from fastapi import FastAPI
from hse_doc_studio.api.config import settings as app_settings
from hse_doc_studio.api.mcp_server import install_mcp
from hse_doc_studio.core.mode import StudioMode
from httpx import ASGITransport, AsyncClient
from mcp.client.client import Client
from mcp.client.streamable_http import streamable_http_client
from mcp_types import ImageContent
from PIL import Image
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from tests.fixtures.app import create_test_app, create_test_container
from tests.fixtures.fake_docker import FakeDocker
from tests.integration.api.pack_studio.conftest import DRAFT, Stand, write_pack
from tests.integration.api.pack_studio.test_places import FILES, fake_docker
from tests.integration.api.pack_studio.test_preview import _settled, _start

__all__ = ["fake_docker"]

_BASE = "http://127.0.0.1"
_VERSION = f"demo/report/{DRAFT}"
_FONT = Path(__file__).resolve().parents[4] / "hse_doc_studio" / "infra" / "signatures" / "fonts" / "DejaVuSans.ttf"


def title_page_pdf() -> bytes:
    """Титул: «Руководитель ____ И. О. Фамилия» на 120 мм сверху, «Автор» и линия рисунка 120..170 мм на 150 мм."""
    if "DV" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("DV", str(_FONT)))
    buf = io.BytesIO()
    sheet = canvas.Canvas(buf, pagesize=(210 * mm, 297 * mm))
    height = 297 * mm

    def text(x: float, y: float, value: str, size: int = 12) -> None:
        sheet.setFont("DV", size)
        sheet.drawString(x * mm, height - y * mm, value)

    text(70, 40, "КУРСОВАЯ РАБОТА", 14)
    text(25, 120, "Руководитель ____________________ И. О. Фамилия")
    text(25, 150, "Автор")
    sheet.line(120 * mm, height - 150 * mm, 170 * mm, height - 150 * mm)
    text(135, 154, "(подпись)", 8)
    sheet.save()
    return buf.getvalue()


@pytest_asyncio.fixture
async def studio(tmp_path: Path, fake_docker: FakeDocker) -> AsyncIterator[tuple[FastAPI, Stand]]:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    saved = app_settings.pack_studio.model_copy()
    container = create_test_container(data_dir)
    app = create_test_app(container)
    install_mcp(app, mode=StudioMode.local)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url=_BASE) as rest:
            resp = await rest.put("/api/v1/mcp/settings", json={"enabled": True})
            assert resp.status_code == 200, resp.text
            yield app, Stand(rest, tmp_path, container)
    finally:
        await container.close()
        app_settings.pack_studio = saved


def _client(app: FastAPI) -> Client:
    http = httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url=_BASE)
    return Client(streamable_http_client(f"{_BASE}/mcp", http_client=http), mode="legacy")


async def _built(stand: Stand) -> tuple[str, str]:
    """Пространство над папкой с паком и собранный отчёт, PDF которого заменён титулом."""
    await stand.enable()
    root = write_pack(stand.root / "packs", FILES)
    ws = await stand.folder_workspace(root.parent, packs_path=root.name)
    ws_id = str(ws["id"])
    _, builds = await _start(stand, ws_id, {"documents": ["report"], "example": "auto:normal"})
    done = await _settled(stand, ws_id, builds[0]["id"])
    assert done["status"] == "succeeded", done
    pdfs = [p for p in (stand.root / "data").rglob("*.pdf") if p.stat().st_size < 100]
    assert pdfs, "no preview pdf in the store"
    for path in pdfs:
        path.write_bytes(title_page_pdf())
    return ws_id, str(done["id"])


async def _json(client: Client, name: str, args: dict[str, Any], *, ok: bool = True) -> dict[str, Any]:
    result = await client.call_tool(name, args)
    text = result.content[0].text  # type: ignore[union-attr]
    assert result.is_error is (not ok), text
    return dict(json.loads(text))


async def test__check__finds_covered_text_and_far_box_and_suggests_places(
    studio: tuple[FastAPI, Stand],
) -> None:
    app, stand = studio
    ws, build = await _built(stand)
    args = {"workspace_id": ws, "version": _VERSION, "build_id": build, "format": "json"}

    async with _client(app) as client:
        # Руководитель на фамилии справа от строки, автор слева от своей линии.
        await _json(
            client,
            "pack_set_placement",
            {
                "workspace_id": ws,
                "version": _VERSION,
                "build_id": build,
                "ops": [
                    {"op": "set_place", "slot": "supervisor", "doc": "report", "box": _box(1, 100, 108, 40)},
                    {"op": "set_place", "slot": "author", "doc": "report", "box": _box(1, 40, 140, 40)},
                ],
            },
        )
        before = await _json(client, "pack_signature_check", args)
        await _json(
            client,
            "pack_set_placement",
            {"workspace_id": ws, "version": _VERSION, "build_id": build, "ops": before["suggested_ops"]},
        )
        after = await _json(client, "pack_signature_check", args)

    slots = {s["slot"]: s for s in before["slots"]}
    assert before["ok"] is False
    supervisor = {f["code"]: f for f in slots["supervisor"]["findings"]}
    assert supervisor["overlaps_text"]["severity"] == "error"
    assert "Фа" in supervisor["overlaps_text"]["text"]
    author_codes = {f["code"] for f in slots["author"]["findings"]}
    assert "far_from_line" in author_codes
    # Предложения: над подчёркиваниями руководителя и над линией автора (120..170 мм на 150 мм).
    supervisor_box = slots["supervisor"]["suggested_ops"][0]["box"]
    author_box = slots["author"]["suggested_ops"][0]["box"]
    assert supervisor_box["x_mm"] >= 45
    assert supervisor_box["x_mm"] + supervisor_box["width_mm"] <= 105
    assert 120 <= author_box["x_mm"] + author_box["width_mm"] / 2 <= 170
    assert author_box["y_mm"] < 150 < author_box["y_mm"] + author_box["width_mm"] * 0.4
    assert after["ok"] is True, after
    assert after["suggested_ops"] == []


async def test__render__png_pages_with_boxes_and_a_legend(studio: tuple[FastAPI, Stand]) -> None:
    app, stand = studio
    ws, build = await _built(stand)

    async with _client(app) as client:
        result = await client.call_tool(
            "pack_signature_render", {"workspace_id": ws, "version": _VERSION, "build_id": build, "dpi": 60}
        )
        missing = await _json(
            client,
            "pack_signature_render",
            {"workspace_id": ws, "version": _VERSION, "build_id": "00000000-0000-0000-0000-000000000001"},
            ok=False,
        )

    assert result.is_error is False
    legend = json.loads(result.content[0].text)  # type: ignore[union-attr]
    assert legend["shown"] == [1]
    assert {item["slot"] for item in legend["legend"]} >= {"supervisor", "author"}
    image = result.content[1]
    assert isinstance(image, ImageContent)
    assert image.mime_type == "image/png"
    png = Image.open(io.BytesIO(base64.b64decode(image.data)))
    assert abs(png.size[0] - 210 / 25.4 * 60) <= 1
    assert abs(png.size[1] - 297 / 25.4 * 60) <= 1
    # Синяя рамка руководителя по месту из пака: 110 мм слева, 130 мм сверху.
    x, y = round(110 / 25.4 * 60), round(130 / 25.4 * 60)
    pixel = png.convert("RGB").getpixel((x, y))
    assert isinstance(pixel, tuple)
    assert pixel[2] > 150
    assert missing["code"] == "preview_not_found"


def _box(page: int, x: float, y: float, width: float) -> dict[str, float]:
    return {"page": page, "x_mm": x, "y_mm": y, "width_mm": width}


@pytest.mark.parametrize("dpi", [50, 150])
def test__title_page_pdf__is_a_real_pdf(dpi: int) -> None:
    from hse_doc_studio.infra.pack_studio.pdf_pages import PdfPages  # noqa: PLC0415

    pages = PdfPages()
    data = title_page_pdf()
    layout = pages.layouts(data, [1])[1]

    assert pages.page_count(data) == 1
    assert {line.source.value for line in layout.lines} == {"drawing", "underscores"}
    assert pages.render(data, 1, dpi, []).startswith(b"\x89PNG")
