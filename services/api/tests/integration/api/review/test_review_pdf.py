"""Комментарии из превью PDF (раздел 2.4): привязка к исходнику через SyncTeX, PDF-якорь, места на PDF, права."""

from __future__ import annotations

import gzip
import uuid
from pathlib import Path, PurePosixPath
from typing import Any

import pytest
from hse_doc_studio.core.projects.locator import IProjectLocator

from tests.integration.api.review.conftest import NOTES, Review

pytestmark = pytest.mark.pg

# Страница 1: строка 2 файла notes.tex набрана на высоте 57..66 пт, строка 3 на 77..86 пт (пункты от верха).
_SYNCTEX = """SyncTeX Version:1
Input:1:/work/{main}
Input:2:/work/{notes}
Input:3:/usr/share/texmf/tex/latex/base/article.cls
Output:pdf
Magnification:1000
Unit:1
X Offset:0
Y Offset:0
Content:
{{1
[1,1:4736286,52633600:30785863,49000000,0
(2,2:4736286,4263256:30785863,500000,100000
h2,2:4736286,4263256:15000000,500000,100000
)
(2,3:4736286,5578891:30785863,500000,100000
)
]
}}1
Postamble:
"""
# Выделение «совместную правку» на строке 2 и чужой текст шаблона на той же высоте.
_ON_LINE_2 = {"x": 150.0, "y": 58.0, "width": 90.0, "height": 9.0}


def _project_folder(review: Review) -> Path:
    """Папка проекта на сервере: API её не показывает, берём у локатора в цикле приложения."""
    stand = review.world.stand

    async def folder() -> Path:
        container = stand.app.state.dishka_container  # type: ignore[attr-defined]
        found = await (await container.get(IProjectLocator)).folder_of(uuid.UUID(review.project))
        assert found is not None
        return Path(found)

    return Path(stand.portal.call(folder))  # type: ignore[attr-defined]


class PdfStand:
    def __init__(self, review: Review) -> None:
        self.review = review
        docs = review.world.anna.get(f"/api/v1/projects/{review.project}/documents").json()
        doc = next(d for d in docs if str(d.get("output_file") or "").endswith(".pdf") and d.get("source_file"))
        self.doc_id = str(doc["id"])
        self.source = str(doc["source_file"])
        self.pdf = str(doc["output_file"])
        self.folder = _project_folder(review)

    def write_pdf(self, content: bytes = b"%PDF-1.4 first build") -> None:
        target = self.folder / self.pdf
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    def write_synctex(self) -> None:
        src = PurePosixPath(self.source)
        target = self.folder / src.parent / ".build" / self.doc_id / f"{src.stem}.synctex.gz"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(gzip.compress(_SYNCTEX.format(main=self.source, notes=NOTES).encode()))

    def create(self, who: Any, fragment: str, rect: dict[str, float] | None = None, **extra: object) -> Any:
        body = {
            "doc_id": self.doc_id,
            "page": 1,
            "rects": [rect or _ON_LINE_2],
            "text": fragment,
            "body": "Поясните",
            **extra,
        }
        return who.post(f"{self.review.base}/pdf-threads", json=body)

    def placed(self, who: Any) -> dict[str, Any]:
        response = who.get(f"{self.review.base}/documents/{self.doc_id}")
        assert response.status_code == 200, response.text
        return dict(response.json())


@pytest.fixture
def pdf(review: Review) -> PdfStand:
    return PdfStand(review)


def test__selection_found_in_source__creates_text_thread_visible_in_editor(review: Review, pdf: PdfStand) -> None:
    pdf.write_pdf()
    pdf.write_synctex()

    created = pdf.create(review.rita, "совмест-\nную правку")

    assert created.status_code == 201, created.text
    thread = created.json()
    assert thread["path"] == NOTES
    assert thread["anchor"]["kind"] == "text"
    assert thread["anchor"]["quote"] == "совместную правку"
    listed = review.world.anna.get(f"{review.base}/threads", params={"path": NOTES}).json()["items"]
    assert [t["id"] for t in listed] == [thread["id"]]


def test__selection_not_in_source__falls_back_to_pdf_anchor(review: Review, pdf: PdfStand) -> None:
    pdf.write_pdf()
    pdf.write_synctex()

    created = pdf.create(review.rita, "Национальный исследовательский университет")

    assert created.status_code == 201, created.text
    thread = created.json()
    assert thread["path"] == pdf.pdf
    anchor = thread["anchor"]
    assert anchor["kind"] == "pdf"
    assert anchor["doc_id"] == pdf.doc_id
    assert anchor["page"] == 1
    assert anchor["rects"] == [_ON_LINE_2]
    assert anchor["text"] == "Национальный исследовательский университет"
    assert len(anchor["build_sha"]) == 64


def test__no_synctex__pdf_anchor_and_inbox_link_carries_document(review: Review, pdf: PdfStand) -> None:
    pdf.write_pdf()

    created = pdf.create(review.rita, "совместную правку")

    assert created.json()["anchor"]["kind"] == "pdf"
    [note] = review.inbox(review.world.anna, "review_thread")
    assert note["payload"]["doc_id"] == pdf.doc_id
    assert note["payload"]["path"] == pdf.pdf


def test__document_review__places_text_and_pdf_threads_and_notices_rebuild(review: Review, pdf: PdfStand) -> None:
    pdf.write_pdf()
    pdf.write_synctex()
    text_thread = pdf.create(review.rita, "совместную правку").json()
    pdf_thread = pdf.create(review.rita, "Колонтитул").json()

    first = pdf.placed(review.world.anna)
    pdf.write_pdf(b"%PDF-1.4 rebuilt")
    rebuilt = pdf.placed(review.world.anna)

    places = {i["thread"]["id"]: i["place"] for i in first["items"]}
    assert places[text_thread["id"]]["page"] == 1
    assert places[text_thread["id"]]["text"] == "совместную правку"
    assert places[text_thread["id"]]["exact"] is False
    [line] = places[text_thread["id"]]["rects"]
    assert 55 < line["y"] < 60
    assert places[pdf_thread["id"]]["exact"] is True
    assert first["build_sha"] == pdf_thread["anchor"]["build_sha"]
    after = {i["thread"]["id"]: i["place"] for i in rebuilt["items"]}
    assert after[pdf_thread["id"]]["exact"] is False
    assert rebuilt["build_sha"] != first["build_sha"]


def test__document_review__quote_removed_from_file__thread_listed_without_place(review: Review, pdf: PdfStand) -> None:
    pdf.write_pdf()
    pdf.write_synctex()
    thread = pdf.create(review.rita, "совместную правку").json()

    review.world.anna.put(f"/api/v1/projects/{review.project}/files/{NOTES}", content="Другой текст.\n".encode())
    placed = pdf.placed(review.world.anna)

    assert [(i["thread"]["id"], i["place"]) for i in placed["items"]] == [(thread["id"], None)]


def test__rights__reader_cannot_comment_or_read_and_editor_can(review: Review, pdf: PdfStand) -> None:
    pdf.write_pdf()

    assert pdf.create(review.world.gleb, "совместную правку").status_code == 403
    assert review.world.gleb.get(f"{review.base}/documents/{pdf.doc_id}").status_code == 403
    assert pdf.create(review.world.dina, "совместную правку").status_code == 404
    assert pdf.create(review.world.vera, "совместную правку").status_code == 201


@pytest.mark.parametrize(
    ("extra", "code"),
    [
        ({"text": "  "}, "empty_quote"),
        ({"rects": []}, "bad_rects"),
        ({"page": 0}, None),
        ({"body": " "}, "empty_body"),
    ],
)
def test__validation__bad_selection_is_rejected(
    review: Review, pdf: PdfStand, extra: dict[str, object], code: str | None
) -> None:
    pdf.write_pdf()

    response = pdf.create(review.rita, "совместную правку", **extra)

    assert response.status_code == 422
    if code is not None:
        assert response.json()["code"] == code


def test__document_without_built_pdf__conflict(review: Review, pdf: PdfStand) -> None:
    response = pdf.create(review.rita, "совместную правку")

    assert response.status_code == 409
    assert response.json()["code"] == "pdf_missing"


def test__unknown_document__not_found(review: Review, pdf: PdfStand) -> None:
    response = review.rita.post(
        f"{review.base}/pdf-threads",
        json={"doc_id": "nope", "page": 1, "rects": [_ON_LINE_2], "text": "x y z", "body": "?"},
    )

    assert response.status_code == 404
