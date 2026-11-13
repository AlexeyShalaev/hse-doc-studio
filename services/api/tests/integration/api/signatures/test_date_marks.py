"""Метки даты подписания мимо маршрута: `PUT .../dates`, чтение и PDF (docs/design/signing-route.md, 14.7)."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from pypdf import PdfReader

from tests.integration.api.mcp.test_mcp_local import Studio, _client, _enable, studio  # noqa: F401
from tests.integration.api.signatures.test_signature_plan import _PNG_1PX, _make_pdf, _project

_DOC = "annotation"
_PROFILE = "checkpoint-1"


def _mark(fmt: str, x_mm: float, *, mark_id: str | None = None, page: int = 1, width_mm: float = 22) -> dict[str, Any]:
    return {
        "id": mark_id,
        "page": page,
        "x_mm": x_mm,
        "y_mm": 250.0,
        "width_mm": width_mm,
        "height_mm": 5.0,
        "format": fmt,
        "align": "center",
    }


_THREE = [_mark("day", 120, width_mm=8), _mark("month_word", 132), _mark("year_short", 160, width_mm=6)]


def _url(project_id: str, slot: str = "supervisor", doc: str = _DOC) -> str:
    return f"/api/v1/projects/{project_id}/signatures/placements/{doc}/{slot}/dates"


async def _put(client: AsyncClient, project_id: str, body: dict[str, Any], slot: str = "supervisor") -> Any:
    return await client.put(_url(project_id, slot), json=body)


def _texts(placement: dict[str, Any]) -> list[str | None]:
    return [m["text"] for m in placement["dates"]]


async def test__put_dates__no_placement_yet__created_off_with_ids_and_empty_texts(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    project_id, _ = await _project(test_app, tmp_path / "proj")

    resp = await _put(test_app, project_id, {"dates": _THREE})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["enabled"] is False
    assert [(m["id"], m["format"], m["text"]) for m in body["dates"]] == [
        ("d1", "day", None),
        ("d2", "month_word", None),
        ("d3", "year_short", None),
    ]
    assert body["signed_at"] is None


async def test__put_dates__manual_date__texts_in_get_plan_and_signed_pdf(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id, _ = await _project(test_app, tmp_path / "proj")
    base = f"/api/v1/projects/{project_id}"
    resp = await test_app.post(
        f"{base}/signatures/slots/supervisor/png", files={"file": ("s.png", _PNG_1PX, "image/png")}
    )
    assert resp.status_code == 200, resp.text

    put = await _put(test_app, project_id, {"dates": _THREE, "signed_at": {"date": "2026-11-13"}})
    state = (await test_app.get(f"{base}/signatures")).json()
    plan = (await test_app.get(f"{base}/signature-plan", params={"profile_id": _PROFILE})).json()
    signed = await test_app.get(f"{base}/docs/{_DOC}/pdf/signed")

    assert put.status_code == 200, put.text
    assert _texts(put.json()) == ["13", "ноября", "26"]
    assert put.json()["signed_at"] == {"at": "2026-11-13", "source": "manual"}
    placement = state["placements"][_DOC]["supervisor"]
    assert _texts(placement) == ["13", "ноября", "26"]
    assert placement["signed_at"] == {"at": "2026-11-13", "source": "manual"}
    slot = next(s for d in plan["docs"] for s in d["slots"] if s["slot_id"] == "supervisor")
    assert slot["dates"] == [
        {"page": 1, "format": "day", "text": "13"},
        {"page": 1, "format": "month_word", "text": "ноября"},
        {"page": 1, "format": "year_short", "text": "26"},
    ]
    assert slot["signed_at"] == {"at": "2026-11-13", "source": "manual"}
    # Метки даты печатаются и без размещённой подписи: в PDF «С подписями» их текст.
    assert signed.status_code == 200, signed.text
    text = PdfReader(io.BytesIO(signed.content)).pages[0].extract_text()
    assert "ноября" in text
    assert "26" in text


async def test__put_dates__ids_kept_new_ones_numbered_after_the_known_and_date_kept_or_cleared(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    project_id, _ = await _project(test_app, tmp_path / "proj")
    first = (await _put(test_app, project_id, {"dates": _THREE, "signed_at": {"date": "2026-11-13"}})).json()

    # d2 убрана, d3 сдвинута, новая метка получает d4, а не занятый или удалённый номер.
    kept = await _put(
        test_app, project_id, {"dates": [_mark("year", 170, mark_id="d3"), _mark("date_long", 20, width_mm=60)]}
    )
    # Ответ несёт `text`, запрос его не принимает: метки отправляются без него.
    marks = [{k: v for k, v in m.items() if k != "text"} for m in kept.json()["dates"]]
    cleared = await _put(test_app, project_id, {"dates": marks, "signed_at": None})
    patched = await test_app.patch(
        f"/api/v1/projects/{project_id}/signatures/placements/{_DOC}/supervisor", json={"enabled": True}
    )

    assert [m["id"] for m in first["dates"]] == ["d1", "d2", "d3"]
    assert kept.status_code == 200, kept.text
    assert [(m["id"], m["x_mm"], m["text"]) for m in kept.json()["dates"]] == [
        ("d3", 170.0, "2026"),
        ("d4", 20.0, "13 ноября 2026 г."),
    ]
    assert kept.json()["signed_at"] == {"at": "2026-11-13", "source": "manual"}
    assert cleared.status_code == 200, cleared.text
    assert (cleared.json()["signed_at"], _texts(cleared.json())) == (None, [None, None])
    # PATCH размещения метки даты не трогает.
    assert patched.status_code == 200, patched.text
    assert [m["id"] for m in patched.json()["dates"]] == ["d3", "d4"]


@pytest.mark.parametrize(
    ("dates", "fragment"),
    [
        ([_mark("day", 10)] * 9, "не больше 8"),
        ([_mark("era", 10)], "неизвестный формат"),
        ([{**_mark("day", 10), "align": "justify"}], "неизвестное выравнивание"),
        ([_mark("day", 10, mark_id="d1"), _mark("year", 40, mark_id="d1")], "повторяется"),
        ([_mark("day", 10, page=2)], "страницы 2 нет в документе (страниц: 1)"),
        ([_mark("day", 200)], "выходит за край страницы 1"),
        ([_mark("day", -1)], "выходит за край страницы 1"),
        ([{**_mark("day", 10), "height_mm": 0}], "нет размера"),
    ],
)
async def test__put_dates__wrong_mark__400_bad_date_mark_nothing_written(
    test_app: AsyncClient, tmp_path: Path, dates: list[dict[str, Any]], fragment: str
) -> None:
    project_id, _ = await _project(test_app, tmp_path / "proj")

    resp = await _put(test_app, project_id, {"dates": dates}, slot="author")
    state = (await test_app.get(f"/api/v1/projects/{project_id}/signatures")).json()

    assert (resp.status_code, resp.json()["code"]) == (400, "bad_date_mark")
    assert fragment in resp.json()["detail"]
    assert state["placements"] == {}


@pytest.mark.parametrize("day", ["13.11.2026", "2026-11-31", "2026-11-13T10:00:00Z", ""])
async def test__put_dates__wrong_manual_date__400_bad_date(test_app: AsyncClient, tmp_path: Path, day: str) -> None:
    project_id, _ = await _project(test_app, tmp_path / "proj")

    resp = await _put(test_app, project_id, {"dates": _THREE, "signed_at": {"date": day}})

    assert (resp.status_code, resp.json()["code"]) == (400, "bad_date")


async def test__put_dates__unknown_slot_404_slot_not_on_the_document_400_extra_field_422(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    project_id, _ = await _project(test_app, tmp_path / "proj")

    unknown = await _put(test_app, project_id, {"dates": []}, slot="dean")
    not_here = await test_app.put(_url(project_id, "author", "presentation"), json={"dates": []})
    extra = await _put(test_app, project_id, {"dates": [], "surprise": 1})

    assert unknown.status_code == 404
    assert not_here.status_code == 400
    assert extra.status_code == 422


async def test__put_dates__document_not_built__only_page_and_left_top_edges_checked(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    project_id, pdf = await _project(test_app, tmp_path / "proj")
    pdf.unlink()

    far = await _put(test_app, project_id, {"dates": [_mark("day", 10, page=5)]})
    _make_pdf(pdf)
    later = await _put(test_app, project_id, {"dates": [_mark("day", 10, page=5)]})

    assert far.status_code == 200, far.text
    assert (later.status_code, later.json()["code"]) == (400, "bad_date_mark")


async def test__mcp_get_signature_plan__dates_and_signed_at(studio: Studio) -> None:  # noqa: F811
    await _enable(studio)
    base = f"/api/v1/projects/{studio.project_id}"
    doc = (await studio.rest.get(f"{base}/documents/{_DOC}")).json()
    _make_pdf(studio.folder / doc["output_file"])
    resp = await studio.rest.put(
        f"{base}/signatures/placements/{_DOC}/supervisor/dates",
        json={"dates": [_mark("date_long", 20, width_mm=60)], "signed_at": {"date": "2026-11-13"}},
    )
    assert resp.status_code == 200, resp.text

    async with _client(studio) as client:
        result = await client.call_tool("get_signature_plan", {"project_id": studio.project_id, "profile_id": _PROFILE})

    plan = json.loads(result.content[0].text)  # type: ignore[union-attr]
    slot = next(s for d in plan["docs"] for s in d["slots"] if s["slot_id"] == "supervisor")
    assert slot["dates"] == [{"page": 1, "format": "date_long", "text": "13 ноября 2026 г."}]
    assert slot["signed_at"] == {"at": "2026-11-13", "source": "manual"}
