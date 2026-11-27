"""Рамки авторов команды в `pack_signature_check` и `pack_signature_render` (signing-route.md, 15.17.20).

Слот `per_author` на сборке, где шаблон ставит строку на каждого автора (`author__<слаг>`), проверяется и рисуется
рамкой на автора (`author--<слаг>`); без таких строк одна рамка слота, как раньше.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from hse_doc_studio.core.access.entities import Actor, ActorSource
from hse_doc_studio.core.catalog import AnchorDate, AnchorPlace, SignatureDefaultPlacement
from hse_doc_studio.core.enums import AnchorState, DateMarkAlign, DateMarkFormat
from hse_doc_studio.core.pack_studio.places import AnchorRef, DocDate, DocFrame, FrameKind, SlotPlaces
from hse_doc_studio.core.pack_studio.preview import PreviewAuthor
from hse_doc_studio.core.pack_studio.sign_check import PlaceKind
from hse_doc_studio.core.signatures.anchors import AnchorKind, BuildAnchor, BuildAnchors
from hse_doc_studio.use_cases.pack_studio.place_check import PackPlaceCheckService, _authors, _of_anchor, _of_slot

pytestmark = pytest.mark.unit

ENTRY = AnchorPlace("author", align=DateMarkAlign.centered, dy_mm=-11, width_mm=35)
DAY = AnchorDate("author.day", format=DateMarkFormat.day)
IVANOV = BuildAnchor("author__ivanov", AnchorKind.sign, 1, 104.0, 230.0, 70.0)
PETROV = BuildAnchor("author__petrov", AnchorKind.sign, 1, 104.0, 252.0, 70.0)
IVANOV_DAY = BuildAnchor("author__ivanov.day", AnchorKind.date, 1, 106.0, 238.0, 8.0)
OLD = BuildAnchor("author", AnchorKind.sign, 1, 104.0, 230.0, 70.0)
FIRST = SignatureDefaultPlacement(page=1, x_mm=121.5, y_mm=219.0, width_mm=35.0)


def _slot(*, per_author: bool = True) -> tuple[SlotPlaces, DocFrame]:
    frame = DocFrame(
        kind=FrameKind.default,
        entry=ENTRY,
        box=FIRST,
        anchor=AnchorRef("author", AnchorState.found),
        dates=(DocDate(0, DAY, None, AnchorRef("author.day", AnchorState.found)),),
    )
    slot = SlotPlaces(
        id="author",
        label={"ru": "Автор работы"},
        applies_to=("shared_technical_specification",),
        per_author=per_author,
        required=False,
        default_place=ENTRY,
        default_set=True,
        places=(),
        dates=(),
        document=frame,
    )
    return slot, frame


def _anchors(*lines: BuildAnchor) -> BuildAnchors:
    return BuildAnchors("e" * 64, lines)


def test__authors__frame_per_author_on_his_line() -> None:
    slot, frame = _slot()

    first, second = _authors(slot, frame, _anchors(IVANOV, IVANOV_DAY, PETROV))

    assert (first.slot, first.anchor, first.box) == ("author--ivanov", "author__ivanov", FIRST)
    assert first.label == "Автор работы — ivanov"
    assert first.dates[0] is not None
    assert first.dates[0].y_mm == 233.0
    assert (second.slot, second.anchor, second.anchor_state) == ("author--petrov", "author__petrov", AnchorState.found)
    assert second.box == SignatureDefaultPlacement(page=1, x_mm=121.5, y_mm=241.0, width_mm=35.0)
    assert second.dates == (None,)  # строки даты Петрова в сборке нет


@pytest.mark.parametrize(
    ("per_author", "lines"),
    [(True, (OLD,)), (False, (IVANOV, PETROV)), (True, ())],
    ids=["old_build", "slot_not_per_author", "no_lines"],
)
def test__authors__one_frame_of_the_slot_as_before(per_author: bool, lines: tuple[BuildAnchor, ...]) -> None:
    slot, frame = _slot(per_author=per_author)

    (only,) = _authors(slot, frame, _anchors(*lines))

    assert (only.slot, only.anchor, only.box, only.anchor_state) == ("author", "author", FIRST, AnchorState.found)


def test__slot_filter__covers_the_authors_of_the_slot() -> None:
    assert _of_slot("author--ivanov", "author")
    assert _of_slot("author", "author")
    assert not _of_slot("supervisor", "author")
    assert _of_anchor("author__ivanov", "author")
    assert not _of_anchor("co_author", "author")


def test__authors__label_carries_the_name_the_build_knows() -> None:
    slot, frame = _slot()

    first, second = _authors(slot, frame, _anchors(IVANOV, PETROV), {"ivanov": "Иванов Иван Иванович"})

    assert (first.slot, first.label) == ("author--ivanov", "Автор работы — Иванов Иван Иванович")
    # Имени автора сборка не знает: остаётся слаг.
    assert (second.slot, second.label) == ("author--petrov", "Автор работы — petrov")


@pytest.mark.parametrize(
    ("authors", "labels"),
    [
        (
            (PreviewAuthor("ivanov", "Иванов Иван"), PreviewAuthor("petrov", "Петров Пётр")),
            ["Автор работы — Иванов Иван", "Автор работы — Петров Пётр"],
        ),
        # Старая сборка авторов не помнит.
        ((), ["Автор работы — ivanov", "Автор работы — petrov"]),
    ],
    ids=["build_knows", "old_build"],
)
async def test__inspect__author_frames_are_named_after_the_build_authors(
    tmp_path: Path, authors: tuple[PreviewAuthor, ...], labels: list[str]
) -> None:
    slot, _ = _slot()
    anchors = _anchors(IVANOV, PETROV)
    build = SimpleNamespace(document="shared_technical_specification", authors=authors)
    pdf = tmp_path / "document.pdf"
    pdf.write_bytes(b"%PDF-1.5")
    view = SimpleNamespace(build=build, places=SimpleNamespace(slots=(slot,)))

    async def get(*_: object) -> object:
        return view

    async def places_source(*_: object) -> object:
        return build, anchors

    async def built_pdf(*_: object) -> Path:
        return pdf

    pages = SimpleNamespace(page_count=lambda _: 1, layouts=lambda *_: {}, ink=lambda *_: [])
    service = PackPlaceCheckService(
        SimpleNamespace(get=get),  # type: ignore[arg-type]
        SimpleNamespace(places_source=places_source, pdf=built_pdf),  # type: ignore[arg-type]
        pages,  # type: ignore[arg-type]
    )
    actor = Actor.user("u1", source=ActorSource.pat, scopes=frozenset({"mcp", "packs"}))

    inspection, _ = await service.inspect(actor, uuid4(), "demo", "report", "2026.1.1", uuid4())

    assert [place.label for place in inspection.places if place.kind is PlaceKind.sign] == labels
