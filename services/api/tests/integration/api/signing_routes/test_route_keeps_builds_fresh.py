"""Маршрут подписания не делает сборки устаревшими и не останавливает сам себя.

Отправка, согласие с картинкой и автоматическая фиксация пишут только состояние подписей под `.hse-studio/`
(`signatures.json`, картинки, зафиксированные PDF). Это не входы сборки: PDF от них не меняется. Поэтому список
документов не должен показывать «устарела: проект изменился» (иначе человек нажмёт «Собрать всё», невоспроизводимая
сборка даст другой PDF, и маршрут, чья отправка ещё не снимает версию на подписи, встанет с `sent_changed`), а сверка
маршрута не должна видеть пересборку.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from tests.integration.api.signing_routes.signer_stand import (
    APPLICATION,
    PROPOSAL,
    FakeKeys,
    Trio,
    install_fake_keys,
    make_trio,
    my,
    states,
)
from tests.integration.api.signing_routes.stand import TOPIC_DOCS, Stand
from tests.integration.api.signing_routes.watch_stand import drain, pdf_built, project_changed, sweep

pytestmark = [pytest.mark.pg, pytest.mark.timeout(240)]


@pytest.fixture
def keys(monkeypatch: pytest.MonkeyPatch) -> FakeKeys:
    return install_fake_keys(monkeypatch)


def _builds(trio: Trio) -> dict[str, Any]:
    resp = trio.call(trio.author, "GET", f"{trio.project.base}/builds")
    assert resp.status_code == 200, resp.text
    return dict(resp.json())


def _fresh(trio: Trio) -> dict[str, bool | None]:
    return {d["doc_id"]: d["cloud"]["fresh"] for d in _builds(trio)["documents"] if d["doc_id"] in TOPIC_DOCS}


async def _stamp_builds(trio: Trio, commit: str) -> None:
    """Облачные сборки документов маршрута из версии `commit`, как их записывает хук удачной сборки."""
    finished = datetime.now(UTC) - timedelta(minutes=5)
    async with trio.stand.sessions.use() as db:
        for doc_id in TOPIC_DOCS:
            await db.execute(
                text(
                    "INSERT INTO compile_records (id, project_id, doc_id, engine, status, started_at, finished_at, "
                    "pages, check_results, log, source_commit, output_sha256, output_size) VALUES (:id, :p, :d, "
                    "'xelatex', 'success', :s, :f, 1, '[]', '', :c, :h, 10)"
                ),
                {
                    "id": uuid4(),
                    "p": UUID(trio.project.id),
                    "d": doc_id,
                    "s": finished - timedelta(minutes=1),
                    "f": finished,
                    "c": commit,
                    "h": "0" * 64,
                },
            )


async def test__send_approve_with_image_and_auto_freeze__builds_stay_fresh_and_route_runs(
    stand: Stand, keys: FakeKeys
) -> None:
    trio = await make_trio(
        stand, {"author": "detached", "supervisor": "detached"}, images=(), plates=("author", "supervisor")
    )
    head = _builds(trio)["head"]
    assert head is not None
    await _stamp_builds(trio, head)

    # Подготовка подписей автором (картинки, способы, размещения) тоже лежит под `.hse-studio/`.
    assert _fresh(trio) == {PROPOSAL: True, APPLICATION: True}

    sent = trio.sent()
    assert (sent["status"], sent["phase"]) == ("active", "approval")
    assert trio.withheld() == {APPLICATION: ["academic_supervisor"]}
    assert _fresh(trio) == {PROPOSAL: True, APPLICATION: True}

    assert my(trio.approved(trio.supervisor)) == ("waiting", "wait")
    assert trio.image(trio.academic).status_code == 200
    after_academic = trio.approved(trio.academic)

    # Согласие с картинкой последнего, кто меняет видимый слой, фиксирует документы: это запись маршрута.
    assert set(trio.frozen_sha()) == {PROPOSAL, APPLICATION}
    assert states(after_academic) == ["to_sign", "to_sign", "done"]
    # Дерево истории грязное (записи подписей), но входы сборки те же: «устарела» не показывается.
    assert _builds(trio)["dirty"] is True
    assert _fresh(trio) == {PROPOSAL: True, APPLICATION: True}

    # Сверка маршрута (хуки сборки и изменения проекта, периодическая) не принимает свои же записи за пересборку.
    drain(stand)
    pdf_built(stand, trio, APPLICATION)
    project_changed(stand, trio)
    assert sweep(stand) == 0
    route = trio.route()
    assert (route["status"], route["phase"], route["stop_reason"]) == ("active", "signing", None)
    assert trio.events() == ["sent", "approved", "approved", "approved", "frozen"]

    # Правка исходников по-прежнему делает сборку устаревшей.
    (trio.project.folder / "appendix.tex").write_text("\\section{Новое}\n", encoding="utf-8")
    assert _fresh(trio) == {PROPOSAL: False, APPLICATION: False}
