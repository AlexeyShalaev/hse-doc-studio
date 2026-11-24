"""Якоря на каждого автора команды (docs/design/signing-route.md, 15.17.20).

Шаблон ставит на строке каждого автора общего документа свой якорь `author__<слаг>`; сервер видит его как якорь
`author` рантайм-слота `author--<слаг>`. Старая сборка с одним якорем `author` ведёт себя как раньше.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from hse_doc_studio.core.catalog import AnchorDate, AnchorPlace, SignatureDefaultPlacement, SignatureSlotDef
from hse_doc_studio.core.entities import Document, Project
from hse_doc_studio.core.enums import DateMarkAlign, DateMarkFormat, ProjectStaffing
from hse_doc_studio.core.signatures.anchors import (
    AnchorKind,
    BuildAnchor,
    BuildAnchors,
    PdfPage,
    author_anchor_id,
    parse_positions,
    split_author_name,
)
from hse_doc_studio.core.signatures.pack_places import (
    SourceAnchors,
    anchor_ref,
    author_lines,
    pack_placement,
    pair_anchors,
    shared_author,
)
from hse_doc_studio.core.value_objects import Author

from tests.factories import make_document, make_project

pytestmark = pytest.mark.unit

SHA = "c" * 64
V = "2026.1.6"
GENERAL = SignatureDefaultPlacement(page=1, x_mm=104, y_mm=233, width_mm=35)
ENTRY = AnchorPlace("author", align=DateMarkAlign.centered, dy_mm=-11, width_mm=35, fallback=GENERAL)
DAY = AnchorDate("author.day", format=DateMarkFormat.day)
SLOT = SignatureSlotDef(
    id="author",
    label={"ru": "Автор работы"},
    applies_to=("shared_technical_specification", "technical_specification"),
    default_placement=GENERAL,
    per_author=True,
    placements=(("shared_technical_specification", ENTRY),),
    default_dates=(("shared_technical_specification", (DAY,)),),
)
# Лист утверждения ЕСПД, «Исполнители:» по строке на автора, одна под другой.
IVANOV = BuildAnchor("author__ivanov", AnchorKind.sign, 1, 104.0, 230.0, 70.0)
PETROV = BuildAnchor("author__petrov", AnchorKind.sign, 1, 104.0, 252.0, 70.0)
IVANOV_DAY = BuildAnchor("author__ivanov.day", AnchorKind.date, 1, 106.0, 238.0, 8.0)
PETROV_DAY = BuildAnchor("author__petrov.day", AnchorKind.date, 1, 106.0, 260.0, 8.0)
SUPERVISOR = BuildAnchor("supervisor", AnchorKind.sign, 1, 30.0, 120.0, 40.0)
# Старый шаблон: один якорь `author` на строке каждого автора, сборка берёт первый.
OLD = BuildAnchor("author", AnchorKind.sign, 1, 104.0, 230.0, 70.0)


def _src(*lines: BuildAnchor) -> SourceAnchors:
    return SourceAnchors(BuildAnchors(SHA, lines))


def _team(**doc: object) -> tuple[Project, Document]:
    shared = replace(make_document("shared_technical_specification"), **doc)
    project = replace(
        make_project(documents=[shared]),
        staffing=ProjectStaffing.team,
        authors=[Author(name="Иванов Иван", slug="ivanov"), Author(name="Петров Пётр", slug="petrov")],
    )
    return project, shared


# --- имена ---


def test__author_anchor_id__sign_and_date() -> None:
    assert author_anchor_id("author", "ivanov") == "author__ivanov"
    assert author_anchor_id("author.day", "ivanov") == "author__ivanov.day"


@pytest.mark.parametrize(
    ("name", "split"),
    [
        ("author__ivanov", ("author", "ivanov")),
        ("co_supervisor", ("co_supervisor", None)),
        ("author__", ("author__", None)),
        ("author__ivanov2", ("author", "ivanov2")),
    ],
)
def test__split_author_name(name: str, split: tuple[str, str | None]) -> None:
    assert split_author_name(name) == split


def test__positions__author_lines_parsed_like_any_anchor() -> None:
    raw = (
        b"hsepos 1 39158276 55380996\n"
        b"sign author__ivanov - 1 19723337 12003921 13017846\n"
        b"date author__ivanov day 1 19723337 11000000 1000000\n"
    )

    anchors = parse_positions(raw, [PdfPage(210.0, 297.0)], SHA)

    assert [a.id for a in anchors.anchors] == ["author__ivanov", "author__ivanov.day"]
    assert anchors.problems == ()


# --- якоря глазами автора ---


def test__for_author__own_line_under_the_slot_name_others_hidden() -> None:
    anchors = BuildAnchors(SHA, (SUPERVISOR, IVANOV, IVANOV_DAY, PETROV, PETROV_DAY))

    seen = anchors.for_author("petrov")

    assert {a.id for a in seen.anchors} == {"supervisor", "author", "author.day"}
    assert seen.get("author") == replace(PETROV, id="author")
    assert seen.get("author.day") == replace(PETROV_DAY, id="author.day")
    assert anchors.author_names() == frozenset({"author"})
    assert anchors.author_keys() == ("ivanov", "petrov")
    assert anchors.author_keys("author.day") == ("ivanov", "petrov")
    assert anchors.author_keys("supervisor") == ()


def test__for_author__shared_line_of_the_same_name_hidden_when_authors_have_lines() -> None:
    anchors = BuildAnchors(SHA, (OLD, IVANOV))

    assert anchors.for_author("petrov").get("author") is None
    assert anchors.for_author("ivanov").get("author") == replace(IVANOV, id="author")


def test__for_author__old_build_with_one_author_anchor__as_is() -> None:
    anchors = BuildAnchors(SHA, (OLD, SUPERVISOR))

    assert anchors.for_author("petrov") is anchors
    assert anchors.author_names() == frozenset()


def test__source_for_author__unknown_anchors_stay_unknown() -> None:
    assert SourceAnchors().for_author("ivanov") == SourceAnchors()
    assert not SourceAnchors().has_author_lines("author")


# --- место пака у пары ---


def test__shared_author__only_author_instance_on_a_shared_document_of_a_team() -> None:
    project, shared = _team()
    own = replace(make_document("technical_specification--ivanov"), def_id="technical_specification", owner="ivanov")
    solo = make_project(documents=[make_document("shared_technical_specification")])

    assert shared_author(project, shared, "author--ivanov") == "ivanov"
    assert shared_author(project, own, "author--ivanov") is None
    assert shared_author(project, shared, "supervisor") is None
    assert shared_author(solo, solo.documents[0], "author") is None


def test__pack_placement__each_author_on_own_line_with_own_date() -> None:
    project, shared = _team()
    src = _src(SUPERVISOR, IVANOV, IVANOV_DAY, PETROV, PETROV_DAY)

    ivanov = pack_placement(
        SLOT, "shared_technical_specification", None, V, pair_anchors(src, project, shared, "author--ivanov")
    )
    petrov = pack_placement(
        SLOT, "shared_technical_specification", None, V, pair_anchors(src, project, shared, "author--petrov")
    )

    assert ivanov is not None
    assert petrov is not None
    assert (ivanov.page, ivanov.x_mm, ivanov.y_mm, ivanov.width_mm) == (1, 121.5, 219.0, 35.0)
    assert (petrov.x_mm, petrov.y_mm) == (121.5, 241.0)
    assert [(d.y_mm, d.format) for d in ivanov.dates] == [(233.0, DateMarkFormat.day)]
    assert [d.y_mm for d in petrov.dates] == [255.0]
    assert ivanov.from_pack is not None
    assert ivanov.from_pack.anchor == "author"
    assert author_lines(SLOT, "shared_technical_specification", src)


def test__pack_placement__author_without_a_line__no_place() -> None:
    project, shared = _team()
    src = _src(IVANOV)

    placement = pack_placement(
        SLOT, "shared_technical_specification", None, V, pair_anchors(src, project, shared, "author--petrov")
    )

    assert placement is None
    ref = anchor_ref(SLOT, "shared_technical_specification", pair_anchors(src, project, shared, "author--petrov"))
    assert ref is not None
    assert ref.state.value == "missing"


def test__pack_placement__old_build__as_before_on_the_one_author_line() -> None:
    project, shared = _team()
    src = _src(OLD)

    scoped = pair_anchors(src, project, shared, "author--petrov")

    assert scoped == src
    assert pack_placement(SLOT, "shared_technical_specification", None, V, scoped) == pack_placement(
        SLOT, "shared_technical_specification", None, V, src
    )
    assert not author_lines(SLOT, "shared_technical_specification", src)


def test__author_lines__place_in_mm_or_unknown_anchors__no() -> None:
    mm = replace(SLOT, placements=(("shared_technical_specification", GENERAL),))

    assert not author_lines(mm, "shared_technical_specification", _src(IVANOV))
    assert not author_lines(SLOT, "shared_technical_specification", SourceAnchors())
    assert not author_lines(SLOT, "shared_technical_specification", SourceAnchors(own_pdf=True))
