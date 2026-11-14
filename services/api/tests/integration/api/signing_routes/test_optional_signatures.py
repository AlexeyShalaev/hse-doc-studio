"""«Подпись необязательна на этой точке» на настоящем сервере (docs/design/signing-route.md, 13.3, 13.6 и 13.8).

Отметка идёт мимо сторожа `route_locked` и на идущем маршруте; слот сверх точки отмечается на точке маршрута; права
те же, что у отправки маршрута; снятие отметки у пропущенной пары оставляет пропуск до нового раунда, пока маршрут
держит документ, и снимает его, когда не держит.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import text

from tests.integration.api.signing_routes.signer_stand import APPLICATION, PROPOSAL, Trio, make_trio
from tests.integration.api.signing_routes.stand import TOPIC, Person, Stand
from tests.integration.api.signing_routes.watch_stand import drain

pytestmark = [pytest.mark.pg, pytest.mark.timeout(240)]

ACADEMIC = "academic_supervisor"


def _code(resp: Any) -> tuple[int, str | None]:
    return resp.status_code, resp.json().get("code") if resp.content else None


def _mark(trio: Trio, who: Person, doc_id: str, slot_id: str, *, optional: bool = True) -> Any:
    path = f"{trio.project.base}/signatures/optional/{doc_id}/{slot_id}"
    return trio.call(who, "PUT", path, json={"profile_id": TOPIC, "optional": optional})


async def _skip(trio: Trio, doc_id: str, slot_id: str) -> None:
    """Пропуск, как его записывает маршрут (R20): участник в базе и запись в `signatures.json`.

    Маршрут пишет пропуск под блокировкой своей строки и `project_lock`, тест пишет мимо них. Поэтому сначала ждём
    фоновую сверку, которую поставила предыдущая отметка: иначе она прочитает участников до записи, а файлы после,
    увидит пропуск в файлах без пропуска участника и уберёт его (`Unskip`).
    """
    drain(trio.stand)
    skipped = {
        "round": 1,
        "at": "2026-11-13T10:00:00+00:00",
        "by": trio.author.id,
        "pairs": [{"doc_id": doc_id, "slot_id": slot_id}],
        "kept_marks": [],
        "refrozen": [],
    }
    async with trio.stand.sessions.use() as db:
        await db.execute(
            text("UPDATE signing_route_participants SET skipped = CAST(:skipped AS jsonb) WHERE persona = :persona"),
            {"skipped": json.dumps(skipped), "persona": slot_id},
        )
    # Файлы после базы: сверка маршрута между ними убрала бы запись, у которой нет пропуска участника (`Unskip`).
    _skip_in_files(trio, doc_id, slot_id)


def _skip_in_files(trio: Trio, doc_id: str, slot_id: str) -> None:
    """Запись пропуска в `signatures.json` мимо `project_lock`: только когда фоновых сверок нет, иначе сверка,
    прочитавшая файл раньше, перепишет его без пропуска."""
    drain(trio.stand)
    path = trio.project.folder / ".hse-studio" / "signatures.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("skipped", {}).setdefault(doc_id, {})[slot_id] = {
        "profile_id": TOPIC,
        "route_id": trio.route_id,
        "round": 1,
        "at": "2026-11-13T10:00:00+00:00",
        "keep_mark": False,
    }
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


async def test__optional_flag__on_a_going_route__extra_slot_marked_listed_and_audited(stand: Stand) -> None:
    trio = await make_trio(stand, images=("author", "supervisor"))
    trio.sent()
    before = trio.route()

    marked = _mark(trio, trio.author, APPLICATION, ACADEMIC)
    again = _mark(trio, trio.author, APPLICATION, ACADEMIC)
    listed = trio.call(trio.author, "GET", f"{trio.project.base}/signatures").json()
    drain(stand)

    assert marked.status_code == 200, marked.text
    assert marked.json() == {
        "doc_id": APPLICATION,
        "slot_id": ACADEMIC,
        "profile_id": TOPIC,
        "optional": True,
        "skipped": False,
        "returns_next_round": False,
    }
    assert again.status_code == 200
    assert listed["optional"] == {APPLICATION: {TOPIC: [ACADEMIC]}}
    assert listed["skipped"] == {}
    runtime = {slot["id"]: slot for slot in listed["runtime_slots"]}
    # Академрука на заявлении включил маршрут сверх точки: галочка у слота показывается с названием точки.
    assert [ref["id"] for ref in runtime[ACADEMIC]["extra_by"].get(APPLICATION, [])] == [TOPIC]
    assert runtime[ACADEMIC]["required"] is False
    # Видимый слой и снимок не меняются: маршрут идёт дальше тем же шагом.
    route = trio.route()
    assert (route["status"], route["events"]) == (before["status"], before["events"])
    audit = trio.stand.admin().get("/api/admin/audit", params={"target": trio.project.id, "limit": 200}).json()
    flags = [e for e in audit["items"] if e["action"] == "signature.optional"]
    assert [(e["actor_id"], {k: v for k, v in e["details"].items() if k != "project_id"}) for e in flags] == [
        (
            trio.author.id,
            {
                "doc_id": APPLICATION,
                "slot_id": ACADEMIC,
                "profile_id": TOPIC,
                "optional": True,
                "route_id": trio.route_id,
            },
        )
    ]


async def test__optional_flag__rights_and_codes(stand: Stand) -> None:
    trio = await make_trio(stand, images=("author", "supervisor"))
    trio.sent()

    # Отмечает тот, кто отправляет маршрут: рецензенту (подписанту) нельзя.
    by_reviewer = _mark(trio, trio.supervisor, APPLICATION, ACADEMIC)
    # На пояснительной записке академрук не стоит ни по точке, ни по маршруту.
    unknown = _mark(trio, trio.author, PROPOSAL, ACADEMIC)
    # Автор согласовал при отправке, его картинка на заявлении уже стоит.
    signed = _mark(trio, trio.author, APPLICATION, "author")
    unknown_point = trio.call(
        trio.author,
        "PUT",
        f"{trio.project.base}/signatures/optional/{APPLICATION}/{ACADEMIC}",
        json={"profile_id": "no-such-point", "optional": True},
    )
    drain(stand)

    assert by_reviewer.status_code == 403
    assert _code(unknown) == (400, "unknown_slot")
    assert _code(signed) == (409, "slot_signed")
    assert unknown_point.status_code == 404
    assert trio.state()["optional"] == {}


async def test__optional_flag__removed_after_skip__skip_kept_while_held_and_dropped_after_cancel(
    stand: Stand,
) -> None:
    trio = await make_trio(stand, images=("author", "supervisor"))
    trio.sent()
    assert _mark(trio, trio.author, APPLICATION, ACADEMIC).status_code == 200
    await _skip(trio, APPLICATION, ACADEMIC)

    held = _mark(trio, trio.author, APPLICATION, ACADEMIC, optional=False)
    after_held = trio.state()
    # Ошибочное снятие отменяется: пропущенной паре отметку можно поставить снова, пропуск остаётся.
    remarked = _mark(trio, trio.author, APPLICATION, ACADEMIC)
    assert _mark(trio, trio.author, APPLICATION, ACADEMIC, optional=False).status_code == 200
    assert trio.call(trio.author, "POST", f"{trio.url}/cancel", json={}).status_code == 200
    marked = _mark(trio, trio.author, APPLICATION, ACADEMIC)
    _skip_in_files(trio, APPLICATION, ACADEMIC)  # отменённый маршрут держит только запись в файлах
    freed = _mark(trio, trio.author, APPLICATION, ACADEMIC, optional=False)
    drain(stand)

    assert held.status_code == 200, held.text
    assert (held.json()["skipped"], held.json()["returns_next_round"]) == (True, True)
    assert (after_held["optional"], list(after_held["skipped"])) == ({}, [APPLICATION])
    assert remarked.status_code == 200, remarked.text
    assert (remarked.json()["optional"], remarked.json()["skipped"], remarked.json()["returns_next_round"]) == (
        True,
        True,
        False,
    )
    # Отменённый маршрут документ не держит: слот сверх точки отметить уже нельзя, а снятие отметки снимает пропуск.
    assert _code(marked) == (400, "unknown_slot")
    assert freed.status_code == 200, freed.text
    assert (freed.json()["skipped"], freed.json()["returns_next_round"]) == (False, False)
    assert (trio.state()["optional"], trio.state()["skipped"]) == ({}, {})
