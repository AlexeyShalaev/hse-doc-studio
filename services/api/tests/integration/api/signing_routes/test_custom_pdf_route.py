"""Документ со своим PDF («Заменить на свой файл») в маршруте подписания, плане подписей и пакете.

Свой файл замещает шаблонный результат сборки целиком: список документов, карточка документа и пакет берут его.
Источник подписи тот же файл, иначе черновик маршрута считал бы документ несобранным (шаблонного PDF нет) или,
хуже, собранным по старой шаблонной сборке, а фиксация и подписи шли бы не по тому PDF, который загрузил автор.
"""

from __future__ import annotations

import hashlib
import io
from typing import Any

import pytest
from reportlab.pdfgen import canvas

from tests.integration.api.signing_routes.stand import (
    TOPIC,
    TOPIC_DOCS,
    TOPIC_PAIRS,
    Person,
    Project,
    Stand,
    make_project,
    person,
)

pytestmark = [pytest.mark.pg, pytest.mark.timeout(240)]

PROPOSAL, APPLICATION = TOPIC_DOCS


def _pdf(text: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(100, 700, text)
    c.save()
    return buf.getvalue()


def _upload(project: Project, doc_id: str, name: str, blob: bytes) -> str:
    resp = project.call(
        project.owner,
        "POST",
        f"{project.base}/documents/{doc_id}/custom-file",
        files={"file": (name, blob, "application/pdf")},
    )
    assert resp.status_code == 200, resp.text
    return str(resp.json()["custom_file"]["stored_path"])


def _listed(project: Project) -> dict[str, dict[str, Any]]:
    resp = project.call(project.owner, "GET", f"{project.base}/documents")
    assert resp.status_code == 200, resp.text
    return {d["id"]: d for d in resp.json()}


async def _custom_project(stand: Stand) -> tuple[Project, Person, dict[str, bytes]]:
    """Сценарий пользователя: заявка когда-то собрана шаблоном, потом оба документа заменены своими PDF."""
    author = await person(stand, "Иванов Иван Иванович")
    project = make_project(stand, author, supervisor={"name": "Петров Пётр Петрович", "role": "university"})
    # Шаблонная сборка заявки до замены: её PDF остаётся на диске рядом со своим файлом.
    project.build(PROPOSAL, "template build")
    uploads = {PROPOSAL: _pdf("my proposal"), APPLICATION: _pdf("my application")}
    for doc_id, blob in uploads.items():
        _upload(project, doc_id, f"{doc_id} мой.pdf", blob)
    return project, author, uploads


async def test__custom_pdf__draft_plan_and_list_agree_built_by_the_uploaded_file(stand: Stand) -> None:
    project, author, uploads = await _custom_project(stand)
    listed = _listed(project)
    created = project.call(author, "POST", project.routes, json={"profile_id": TOPIC})
    assert created.status_code == 201, created.text
    route_id = created.json()["id"]

    preview = project.call(author, "POST", f"{project.routes}/{route_id}/preview", json={}).json()
    plan = project.call(author, "GET", f"{project.base}/signature-plan", params={"profile_id": TOPIC})
    assert plan.status_code == 200, plan.text

    sha = {doc_id: hashlib.sha256(blob).hexdigest() for doc_id, blob in uploads.items()}
    assert {d: listed[d]["output_file"].split("/_custom/")[0] for d in TOPIC_DOCS} == {d: d for d in TOPIC_DOCS}
    assert {d["doc_id"]: d["built"] for d in preview["docs"]} == {PROPOSAL: True, APPLICATION: True}
    assert [b for b in preview["blockers"] if b["code"] == "not_built"] == []
    # Токен документа это хэш источника подписи: своего файла, а не старой шаблонной сборки.
    assert {d["doc_id"]: d["token"] for d in preview["docs"]} == {d: f"build:{sha[d]}" for d in TOPIC_DOCS}
    assert {d["doc_id"]: d["built"] for d in plan.json()["docs"]} == {PROPOSAL: True, APPLICATION: True}


async def test__custom_pdf__route_sends_and_completes_on_the_uploaded_file(stand: Stand) -> None:
    project, author, uploads = await _custom_project(stand)
    supervisor = await person(stand, "Петров Пётр Петрович")
    await project.member(supervisor, "reviewer", "supervisor")
    project.png(author, "author")
    project.png(author, "supervisor")
    project.place(author, *TOPIC_PAIRS)
    created = project.call(author, "POST", project.routes, json={"profile_id": TOPIC})
    assert created.status_code == 201, created.text
    route_id = created.json()["id"]
    preview = project.call(author, "POST", f"{project.routes}/{route_id}/preview", json={}).json()
    expected = {d["doc_id"]: d["token"] for d in preview["docs"]}

    sent = project.call(author, "POST", f"{project.routes}/{route_id}/send", json={"expected": expected, "sign": None})

    assert sent.status_code == 200, sent.text
    # Версия на подписи снята со своего файла, а не со старой шаблонной сборки заявки.
    pinned = {doc_id: (project.folder / f".hse-studio/frozen/{doc_id}.source.pdf").read_bytes() for doc_id in uploads}
    assert pinned == uploads

    task = project.call(supervisor, "GET", f"{project.routes}/{route_id}/task")
    assert task.status_code == 200, task.text
    tokens = {d["doc_id"]: d["token"] for d in task.json()["docs"] if d["token"] is not None}
    approved = project.call(
        supervisor,
        "POST",
        f"{project.routes}/{route_id}/task/approve",
        json={"expected": tokens, "method": None, "sign": None},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["route"]["status"] == "completed"

    plan = project.call(author, "GET", f"{project.base}/signature-plan", params={"profile_id": TOPIC}).json()
    assert {(d["doc_id"], s["slot_id"]): s["status"] for d in plan["docs"] for s in d["slots"]} == dict.fromkeys(
        TOPIC_PAIRS, "signed"
    )
