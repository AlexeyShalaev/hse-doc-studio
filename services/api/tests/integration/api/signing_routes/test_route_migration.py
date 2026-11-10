"""Перенос маршрутов 0.20.0 на версию на подписи (docs/design/signing-route.md, 12.11) на настоящем сервере.

Маршрут 0.20.0 версии на подписи не снимал: в снимке только sha256 сборки на момент отправки, в состоянии подписей
нет `pinned`, у документов снимка нет `sent_at`. Стенд получает такой маршрут честной отправкой, после которой
версия на подписи и `sent_at` снимка стираются, как их и не было.

Форма прода: маршрут «Заявка на тему КП» (заявление и предложение) на втором шаге из трёх, у автора с 09.11 лежит
ручная фиксация заявления (`.hse-studio/frozen/topic_application.pdf`) из более ранней сборки, после отправки
документы пересобирались: заявление без правок (те же байты), предложение с правками. Сборки идут как на сервере:
запись сборки с отпечатком и PDF в архиве сборок (`IArtifactStore`).
"""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.entities import CompileRecord
from hse_doc_studio.core.enums import CompileStatus, EngineType
from hse_doc_studio.core.jobs.artifacts import IArtifactStore
from hse_doc_studio.core.repositories import ICompileRepository
from hse_doc_studio.infra.db.orm.signing_routes import SigningRouteRow
from hse_doc_studio.use_cases.signing_route import author as author_module
from hse_doc_studio.use_cases.signing_route.reconcile import RouteReconciler
from pypdf import PdfReader
from sqlalchemy import update

from tests.integration.api.signing_routes.signer_stand import APPLICATION, PROPOSAL, Trio, make_trio, my, states
from tests.integration.api.signing_routes.stand import TOPIC, Stand
from tests.integration.api.signing_routes.test_route_audit import _audit
from tests.integration.api.signing_routes.watch_stand import container, in_app, notifications, project_changed, sweep

pytestmark = [pytest.mark.pg, pytest.mark.timeout(240)]


@pytest.fixture(autouse=True)
def _no_send_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    # «Отправить новую версию» идёт следом за переносом: ограничение «раз в минуту» здесь не проверяется.
    monkeypatch.setattr(author_module, "SEND_INTERVAL", timedelta(0))


# --- стенд: сборки как на сервере и маршрут 0.20.0 --------------------------------------------------------------------


def _output(trio: Trio, doc_id: str) -> str:
    doc = trio.call(trio.author, "GET", f"{trio.project.base}/documents/{doc_id}").json()
    return str(doc["output_file"])


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record_build(stand: Stand, trio: Trio, doc_id: str) -> str:
    """Удачная сборка на сервере: запись с отпечатком PDF и его копия в архиве сборок; возвращает sha256 PDF."""
    output = _output(trio, doc_id)
    pdf = trio.project.folder / output
    sha256, size = _sha(pdf), pdf.stat().st_size
    folder, project_id = trio.project.folder, UUID(trio.project.id)

    async def record() -> None:
        now = datetime.now(UTC)
        async with container(stand)() as scope:
            compiles = await scope.get(ICompileRepository)
            artifacts = await scope.get(IArtifactStore)
            build = CompileRecord(
                id=uuid4(),
                project_folder=folder,
                doc_id=doc_id,
                engine=EngineType.xelatex,
                status=CompileStatus.success,
                started_at=now,
                finished_at=now,
                log="",
                output_path=pdf,
                check_results=[],
                pages=1,
                output_sha256=sha256,
                output_size=size,
            )
            await compiles.save(build)
            source = str(PurePosixPath(output).with_suffix(".tex"))
            await artifacts.archive_pdf(project_id, folder, doc_id, build.id, source)
            # Архив действительно держит эту сборку: перенос будет искать именно его.
            archived = await artifacts.read_archived_pdf(project_id, folder, doc_id, build.id)
            assert hashlib.sha256(archived).hexdigest() == sha256

    in_app(stand, record)
    return sha256


def _build(stand: Stand, trio: Trio, doc_id: str, text: str) -> str:
    trio.project.build(doc_id, text)
    return _record_build(stand, trio, doc_id)


def _rebuild_same(stand: Stand, trio: Trio, doc_id: str) -> str:
    """Пересборка без правок: воспроизводимая сборка кладёт те же байты."""
    pdf = trio.project.folder / _output(trio, doc_id)
    pdf.write_bytes(pdf.read_bytes())
    return _record_build(stand, trio, doc_id)


def _edit_state(trio: Trio, change: Any) -> None:
    path = trio.project.folder / ".hse-studio" / "signatures.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    change(state)
    path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


async def _as_sent_on_0_20_0(stand: Stand, trio: Trio, **row: Any) -> dict[str, str]:
    """Сделать отправленный маршрут маршрутом 0.20.0: без версии на подписи и без `sent_at` в снимке.

    `row` прочие поля строки маршрута (остановка на 0.20.0). Возвращает sha256 отправленных сборок по документам.
    """
    pinned = trio.state()["pinned"]
    sent = {doc_id: version["sha256"] for doc_id, version in pinned.items()}
    for version in pinned.values():
        (trio.project.folder / version["path"]).unlink()
    _edit_state(trio, lambda state: state.pop("pinned"))
    async with stand.sessions.use() as db:
        found = await db.get(SigningRouteRow, UUID(trio.route_id))
        assert found is not None
        snapshot = [{k: v for k, v in item.items() if k not in ("sent_at", "replaced")} for item in found.snapshot]
        assert [item["compiled_sha256"] for item in snapshot] == [sent[d] for d in (PROPOSAL, APPLICATION)]
        await db.execute(update(SigningRouteRow).where(SigningRouteRow.id == found.id).values(snapshot=snapshot, **row))
    return sent


def _migrate_all(stand: Stand) -> int | None:
    """Разовая задача лидера при старте."""

    async def run() -> int | None:
        async with container(stand)() as scope:
            return await (await scope.get(RouteReconciler)).migrate_all()

    result: int | None = in_app(stand, run)
    return result


def _migrations(trio: Trio) -> list[dict[str, Any]]:
    return [e for e in _audit(trio, "signing_route") if e["action"] == "signing_route.migrate"]


def _doc(body: dict[str, Any], doc_id: str) -> dict[str, Any]:
    return next(d for d in body["docs"] if d["doc_id"] == doc_id)


def _plan_route(trio: Trio) -> dict[str, Any]:
    resp = trio.call(trio.author, "GET", f"{trio.project.base}/signature-plan", params={"profile_id": TOPIC})
    assert resp.status_code == 200, resp.text
    route: dict[str, Any] = resp.json()["route"]
    return route


def _pdf_text(data: bytes) -> str:
    return "".join(page.extract_text() for page in PdfReader(io.BytesIO(data)).pages)


@dataclass(frozen=True)
class _Prod:
    trio: Trio
    sent: dict[str, str]
    manual_frozen: str
    sent_at: str


async def _production_route(stand: Stand, *, archived: bool = True, **row: Any) -> _Prod:
    """Маршрут прода на 0.20.0: второй шаг из трёх, ручная фиксация заявления от 09.11 из прежней сборки.

    `archived` сборки до отправки лежат в архиве сборок (иначе только файлы на месте, как после сборки, которой
    архив уже не помнит).
    """
    trio = await make_trio(stand, images=("author", "supervisor", "academic_supervisor"))
    build = (lambda doc_id, text: _build(stand, trio, doc_id, text)) if archived else trio.project.build
    # 09.11: автор собрал заявление и сам зафиксировал его для подписи.
    build(APPLICATION, "draft 09.11")
    frozen = trio.call(trio.author, "POST", f"{trio.project.base}/docs/{APPLICATION}/frozen")
    assert frozen.status_code == 200, frozen.text
    manual_frozen = trio.frozen_sha()[APPLICATION]
    # 10.11: правки, сборки, отправка; автор на первом шаге согласовал отправкой.
    build(APPLICATION, "sent 10.11")
    build(PROPOSAL, "sent 10.11")
    trio.sent()
    sent = await _as_sent_on_0_20_0(stand, trio, **row)
    route = trio.route()
    assert [_doc(route, d)["sent"] for d in (PROPOSAL, APPLICATION)] == [None, None]
    return _Prod(trio, sent, manual_frozen, route["sent_at"])


# --- прод: маршрут идёт, сборки после отправки с правками и без -------------------------------------------------------


async def test__production_route__rebuilt_with_and_without_changes__pinned_from_build_and_archive_and_goes_on(
    stand: Stand,
) -> None:
    prod = await _production_route(stand)
    trio = prod.trio
    assert (trio.route()["status"], states(trio.route())) == ("active", ["done", "to_approve", "waiting"])
    frozen_before, withheld_before, events_before = trio.frozen_sha(), trio.withheld(), trio.events()
    updated_before = trio.route()["updated_at"]
    # Ручная фиксация 09.11 сделана из прежней сборки и осталась как есть.
    assert frozen_before[APPLICATION] == prod.manual_frozen
    # После отправки: заявление пересобрано без правок, предложение дважды с правками.
    assert _rebuild_same(stand, trio, APPLICATION) == prod.sent[APPLICATION]
    assert _build(stand, trio, PROPOSAL, "after 10.11 v2") != prod.sent[PROPOSAL]
    _build(stand, trio, PROPOSAL, "after 10.11 v3")

    # Разовая задача лидера при старте.
    assert _migrate_all(stand) == 1

    # Версия на подписи это ровно то, что ушло подписантам: заявление из текущей сборки, предложение из архива.
    pinned = trio.state()["pinned"]
    assert {doc_id: v["sha256"] for doc_id, v in pinned.items()} == prod.sent
    for doc_id, version in pinned.items():
        assert (version["route_id"], version["round"]) == (trio.route_id, 1)
        assert datetime.fromisoformat(version["pinned_at"]) == datetime.fromisoformat(prod.sent_at)
        assert _sha(trio.project.folder / version["path"]) == prod.sent[doc_id]
    assert "sent 10.11" in _pdf_text((trio.project.folder / pinned[PROPOSAL]["path"]).read_bytes())

    # Маршрут идёт как шёл: ни событий, ни записи маршрута, ни уведомлений; согласие автора и картинки на месте.
    route = trio.route()
    assert (route["status"], route["stop_reason"], route["updated_at"]) == ("active", None, updated_before)
    assert trio.events() == events_before == ["sent", "approved"]
    assert states(route) == ["done", "to_approve", "waiting"]
    assert (trio.frozen_sha(), trio.withheld()) == (frozen_before, withheld_before)
    assert notifications(stand, trio, "author", "signing_paused") == []
    # Отправленная версия видна, правки предложения после отправки тоже.
    assert _doc(route, PROPOSAL)["sent"]["sha256"] == prod.sent[PROPOSAL]
    assert datetime.fromisoformat(_doc(route, APPLICATION)["sent"]["at"]) == datetime.fromisoformat(prod.sent_at)
    assert ([_doc(route, d)["changed"] for d in (PROPOSAL, APPLICATION)], route["changed_docs"]) == (
        [True, False],
        [PROPOSAL],
    )
    assert _plan_route(trio)["changed_docs"] == [PROPOSAL]

    [migrated] = _migrations(trio)
    assert migrated["actor_id"] is None
    details = migrated["details"]
    assert (details["route_id"], details["outcome"], details["docs"], details["lost"]) == (
        trio.route_id,
        "pinned",
        [PROPOSAL, APPLICATION],
        [],
    )
    assert {r["doc_id"]: (r["from"], r["sha256"]) for r in details["restored"]} == {
        PROPOSAL: ("archive", prod.sent[PROPOSAL]),
        APPLICATION: ("build", prod.sent[APPLICATION]),
    }

    # Повтор задачи, сверка и хуки ничего не меняют и аудит не дописывают.
    assert _migrate_all(stand) == 0
    assert sweep(stand) == 0
    project_changed(stand, trio)
    _build(stand, trio, PROPOSAL, "after 10.11 v4")
    assert sweep(stand) == 0
    assert trio.state()["pinned"] == pinned
    assert len(_migrations(trio)) == 1
    assert trio.route()["updated_at"] == updated_before

    # Подписант видит отправленную версию, согласует её, маршрут доходит до конца.
    task = trio.task(trio.supervisor)
    assert my(task) == ("to_approve", "approve")
    proposal = trio.call(trio.supervisor, "GET", _doc(task, PROPOSAL)["pdf_url"])
    assert proposal.status_code == 200, proposal.text
    assert "sent 10.11" in _pdf_text(proposal.content)
    assert "v4" not in _pdf_text(proposal.content)
    trio.approved(trio.supervisor)
    trio.approved(trio.academic)
    done = trio.route()
    assert (done["status"], done["changed_docs"]) == ("completed", [PROPOSAL])
    assert trio.events() == ["sent", "approved", "approved", "approved", "completed"]
    assert trio.state()["pinned"] == pinned


async def test__production_route__nothing_rebuilt__migration_is_silent(stand: Stand) -> None:
    prod = await _production_route(stand)
    trio = prod.trio
    before = trio.route()

    # Ленивый путь: первая же сверка переносит маршрут (задача лидера ещё не дошла).
    assert sweep(stand) == 1

    assert {doc_id: v["sha256"] for doc_id, v in trio.state()["pinned"].items()} == prod.sent
    after = trio.route()
    assert (after["status"], after["updated_at"], after["changed_docs"]) == ("active", before["updated_at"], [])
    assert trio.events() == ["sent", "approved"]
    assert [r["from"] for r in _migrations(trio)[0]["details"]["restored"]] == ["build", "build"]
    assert _migrate_all(stand) == 0
    assert len(_migrations(trio)) == 1


# --- версию не восстановить -------------------------------------------------------------------------------------------


async def test__sent_version_lost__route_stops_with_sent_changed__new_version_keeps_other_approvals(
    stand: Stand,
) -> None:
    # Сборки до отправки архив не помнит: предложение, пересобранное с правками, восстановить не из чего.
    prod = await _production_route(stand, archived=False)
    trio = prod.trio
    _build(stand, trio, PROPOSAL, "after 10.11 v2")
    frozen_before = trio.frozen_sha()

    assert sweep(stand) == 1

    route = trio.route()
    assert (route["status"], route["stop_reason"]) == ("paused", "sent_changed")
    assert [(e["kind"], e["reason"]) for e in route["events"]][-1] == ("paused", "sent_changed")
    # Заявление, которое восстановить можно, перенесено: его согласие и подписи остаются.
    pinned = trio.state()["pinned"]
    assert {doc_id: v["sha256"] for doc_id, v in pinned.items()} == {APPLICATION: prod.sent[APPLICATION]}
    assert (_doc(route, PROPOSAL)["sent"], _doc(route, PROPOSAL)["changed"]) == (None, True)
    assert _doc(route, APPLICATION)["changed"] is False
    assert trio.frozen_sha() == frozen_before
    [migrated] = _migrations(trio)
    assert (migrated["details"]["outcome"], migrated["details"]["lost"]) == ("needs_new_version", [PROPOSAL])
    assert len(notifications(stand, trio, "author", "signing_paused")) == 1

    # Повторы ничего не пишут.
    assert _migrate_all(stand) == 0
    assert sweep(stand) == 0
    assert len(_migrations(trio)) == 1
    assert trio.events() == ["sent", "approved", "paused"]

    # «Отправить новую версию»: изменилось только предложение, согласие автора на заявлении переносится.
    preview = trio.preview()
    assert preview["can_send"] is True
    assert {d["doc_id"]: d["change"] for d in preview["docs"]} == {PROPOSAL: "changed", APPLICATION: "same"}
    assert {p["persona"]: p["keeps_approval"] for p in preview["participants"]}["author"] is True
    resent = trio.sent()
    assert (resent["status"], resent["round"]) == ("active", 2)
    assert states(resent) == ["done", "to_approve", "waiting"]
    after = trio.state()["pinned"]
    assert after[APPLICATION] == pinned[APPLICATION]
    assert after[PROPOSAL]["round"] == 2
    assert after[PROPOSAL]["sha256"] == _sha(trio.project.folder / _output(trio, PROPOSAL))


# --- остановлен на 0.20.0 по пересборке ---------------------------------------------------------------------------


async def test__stopped_by_rebuild_on_0_20_0__stays_stopped__pinned_and_offers_new_version(stand: Stand) -> None:
    prod = await _production_route(stand, status="paused", phase=None, stop_reason="rebuilt")
    trio = prod.trio
    _build(stand, trio, PROPOSAL, "after 10.11 v2")
    before = trio.route()
    assert (before["status"], before["stop_reason"], before["changed_docs"]) == ("paused", "rebuilt", [PROPOSAL])

    assert _migrate_all(stand) == 1

    route = trio.route()
    assert (route["status"], route["stop_reason"], route["updated_at"]) == ("paused", "rebuilt", before["updated_at"])
    assert trio.events() == ["sent", "approved"]
    assert {doc_id: v["sha256"] for doc_id, v in trio.state()["pinned"].items()} == prod.sent
    assert (_doc(route, PROPOSAL)["sent"]["sha256"], route["changed_docs"]) == (prod.sent[PROPOSAL], [PROPOSAL])
    assert _migrations(trio)[0]["details"]["outcome"] == "pinned"
    assert _migrate_all(stand) == 0
    assert len(_migrations(trio)) == 1

    preview = trio.preview()
    assert {d["doc_id"]: d["change"] for d in preview["docs"]} == {PROPOSAL: "changed", APPLICATION: "same"}
    resent = trio.sent()
    assert (resent["status"], resent["round"], states(resent)) == ("active", 2, ["done", "to_approve", "waiting"])
    assert resent["changed_docs"] == []


async def test__stopped_on_0_20_0__version_lost__nothing_written_and_new_version_offered(stand: Stand) -> None:
    prod = await _production_route(stand, archived=False, status="paused", phase=None, stop_reason="rebuilt")
    trio = prod.trio
    trio.project.build(PROPOSAL, "after 10.11 v2")
    trio.project.build(APPLICATION, "after 10.11 v2")

    assert _migrate_all(stand) == 0

    route = trio.route()
    assert (route["status"], route["stop_reason"]) == ("paused", "rebuilt")
    assert trio.state().get("pinned", {}) == {}
    assert route["changed_docs"] == [PROPOSAL, APPLICATION]
    assert _migrations(trio) == []
    assert trio.preview()["can_send"] is True


# --- после переноса: подмена версии на подписи мимо маршрута ----------------------------------------------------------


async def test__after_migration__sent_version_replaced_outside_the_route__paused_with_sent_changed(
    stand: Stand,
) -> None:
    prod = await _production_route(stand)
    trio = prod.trio
    assert _migrate_all(stand) == 1

    trio.project.replace_sent(PROPOSAL)
    project_changed(stand, trio)

    route = trio.route()
    assert (route["status"], route["stop_reason"]) == ("paused", "sent_changed")
    # Перенос подменённую версию не «чинит»: она снята, записи в аудите о переносе больше не появляются.
    assert _migrate_all(stand) == 0
    assert len(_migrations(trio)) == 1


# --- ленивый перенос в действии подписанта --------------------------------------------------------------------------


async def test__signer_acts_before_any_migration__route_migrated_first_and_approval_goes_through(
    stand: Stand,
) -> None:
    prod = await _production_route(stand)
    trio = prod.trio
    _build(stand, trio, PROPOSAL, "after 10.11 v2")
    assert trio.image(trio.supervisor).status_code == 200

    # Научрук открыл страницу до пересборки: согласует то, что ему отправили.
    sent_tokens = {doc_id: f"build:{sha}" for doc_id, sha in prod.sent.items()}
    approved = trio.approved(trio.supervisor, expected=sent_tokens)

    assert approved["route"]["status"] == "active"
    assert my(approved) == ("done", "done")
    assert {doc_id: v["sha256"] for doc_id, v in trio.state()["pinned"].items()} == prod.sent
    assert trio.events() == ["sent", "approved", "approved"]
    [migrated] = _migrations(trio)
    assert (migrated["actor_id"], migrated["details"]["outcome"]) == (None, "pinned")
    assert _migrate_all(stand) == 0
