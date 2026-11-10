"""Что останавливает маршрут мимо страницы подписи (docs/design/signing-route.md, раздел 5.5) на настоящем сервере.

Хук сборки, хук записи состояния подписей, изменение проекта мимо API (синхронизация, восстановление), уход
участника и периодическая сверка. Маршрут записывается остановленным, уведомления уходят один раз, повторная
сверка ничего не меняет, а сценарии самого маршрута свою же запись за изменение не принимают.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from hse_doc_studio.core.git_remote.pdf_observer import IBuiltPdfObserver
from hse_doc_studio.core.repositories import ISignatureRepository
from hse_doc_studio.core.signing_route.ports import IRouteWatch
from hse_doc_studio.use_cases.signing_route.reconcile import RouteReconciler
from hse_doc_studio.use_cases.signing_route.watch import RouteWatch, WatchedSignatureRepository

from tests.integration.api.signing_routes.signer_stand import APPLICATION, PROPOSAL, Trio, make_trio, my
from tests.integration.api.signing_routes.stand import Stand
from tests.integration.api.signing_routes.watch_stand import (
    container,
    drain,
    in_app,
    notifications,
    pdf_built,
    project_changed,
    sweep,
)

pytestmark = [pytest.mark.pg, pytest.mark.timeout(240)]


def _stopped(trio: Trio) -> tuple[str, str | None]:
    route = trio.route()
    return route["status"], route["stop_reason"]


def _pdf(trio: Trio, doc_id: str) -> Any:
    doc = trio.call(trio.author, "GET", f"{trio.project.base}/documents/{doc_id}").json()
    return trio.project.folder / doc["output_file"]


def _edit_state(trio: Trio, change: Any) -> None:
    """Правка `signatures.json` мимо API, как её принесла бы синхронизация."""
    path = trio.project.folder / ".hse-studio" / "signatures.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    change(state)
    path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


async def test__server__build_and_signature_hooks_lead_to_the_route_watch(stand: Stand) -> None:
    async def wired() -> tuple[Any, Any, Any, Any]:
        app = container(stand)
        return (
            await app.get(RouteWatch),
            await app.get(IRouteWatch),
            await app.get(IBuiltPdfObserver),
            await app.get(ISignatureRepository),
        )

    watch, port, observer, signatures = in_app(stand, wired)

    assert port is watch
    assert observer is watch
    assert isinstance(signatures, WatchedSignatureRepository)


async def test__sent_version_replaced__route_paused_once_and_people_notified(stand: Stand) -> None:
    trio = await make_trio(stand, images=("author", "supervisor", "academic_supervisor"))
    trio.sent()
    trio.approved(trio.supervisor)
    assert trio.withheld() == {APPLICATION: ["academic_supervisor"]}

    # Пересборка маршрут не трогает (12.5): у документа только «есть изменения после отправки».
    trio.project.build(PROPOSAL, "v2")
    pdf_built(stand, trio, PROPOSAL)
    assert (trio.route()["status"], trio.route()["changed_docs"]) == ("active", [PROPOSAL])

    # Подмена версии на подписи мимо маршрута (git, восстановление): сверка останавливает маршрут.
    trio.project.replace_sent(PROPOSAL)
    pdf_built(stand, trio, PROPOSAL)

    route = trio.route()
    assert (route["status"], route["stop_reason"], route["phase"]) == ("paused", "sent_changed", None)
    assert [(e["kind"], e["reason"], e["who"]) for e in route["events"]][-1] == ("paused", "sent_changed", None)
    # Согласие действует по документам (12.6): картинка научрука придержана только на заявке, на заявлении она
    # остаётся, как и картинка автора: заявление не менялось.
    assert trio.withheld() == {APPLICATION: ["academic_supervisor"], PROPOSAL: ["supervisor"]}
    # Автору и тем, кто уже согласовал; академрук ещё не согласовывал.
    assert [n["payload"]["outcome"] for n in notifications(stand, trio, "author", "signing_paused")] == ["sent_changed"]
    assert len(notifications(stand, trio, "supervisor", "signing_paused")) == 1
    assert notifications(stand, trio, "academic_supervisor", "signing_paused") == []
    assert my(trio.task(trio.academic)) == ("waiting", "wait")

    # Повторная сборка и сверка остановленный маршрут не трогают: ни событий, ни уведомлений.
    trio.project.build(PROPOSAL, "v3")
    pdf_built(stand, trio, PROPOSAL)

    assert sweep(stand) == 0
    assert trio.events() == ["sent", "approved", "approved", "paused"]
    assert len(notifications(stand, trio, "author", "signing_paused")) == 1


async def test__rebuild__same_pdf__route_goes_on(stand: Stand) -> None:
    trio = await make_trio(stand, images=("author", "supervisor"), academic="none")
    sent = trio.sent()
    pdf = _pdf(trio, PROPOSAL)
    built = pdf.read_bytes()

    # Воспроизводимая сборка (R12): пересборка без правок кладёт те же байты.
    pdf.write_bytes(built)
    pdf_built(stand, trio, PROPOSAL)

    route = trio.route()
    assert (route["status"], route["updated_at"]) == ("active", sent["updated_at"])
    assert trio.events() == ["sent", "approved"]
    assert my(trio.task(trio.supervisor)) == ("to_approve", "approve")
    assert notifications(stand, trio, "author", "signing_paused") == []


async def test__other_document_rebuilt__route_goes_on(stand: Stand) -> None:
    trio = await make_trio(stand, images=("author", "supervisor"), academic="none")
    trio.sent()
    docs = trio.call(trio.author, "GET", f"{trio.project.base}/documents").json()
    other = next(d["id"] for d in docs if d["id"] not in (PROPOSAL, APPLICATION))

    trio.project.build(other, "v2")
    pdf_built(stand, trio, other)

    assert _stopped(trio) == ("active", None)
    assert trio.events() == ["sent", "approved"]


async def test__marks_changed_outside_the_route__route_paused_and_images_stay(stand: Stand) -> None:
    trio = await make_trio(stand, images=("author", "supervisor"), academic="none")
    trio.sent()

    # Синхронизация принесла другое размещение подписи автора: видимый слой изменился мимо маршрута.
    _edit_state(trio, lambda state: state["placements"][APPLICATION]["author"].update(x_mm=77))
    project_changed(stand, trio)

    assert _stopped(trio) == ("paused", "marks_changed")
    assert trio.events() == ["sent", "approved", "paused"]
    # Сборка та же: согласие автора в силе, его картинка не придерживается.
    assert trio.withheld() == {APPLICATION: ["supervisor"], PROPOSAL: ["supervisor"]}
    assert [n["payload"]["outcome"] for n in notifications(stand, trio, "author", "signing_paused")] == [
        "marks_changed"
    ]


async def test__frozen_pdf_removed_outside_the_route__route_paused(stand: Stand) -> None:
    trio = await make_trio(stand, {"supervisor": "detached"}, plates=("supervisor",), academic="none")
    trio.sent()
    assert sorted(trio.frozen_sha()) == [PROPOSAL, APPLICATION]

    # Восстановление из истории вернуло состояние без фиксации заявки.
    _edit_state(trio, lambda state: state["frozen"].pop(PROPOSAL))
    project_changed(stand, trio)

    assert _stopped(trio) == ("paused", "frozen_changed")
    assert [(e["kind"], e["reason"]) for e in trio.route()["events"]][-1] == ("paused", "frozen_changed")


async def test__completed_route__signature_edit__paused_by_the_state_write_hook(stand: Stand) -> None:
    trio = await make_trio(stand, images=("author", "supervisor"), academic="none")
    trio.sent()
    assert trio.approved(trio.supervisor)["route"]["status"] == "completed"
    placement = f"{trio.project.base}/signatures/placements/{APPLICATION}/author"

    # Завершённый маршрут правку не запрещает, но следит за документами: запись состояния подписей его останавливает.
    moved = trio.call(trio.author, "PATCH", placement, json={"x_mm": 55})
    drain(stand)

    assert moved.status_code == 200, moved.text
    assert _stopped(trio) == ("paused", "marks_changed")
    assert trio.events() == ["sent", "approved", "approved", "completed", "paused"]


async def test__participant_removed_from_the_project__route_paused_and_only_the_author_notified(
    stand: Stand,
) -> None:
    trio = await make_trio(stand, images=("author", "supervisor", "academic_supervisor"))
    trio.sent()
    trio.approved(trio.supervisor)

    removed = trio.call(
        trio.author, "DELETE", f"{trio.project.base}/members/user:{trio.people['academic_supervisor'].id}"
    )
    drain(stand)

    assert removed.status_code == 204, removed.text
    route = trio.route()
    assert (route["status"], route["stop_reason"]) == ("paused", "participant_left")
    assert [(e["kind"], e["reason"]) for e in route["events"]][-1] == ("paused", "participant_left")
    assert [n["payload"]["outcome"] for n in notifications(stand, trio, "author", "signing_paused")] == [
        "participant_left"
    ]
    assert notifications(stand, trio, "supervisor", "signing_paused") == []
    # Сборка та же: согласия в силе, картинки согласовавших остаются.
    assert trio.withheld() == {APPLICATION: ["academic_supervisor"]}


async def test__participant_lost_the_persona__route_paused(stand: Stand) -> None:
    trio = await make_trio(stand, images=("author", "supervisor"), academic="none")
    trio.sent()
    member = f"{trio.project.base}/members/user:{trio.supervisor.id}"
    grant = {"role": "reviewer", "persona": None, "can_share": False, "show_sources": True, "can_edit_all": False}

    # Научрук остался рецензентом, но без персоны: слот научрука он больше не подписывает.
    changed = trio.call(trio.author, "PUT", member, json=grant)
    drain(stand)

    assert changed.status_code == 200, changed.text
    assert _stopped(trio) == ("paused", "participant_left")
    assert len(notifications(stand, trio, "author", "signing_paused")) == 1


async def test__restore_from_history__signatures_rolled_back__route_paused(stand: Stand) -> None:
    trio = await make_trio(stand, images=("author", "supervisor"), academic="none")
    saved = trio.call(trio.author, "POST", f"{trio.project.base}/vcs/snapshots", json={"message": "до отправки"})
    assert saved.status_code == 200, saved.text
    trio.sent()
    assert trio.withheld() == {APPLICATION: ["supervisor"], PROPOSAL: ["supervisor"]}

    # Откат к версии до отправки возвращает состояние подписей без придержанных картинок: видимый слой другой.
    restored = trio.call(
        trio.author,
        "POST",
        f"{trio.project.base}/vcs/restore",
        json={"commit_id": saved.json()["id"], "mode": "snapshot"},
    )
    drain(stand)

    assert restored.status_code == 200, restored.text
    assert _stopped(trio) == ("paused", "marks_changed")
    assert [(e["kind"], e["reason"]) for e in trio.route()["events"]][-1] == ("paused", "marks_changed")


async def test__sweep__missed_hook__route_paused__second_pass_changes_nothing(stand: Stand) -> None:
    trio = await make_trio(stand, images=("author", "supervisor"), academic="none")
    other = await make_trio(stand, images=("author", "supervisor"), academic="none")
    trio.sent()
    untouched = other.sent()

    # Подмена версии на подписи без хука (git, восстановление `.hse-studio`): маршрут в хранилище ещё идёт.
    trio.project.replace_sent(APPLICATION)

    assert sweep(stand) == 1
    assert _stopped(trio) == ("paused", "sent_changed")
    assert len(notifications(stand, trio, "author", "signing_paused")) == 1
    # Идемпотентно: второй проход ничего не пишет, чужой маршрут не тронут.
    assert sweep(stand) == 0
    assert trio.events() == ["sent", "approved", "paused"]
    assert len(notifications(stand, trio, "author", "signing_paused")) == 1
    after = other.route()
    assert (after["status"], after["updated_at"]) == ("active", untouched["updated_at"])
    assert other.events() == ["sent", "approved"]


async def test__route_scenarios_write_signatures_themselves__no_reconciliation_and_no_false_stop(
    stand: Stand, monkeypatch: pytest.MonkeyPatch
) -> None:
    reconciled: list[bool] = []
    recalculate = RouteReconciler.recalculate

    async def spy(self: RouteReconciler, *args: Any, **kwargs: Any) -> bool:
        changed = await recalculate(self, *args, **kwargs)
        reconciled.append(changed)
        return changed

    monkeypatch.setattr(RouteReconciler, "recalculate", spy)
    trio = await make_trio(stand, images=("author", "supervisor", "academic_supervisor"))
    # Отправка придерживает картинки, согласие открывает картинку научрука: сценарий сам пишет состояние
    # подписей под блокировкой строки маршрута и `project_lock` и сам обновляет снимок.
    trio.sent()
    drain(stand)
    approved = trio.approved(trio.supervisor)
    drain(stand)

    assert my(approved) == ("done", "done")
    assert trio.withheld() == {APPLICATION: ["academic_supervisor"]}
    # Свои записи маршрута сверку не зовут: ни встречной блокировки, ни остановки по собственной правке.
    assert reconciled == []
    assert _stopped(trio) == ("active", None)
    assert trio.events() == ["sent", "approved", "approved"]
    assert notifications(stand, trio, "author", "signing_paused") == []
    assert my(trio.task(trio.academic)) == ("to_approve", "approve")

    # А сверка, попавшая на идущий маршрут без изменений, ничего не пишет.
    project_changed(stand, trio)

    assert reconciled == [False]
    assert trio.events() == ["sent", "approved", "approved"]
