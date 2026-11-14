"""Места подписей на якорях шаблона на настоящем сервере (docs/design/signing-route.md, 15.17.8 и 15.17.9).

Пак `anchor_stand`: настоящая `hse-cs-sse/coursework` 2026.1.5, точка «Заявка на тему КП» с пресетом 15.10 на
якорях. Разные вёрстки (язык, строка консультанта, длинное название) дают разные места без правки пака; ручное место,
документ под маршрутом и с ЭП над B пересборка не двигает; без якорей (раннер прежней версии) место встаёт по
запасным мм пака, а метки даты без них не встают; у своего PDF мест из шаблона нет.
"""

from __future__ import annotations

import io
import json
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import hse_doc_studio.use_cases.signing_route.author as author_module
import pytest
from hse_doc_studio.core.signatures.ports import IBuildPlaces
from reportlab.pdfgen import canvas

from tests.integration.api.signing_routes.anchor_stand import (
    ANCHOR_VERSION,
    application_lines,
    build,
    proposal_lines,
)
from tests.integration.api.signing_routes.stand import TOPIC, TOPIC_DOCS, Person, Project, Stand, make_project, person
from tests.integration.api.signing_routes.watch_stand import container, in_app

pytestmark = [pytest.mark.pg, pytest.mark.timeout(240)]

PROPOSAL, APPLICATION = TOPIC_DOCS
HSE = {"name": "Петров Пётр Петрович", "role": "university"}
COMPANY = {"name": "Петров Пётр Петрович", "role": "company"}
CONSULTANT = {"name": "Сидоров Сидор Сидорович", "role": "company"}


async def _project(stand: Stand, **people: Any) -> tuple[Project, Person]:
    author = await person(stand, "Иванов Иван Иванович")
    supervisor = await person(stand, "Петров Пётр Петрович")
    project = make_project(stand, author, version=ANCHOR_VERSION, **({"supervisor": HSE} | people))
    await project.member(supervisor, "reviewer", "supervisor")
    return project, author


def _placements(project: Project) -> dict[str, dict[str, Any]]:
    path = project.folder / ".hse-studio" / "signatures.json"
    return dict(json.loads(path.read_text(encoding="utf-8")).get("placements", {})) if path.is_file() else {}


def _box(project: Project, doc_id: str, slot_id: str) -> tuple[float, float, float, bool]:
    place = _placements(project)[doc_id][slot_id]
    return place["x_mm"], place["y_mm"], place["width_mm"], place["enabled"]


def _draft(project: Project, who: Person) -> dict[str, Any]:
    created = project.call(who, "POST", project.routes, json={"profile_id": TOPIC})
    assert created.status_code == 201, created.text
    return dict(created.json())


def _after_build(stand: Stand, project: Project, doc_id: str) -> int:
    """Пересчёт мест после публикации сборки, как его зовёт хук сборки сервера."""

    async def run() -> int:
        places = await container(stand).get(IBuildPlaces)
        return await places.after_build(UUID(project.id), project.folder, doc_id)

    return int(in_app(stand, run))


def _rebuild(stand: Stand, project: Project, doc_id: str, lines: Any, text: str) -> int:
    build(project, doc_id, lines, text)
    return _after_build(stand, project, doc_id)


def _signatures(project: Project, who: Person) -> dict[str, Any]:
    resp = project.call(who, "GET", f"{project.base}/signatures")
    assert resp.status_code == 200, resp.text
    return dict(resp.json())


def _plan_hints(project: Project, who: Person) -> dict[tuple[str, str], list[str]]:
    plan = project.call(who, "GET", f"{project.base}/signature-plan")
    assert plan.status_code == 200, plan.text
    return {(d["doc_id"], s["slot_id"]): s["hints"] for d in plan.json()["docs"] for s in d["slots"]}


def _restore(project: Project, who: Person, doc_id: str, slot_id: str) -> Any:
    return project.call(who, "POST", f"{project.base}/signatures/placements/{doc_id}/{slot_id}/restore", json={})


def _send(project: Project, who: Person, route_id: str) -> dict[str, Any]:
    preview = project.call(who, "POST", f"{project.routes}/{route_id}/preview", json={}).json()
    expected = {d["doc_id"]: d["token"] for d in preview["docs"]}
    sent = project.call(who, "POST", f"{project.routes}/{route_id}/send", json={"expected": expected, "sign": None})
    assert sent.status_code == 200, sent.text
    return dict(sent.json())


# --- черновик по якорям ---------------------------------------------------------------------------------------------


async def test__draft__places_and_dates_on_the_lines_of_the_build(anchor_packs: Path, stand: Stand) -> None:
    project, author = await _project(stand)
    build(project, APPLICATION, application_lines())
    sha = build(project, PROPOSAL, proposal_lines())

    _draft(project, author)

    # Правые края у конца линии «Подпись» (195 мм), верх рамки на 10 и 11 мм выше линии.
    assert _box(project, APPLICATION, "supervisor") == (167.0, 176.8, 28.0, True)
    assert _box(project, APPLICATION, "author") == (165.0, 201.3, 30.0, True)
    # Описание проекта: рамка в пустой ячейке над строкой даты, на 30 мм правее её начала, верх на 22 мм выше.
    proposal = _placements(project)[PROPOSAL]["supervisor"]
    assert (proposal["x_mm"], proposal["y_mm"], proposal["width_mm"]) == (109.7, 131.0, 40.0)
    # Русская строка даты: день и месяц словом; метки английской строки (месяц числом) в этой сборке нет.
    assert [(m["format"], m["x_mm"], m["y_mm"]) for m in proposal["dates"]] == [
        ("day", 81.7, 148.0),
        ("month_word", 92.6, 148.0),
    ]
    assert proposal["from_pack"]["anchor"] == "supervisor"
    assert proposal["from_pack"]["build"] == sha[:16]
    state = _signatures(project, author)
    placement = state["placements"][APPLICATION]["supervisor"]
    assert (placement["origin"], placement["source"]) == ("pack", "anchor")
    assert placement["anchor"] == {"id": "supervisor", "state": "found"}
    runtime = next(s for s in state["runtime_slots"] if s["id"] == "supervisor")
    assert runtime["default_placements"][APPLICATION] == {
        "source": "anchor",
        "anchor": "supervisor",
        "align": "right",
        "dx_mm": 0.0,
        "dy_mm": -10.0,
        "width_mm": 28.0,
        "fallback": {"page": 1, "x_mm": 168.0, "y_mm": 177.0, "width_mm": 28.0},
    }


async def test__layouts__language_and_title_move_the_places_without_pack_edits(
    anchor_packs: Path, stand: Stand
) -> None:
    project, author = await _project(stand)
    build(project, APPLICATION, application_lines())
    build(project, PROPOSAL, proposal_lines())
    _draft(project, author)

    english = _rebuild(stand, project, APPLICATION, application_lines(lang="en"), "en")
    longer = _rebuild(stand, project, PROPOSAL, proposal_lines(title_rows=2), "long title")
    again = _rebuild(stand, project, PROPOSAL, proposal_lines(title_rows=2), "long title")

    # Английская шапка короче: научрук и автор на 28,8 мм выше; длинное название опускает строку даты.
    assert english == 2
    assert _box(project, APPLICATION, "supervisor") == (167.0, 148.0, 28.0, True)
    assert _box(project, APPLICATION, "author") == (165.0, 172.5, 30.0, True)
    assert longer == 1
    proposal = _placements(project)[PROPOSAL]["supervisor"]
    assert (proposal["y_mm"], [m["y_mm"] for m in proposal["dates"]]) == (137.0, [154.0, 154.0])
    # Та же сборка: места не меняются, файл не пишется.
    assert again == 0


async def test__layouts__consultant_row_moves_academic_and_a_missing_line_switches_its_place_off(
    anchor_packs: Path, stand: Stand
) -> None:
    project, author = await _project(stand, supervisor=COMPANY, co_supervisor=CONSULTANT)
    build(project, APPLICATION, application_lines(consultant=True, academic=True))
    build(project, PROPOSAL, proposal_lines())

    route = _draft(project, author)

    assert {(s["slot_id"]) for d in route["docs"] for s in d["slots"]} >= {"co_supervisor", "academic_supervisor"}
    assert _box(project, APPLICATION, "co_supervisor") == (167.0, 215.9, 28.0, True)
    assert _box(project, APPLICATION, "academic_supervisor") == (167.0, 234.1, 28.0, True)

    # Консультанта убрали из данных проекта: шаблон строку не печатает, академрук поднимается на её место.
    moved = _rebuild(stand, project, APPLICATION, application_lines(academic=True), "no consultant")

    assert moved == 2
    assert _box(project, APPLICATION, "academic_supervisor") == (167.0, 215.9, 28.0, True)
    # Пара консультанта осталась в черновике, а строки нет: место выключено, якорь `missing`.
    assert _box(project, APPLICATION, "co_supervisor") == (167.0, 215.9, 28.0, False)
    state = _signatures(project, author)
    assert state["placements"][APPLICATION]["co_supervisor"]["anchor"] == {"id": "co_supervisor", "state": "missing"}
    restored = _restore(project, author, APPLICATION, "co_supervisor")
    assert restored.status_code == 409, restored.text
    assert restored.json()["code"] == "anchor_missing"
    assert _plan_hints(project, author)[(APPLICATION, "supervisor")] == []

    # Шаблон и данные разошлись: строки научрука в сборке нет, план подсказывает `anchor_missing` (не блокирует).
    without = tuple(line for line in application_lines(academic=True) if line.id != "supervisor")
    assert _rebuild(stand, project, APPLICATION, without, "no supervisor line") == 1
    assert _box(project, APPLICATION, "supervisor")[3] is False
    assert _plan_hints(project, author)[(APPLICATION, "supervisor")] == ["anchor_missing"]


# --- что пересборка не двигает --------------------------------------------------------------------------------------


async def test__manual_place__stays_where_the_author_put_it(anchor_packs: Path, stand: Stand) -> None:
    project, author = await _project(stand)
    build(project, APPLICATION, application_lines())
    build(project, PROPOSAL, proposal_lines())
    _draft(project, author)
    patched = project.call(
        author, "PATCH", f"{project.base}/signatures/placements/{APPLICATION}/author", json={"x_mm": 150.0}
    )
    assert patched.status_code == 200, patched.text
    assert (patched.json()["origin"], patched.json()["source"]) == ("manual", None)

    moved = _rebuild(stand, project, APPLICATION, application_lines(lang="en"), "en")

    assert moved == 1  # только научрук
    assert _box(project, APPLICATION, "author") == (150.0, 201.3, 30.0, True)
    assert _box(project, APPLICATION, "supervisor")[1] == 148.0


async def test__document_on_a_route__rebuild_keeps_the_place_new_version_moves_it(
    anchor_packs: Path, stand: Stand, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(author_module, "SEND_INTERVAL", timedelta(0))
    project, author = await _project(stand)
    build(project, APPLICATION, application_lines())
    build(project, PROPOSAL, proposal_lines())
    route = _draft(project, author)
    project.png(author, "author")
    project.png(author, "supervisor")
    _send(project, author, route["id"])

    held = _rebuild(stand, project, APPLICATION, application_lines(lang="en"), "en")

    # Документ подписывают по версии на подписи: рабочая сборка места не двигает.
    assert held == 0
    assert _box(project, APPLICATION, "supervisor") == (167.0, 176.8, 28.0, True)

    _send(project, author, route["id"])

    # «Отправить новую версию»: места из шаблона встают по строкам отправленной сборки.
    assert _box(project, APPLICATION, "supervisor") == (167.0, 148.0, 28.0, True)
    assert _box(project, APPLICATION, "author") == (165.0, 172.5, 30.0, True)
    assert _box(project, PROPOSAL, "supervisor")[1] == 131.0  # описание не менялось


async def test__e_signature_over_b__rebuild_keeps_the_place(anchor_packs: Path, stand: Stand) -> None:
    project, author = await _project(stand)
    build(project, APPLICATION, application_lines())
    build(project, PROPOSAL, proposal_lines())
    _draft(project, author)
    path = project.folder / ".hse-studio" / "signatures.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw.setdefault("frozen", {})[APPLICATION] = {
        "path": f".hse-studio/frozen/{APPLICATION}.pdf",
        "sha256": "d" * 64,
        "source_sha256": "e" * 64,
        "size": 1,
        "frozen_at": "2026-11-14T10:00:00+00:00",
    }
    raw.setdefault("detached", {})[APPLICATION] = {
        "author": {
            "file": f".hse-studio/frozen/{APPLICATION}.author.sig",
            "format": "cms",
            "origin": "uploaded",
            "pdf_sha256": "d" * 64,
            "verdict": "valid",
            "signer": "Иванов",
            "signer_id": "f" * 64,
            "added_at": "2026-11-14T10:00:00+00:00",
        }
    }
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert json.loads(path.read_text(encoding="utf-8"))["detached"][APPLICATION]

    moved = _rebuild(stand, project, APPLICATION, application_lines(lang="en"), "en")

    assert moved == 0
    assert _box(project, APPLICATION, "supervisor") == (167.0, 176.8, 28.0, True)


# --- без якорей и свой PDF -----------------------------------------------------------------------------------------


async def test__runner_without_anchors__fallback_mm_places_no_date_marks(anchor_packs: Path, stand: Stand) -> None:
    project, author = await _project(stand)
    # Раннер прежней версии: PDF есть, якорей нет.
    build(project, APPLICATION, None)
    build(project, PROPOSAL, None)

    _draft(project, author)

    # Запасные места пака (замеры 2026.1.4) с пометкой якоря, без сборки; метки даты запасных мест не имеют.
    placements = _placements(project)
    assert _box(project, APPLICATION, "author") == (165.0, 201.0, 30.0, True)
    assert _box(project, APPLICATION, "supervisor") == (168.0, 177.0, 28.0, True)
    assert placements[APPLICATION]["author"]["from_pack"]["anchor"] == "author"
    assert placements[APPLICATION]["author"]["from_pack"].get("build") is None
    assert _box(project, PROPOSAL, "supervisor") == (110.0, 131.0, 40.0, True)
    assert placements[PROPOSAL]["supervisor"]["dates"] == []
    assert _after_build(stand, project, APPLICATION) == 0
    state = _signatures(project, author)
    assert state["placements"][APPLICATION]["author"]["anchor"] == {"id": "author", "state": "unknown"}
    assert _plan_hints(project, author)[(APPLICATION, "supervisor")] == []
    fallback = _restore(project, author, APPLICATION, "supervisor")
    assert fallback.status_code == 200, fallback.text
    assert (fallback.json()["x_mm"], fallback.json()["y_mm"]) == (168.0, 177.0)

    # Сборка уже с якорями: места из запасных встают по строкам, метки даты появляются у описания.
    assert _rebuild(stand, project, APPLICATION, application_lines(), "with anchors") == 2
    assert _box(project, APPLICATION, "author") == (165.0, 201.3, 30.0, True)
    assert _box(project, APPLICATION, "supervisor") == (167.0, 176.8, 28.0, True)
    assert _rebuild(stand, project, PROPOSAL, proposal_lines(), "with anchors") == 1
    proposal = _placements(project)[PROPOSAL]["supervisor"]
    assert (proposal["x_mm"], proposal["y_mm"]) == (109.7, 131.0)
    assert [m["format"] for m in proposal["dates"]] == ["day", "month_word"]
    restored = _restore(project, author, APPLICATION, "supervisor")
    assert restored.status_code == 200, restored.text
    assert (restored.json()["x_mm"], restored.json()["y_mm"], restored.json()["source"]) == (167.0, 176.8, "anchor")


def _pdf(text: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(100, 700, text)
    c.save()
    return buf.getvalue()


async def test__own_uploaded_pdf__no_template_places(anchor_packs: Path, stand: Stand) -> None:
    project, author = await _project(stand)
    build(project, APPLICATION, application_lines())
    build(project, PROPOSAL, proposal_lines())
    uploaded = project.call(
        author,
        "POST",
        f"{project.base}/documents/{APPLICATION}/custom-file",
        files={"file": ("моё заявление.pdf", _pdf("my application"), "application/pdf")},
    )
    assert uploaded.status_code == 200, uploaded.text

    _draft(project, author)

    # У своего PDF строк шаблона нет: ни места по якорю, ни запасного места в мм.
    assert set(_placements(project).get(APPLICATION, {})) == set()
    assert _box(project, PROPOSAL, "supervisor")[:2] == (109.7, 131.0)
    assert _after_build(stand, project, APPLICATION) == 0
    restored = _restore(project, author, APPLICATION, "author")
    assert restored.status_code == 409, restored.text
    assert restored.json()["code"] == "anchors_unknown"
