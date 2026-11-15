"""Сценарий мест подписей (срез T9): правка идёт по якорям сборки её документа, ошибки правки это `place_invalid`.

Файлы и предпросмотр подменены: здесь проверяется связка сценария, а не запись на диск и сборка.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
import yaml
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.file_version import file_etag
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.paths import VersionRef
from hse_doc_studio.core.pack_studio.places import MAX_PLACE_OPS, PlaceBox, PlaceOp, PlaceOpKind
from hse_doc_studio.core.pack_studio.preview import PreviewBuild, PreviewStatus
from hse_doc_studio.core.signatures.anchors import AnchorKind, BuildAnchor, BuildAnchors
from hse_doc_studio.infra.pack_studio.places import PackPlacesEditor
from hse_doc_studio.use_cases.pack_studio.files import PackFile, WrittenFile
from hse_doc_studio.use_cases.pack_studio.places import PackPlacesService

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

    async def places_source(
        self, actor: Actor, workspace_id: UUID, build_id: UUID, ref: VersionRef
    ) -> tuple[PreviewBuild, BuildAnchors | None]:
        assert build_id == self.build.id
        assert (ref.pack, ref.template, ref.version) == ("p", "t", "1.0.1")
        return self.build, ANCHORS


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
