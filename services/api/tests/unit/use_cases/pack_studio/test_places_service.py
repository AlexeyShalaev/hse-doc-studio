"""Сценарий мест подписей (срез T9): правка идёт по якорям сборки её документа, ошибки правки это `place_invalid`.

Файлы и предпросмотр подменены: здесь проверяется связка сценария, а не запись на диск и сборка.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
import yaml
from hse_doc_studio.api.routers.v1.pack_studio_places import places_response
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.file_version import file_etag
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.paths import VersionRef
from hse_doc_studio.core.pack_studio.places import (
    MAX_PLACE_OPS,
    AnchorView,
    PlaceBox,
    PlaceOp,
    PlaceOpKind,
    anchor_views,
)
from hse_doc_studio.core.pack_studio.preview import PreviewAuthor, PreviewBuild, PreviewStatus
from hse_doc_studio.core.signatures.anchors import AnchorKind, BuildAnchor, BuildAnchors
from hse_doc_studio.infra.pack_studio.places import PackPlacesEditor
from hse_doc_studio.use_cases.pack_studio.files import PackFile, WrittenFile
from hse_doc_studio.use_cases.pack_studio.places import PackPlacesService, PlacesView

ACTOR = Actor.local()
WS = uuid4()
PATH = "p/templates/t/versions/1.0.1/version.yaml"

TEXT = """\
documents: [report]
signatures:
  slots:
    - id: supervisor
      applies_to: [report]
      default_placement: { page: 1, x_mm: 110, y_mm: 130, width_mm: 40 }
"""

ANCHORS = BuildAnchors(pdf_sha256="b" * 64, anchors=(BuildAnchor("supervisor", AnchorKind.sign, 1, 60.0, 180.0, 40.0),))


class FakeFiles:
    def __init__(self) -> None:
        self.text = TEXT
        self.if_match: list[str | None] = []

    async def read(self, actor: Actor, workspace_id: UUID, raw_path: str) -> PackFile:
        assert raw_path == PATH
        data = self.text.encode("utf-8")
        return PackFile(raw_path, data, file_etag(data), None)

    async def edit_yaml(
        self, actor: Actor, workspace_id: UUID, raw_path: str, edit: Callable[[str], str], if_match: str | None
    ) -> WrittenFile:
        assert raw_path == PATH
        self.if_match.append(if_match)
        self.text = edit(self.text)
        data = self.text.encode("utf-8")
        return WrittenFile(raw_path, file_etag(data), len(data), content=self.text)


class FakePreviews:
    def __init__(self, document: str) -> None:
        self.build = PreviewBuild(
            id=uuid4(),
            owner_id=None,
            workspace_id=WS,
            pack="p",
            template="t",
            version="1.0.1",
            document=document,
            example="auto:normal",
            combination={},
            key="k",
            status=PreviewStatus.succeeded,
            cached=False,
            created_at=datetime.now(UTC),
            has_anchors=True,
        )
        self.anchors = ANCHORS

    async def places_source(
        self, actor: Actor, workspace_id: UUID, build_id: UUID, ref: VersionRef
    ) -> tuple[PreviewBuild, BuildAnchors | None]:
        assert build_id == self.build.id
        assert (ref.pack, ref.template, ref.version) == ("p", "t", "1.0.1")
        return self.build, self.anchors


def _service(document: str = "report") -> tuple[PackPlacesService, FakeFiles, FakePreviews]:
    files = FakeFiles()
    previews = FakePreviews(document)
    service = PackPlacesService(files, previews, PackPlacesEditor())  # type: ignore[arg-type]
    return service, files, previews


def _placements(text: str) -> Any:
    return yaml.safe_load(text)["signatures"]["slots"][0].get("placements")


async def test__get__frames_by_the_anchors_of_the_build() -> None:
    service, _, previews = _service()

    view = await service.get(ACTOR, WS, "p", "t", "1.0.1", previews.build.id)

    assert view.path == PATH
    assert view.places.document == "report"
    assert view.places.anchors_known is True
    assert view.places.slots[0].document is not None


TEAM_ANCHORS = BuildAnchors(
    pdf_sha256="c" * 64,
    anchors=(
        BuildAnchor("author__ivanov", AnchorKind.sign, 1, 104.0, 230.0, 70.0),
        BuildAnchor("author__ivanov.day", AnchorKind.date, 1, 106.0, 238.0, 8.0),
        BuildAnchor("author__petrova", AnchorKind.sign, 1, 104.0, 252.0, 70.0),
        BuildAnchor("supervisor", AnchorKind.sign, 1, 60.0, 180.0, 40.0),
    ),
)
TEAM = (PreviewAuthor("ivanov", "Иванов Иван Иванович"), PreviewAuthor("petrova", "Петрова Мария Сергеевна"))


async def test__get__team_build__author_anchors_read_as_the_slot_and_the_author_name() -> None:
    service, _, previews = _service()
    previews.build = replace(previews.build, authors=TEAM)
    previews.anchors = TEAM_ANCHORS

    places = (await service.get(ACTOR, WS, "p", "t", "1.0.1", previews.build.id)).places

    # Сырые id остаются как были: по ним места привязаны в шаблоне.
    assert places.sign_anchors == ("author__ivanov", "author__petrova", "supervisor")
    assert places.date_anchors == ("author__ivanov.day",)
    assert places.anchor_views == (
        AnchorView("author__ivanov", AnchorKind.sign, "author", None, "ivanov", "Иванов Иван Иванович"),
        AnchorView("author__petrova", AnchorKind.sign, "author", None, "petrova", "Петрова Мария Сергеевна"),
        AnchorView("supervisor", AnchorKind.sign, "supervisor"),
        AnchorView("author__ivanov.day", AnchorKind.date, "author", "day", "ivanov", "Иванов Иван Иванович"),
    )
    build = places_response(WS, PlacesView(VersionRef("p", "t", "1.0.1"), PATH, '"e"', None, previews.build, places))
    assert build.build is not None
    assert [(a.id, a.kind, a.slot, a.part, a.author, a.author_name) for a in build.build.anchor_views] == [
        ("author__ivanov", "sign", "author", None, "ivanov", "Иванов Иван Иванович"),
        ("author__petrova", "sign", "author", None, "petrova", "Петрова Мария Сергеевна"),
        ("supervisor", "sign", "supervisor", None, None, None),
        ("author__ivanov.day", "date", "author", "day", "ivanov", "Иванов Иван Иванович"),
    ]


async def test__get__build_that_does_not_know_its_authors__slug_without_a_name() -> None:
    service, _, previews = _service()
    previews.anchors = TEAM_ANCHORS

    places = (await service.get(ACTOR, WS, "p", "t", "1.0.1", previews.build.id)).places

    assert places.anchor_views[0] == AnchorView("author__ivanov", AnchorKind.sign, "author", None, "ivanov", None)


async def test__get__without_a_build__no_anchor_views() -> None:
    service, _, _ = _service()

    places = (await service.get(ACTOR, WS, "p", "t", "1.0.1", None)).places

    assert (places.sign_anchors, places.anchor_views) == ((), ())


def test__anchor_views__malformed_author_names_stay_plain_slots() -> None:
    views = anchor_views(["author__", "__ivanov", "co_author"], ["supervisor.month_word"], {"ivanov": "Иванов"})

    assert [(v.slot, v.author, v.part) for v in views] == [
        ("author__", None, None),
        ("__ivanov", None, None),
        ("co_author", None, None),
        ("supervisor", None, "month_word"),
    ]


async def test__edit__new_place_lands_on_the_line_of_the_build() -> None:
    service, files, previews = _service()
    op = PlaceOp(PlaceOpKind.set_place, "supervisor", "report", box=PlaceBox(1, 60, 170, 40))

    view = await service.edit(ACTOR, WS, "p", "t", "1.0.1", previews.build.id, [op], '"etag"')

    assert files.if_match == ['"etag"']
    assert _placements(files.text) == {
        "report": {"anchor": "supervisor", "align": "left", "page": 1, "x_mm": 60, "y_mm": 170, "width_mm": 40}
    }
    assert view.etag == file_etag(files.text.encode("utf-8"))
    assert view.places.slots[0].document is not None


async def test__edit__anchors_of_another_document_are_not_used() -> None:
    service, files, previews = _service(document="memo")
    op = PlaceOp(PlaceOpKind.set_place, "supervisor", "report", box=PlaceBox(1, 60, 170, 40))

    await service.edit(ACTOR, WS, "p", "t", "1.0.1", previews.build.id, [op], None)

    assert _placements(files.text) == {"report": {"page": 1, "x_mm": 60, "y_mm": 170, "width_mm": 40}}


async def test__edit__impossible_edit_is_place_invalid_and_keeps_the_text() -> None:
    service, files, _ = _service()
    op = PlaceOp(PlaceOpKind.remove_place, "supervisor", "report")

    with pytest.raises(PackStudioError) as caught:
        await service.edit(ACTOR, WS, "p", "t", "1.0.1", None, [op], None)

    assert caught.value.code is PackStudioErrorCode.place_invalid
    assert "no place of its own" in str(caught.value.ctx["reason"])
    assert files.text == TEXT


async def test__edit__too_many_operations_are_refused() -> None:
    service, _, _ = _service()
    ops = [PlaceOp(PlaceOpKind.remove_place, "supervisor", "report")] * (MAX_PLACE_OPS + 1)

    with pytest.raises(PackStudioError) as caught:
        await service.edit(ACTOR, WS, "p", "t", "1.0.1", None, ops, None)

    assert caught.value.code is PackStudioErrorCode.place_invalid
