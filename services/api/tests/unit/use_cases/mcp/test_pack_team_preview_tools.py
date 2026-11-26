"""Командный предпросмотр через MCP: выбор автора в `pack_preview_build`, блок `author` в `pack_read` и якоря авторов
словами в `pack_set_placement`. Службы подменены: проверяется, что тулы передают и показывают."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.access.entities import Actor, ActorSource
from hse_doc_studio.core.i18n import set_interface_language
from hse_doc_studio.core.pack_studio.paths import VersionRef
from hse_doc_studio.core.pack_studio.preview import PreviewBuild, PreviewStatus, PreviewSwitch
from hse_doc_studio.core.signatures.anchors import BuildAnchors
from hse_doc_studio.infra.pack_studio.places import PackPlacesEditor
from hse_doc_studio.use_cases.mcp.tools.packs import (
    PackPreviewBuildTool,
    PackSetPlacementTool,
    _author_arg,
    _preview_author,
)
from hse_doc_studio.use_cases.pack_studio.places import PackPlacesService
from hse_doc_studio.use_cases.pack_studio.preview import PackPreviewService, PreviewOptions, StartPreviewInput

from tests.unit.use_cases.pack_studio.outcome.synthetic import load_synthetic
from tests.unit.use_cases.pack_studio.test_places_service import PATH, TEAM, TEAM_ANCHORS, FakeFiles

ACTOR = Actor.user("u1", source=ActorSource.pat, scopes=frozenset({"mcp", "packs"}))
WS = uuid4()


@pytest.fixture(autouse=True)
def _russian() -> None:
    set_interface_language("ru")


class _Deps:
    def __init__(self, by_type: dict[type, object]) -> None:
        self.by_type = by_type

    async def get(self, dependency_type: type[Any], component: str | None = None) -> Any:
        return self.by_type[dependency_type]


def _build(**fields: Any) -> PreviewBuild:
    base = PreviewBuild(
        id=uuid4(),
        owner_id="u1",
        workspace_id=WS,
        pack="p",
        template="t",
        version="1.0.1",
        document="report",
        example="auto:normal",
        combination={"staffing": "team2"},
        key="k",
        status=PreviewStatus.succeeded,
        cached=True,
        created_at=datetime.now(UTC),
        has_anchors=True,
    )
    return replace(base, **fields)


class _Previews:
    def __init__(self, build: PreviewBuild) -> None:
        self.build = build
        self.started: list[StartPreviewInput] = []

    async def get(self, _actor: Actor, _ws: UUID, _build_id: UUID) -> PreviewBuild:
        return self.build

    async def places_source(
        self, _actor: Actor, _ws: UUID, _build_id: UUID, _ref: VersionRef
    ) -> tuple[PreviewBuild, BuildAnchors | None]:
        return self.build, TEAM_ANCHORS


class _Starting(_Previews):
    async def start(
        self, _actor: Actor, _ws: UUID, _pack: str, _template: str, _version: str, inp: StartPreviewInput
    ) -> list[PreviewBuild]:
        self.started.append(inp)
        return [self.build]


@pytest.mark.parametrize(
    ("raw", "expected"), [("petrova", "petrova"), (2, "2"), (" 2 ", "2"), ("", None), (None, None)]
)
def test__author_arg__number_or_slug_becomes_a_string(raw: object, expected: str | None) -> None:
    assert _author_arg({} if raw is None else {"author": raw}) == expected


async def test__preview_build__passes_the_author_and_shows_whose_document_was_built() -> None:
    previews = _Starting(_build(author="petrova", authors=TEAM, file_name="Отчёт — Петрова.pdf"))
    tool = PackPreviewBuildTool(_Deps({PackPreviewService: previews}))  # type: ignore[arg-type]

    result = await tool.run(
        ACTOR,
        {
            "workspace_id": str(WS),
            "version": "p/t/1.0.1",
            "documents": ["report"],
            "combination": {"staffing": "team2"},
            "author": 2,
            "wait_s": 0,
        },
    )

    assert result.is_error is False
    assert [inp.author for inp in previews.started] == ["2"]
    [build] = json.loads(result.text)["builds"]
    assert build["author"] == "petrova"
    assert build["file_name"] == "Отчёт — Петрова.pdf"
    assert build["authors"] == [
        {"number": 1, "slug": "ivanov", "name": "Иванов Иван Иванович"},
        {"number": 2, "slug": "petrova", "name": "Петрова Мария Сергеевна"},
    ]


async def test__preview_build__without_author__the_default_is_kept() -> None:
    previews = _Starting(_build(author="ivanov", authors=TEAM))
    tool = PackPreviewBuildTool(_Deps({PackPreviewService: previews}))  # type: ignore[arg-type]

    result = await tool.run(ACTOR, {"workspace_id": str(WS), "version": "p/t/1.0.1", "documents": ["report"]})

    assert [inp.author for inp in previews.started] == [None]
    assert json.loads(result.text)["builds"][0]["author"] == "ivanov"


def test__preview_build_spec__describes_the_author_parameter() -> None:
    spec = PackPreviewBuildTool.spec

    assert spec.parameters["properties"]["author"]["type"] == "string"
    assert "author" not in spec.parameters.get("required", ())
    assert "author:" in spec.description
    assert "по умолчанию первый автор" in spec.description


def test__read_preview_block__says_how_to_pick_an_author(tmp_path_factory: pytest.TempPathFactory) -> None:
    version = load_synthetic(tmp_path_factory.mktemp("packs"))
    options = PreviewOptions(
        pack_id="p",
        template_id="t",
        version_id="1.0.0",
        documents=version.documents,
        switches=(PreviewSwitch("staffing", ("solo", "team2", "team3"), "solo"),),
        examples=(),
        default_example="auto:normal",
        combination={"staffing": "solo"},
    )

    block = _preview_author(options)

    assert block["default"] == 1
    assert block["count_by_staffing"] == {"solo": 1, "team2": 2, "team3": 3}
    assert "report" in block["personal_documents"]
    assert "shared_spec" not in block["personal_documents"]
    assert "pack_preview_build" in block["hint"]


async def test__set_placement__read__author_anchors_come_with_the_slot_and_the_author_name() -> None:
    previews = _Previews(_build(document="report", authors=TEAM))
    places = PackPlacesService(FakeFiles(), previews, PackPlacesEditor())  # type: ignore[arg-type]
    tool = PackSetPlacementTool(_Deps({PackPlacesService: places}))  # type: ignore[arg-type]

    result = await tool.run(
        ACTOR, {"workspace_id": str(WS), "version": "p/t/1.0.1", "build_id": str(previews.build.id)}
    )

    body = json.loads(result.text)
    assert body["path"] == PATH
    found = body["places"]
    assert found["sign_anchors"] == ["author__ivanov", "author__petrova", "supervisor"]
    assert found["anchor_views"][:2] == [
        {
            "id": "author__ivanov",
            "kind": "sign",
            "slot": "author",
            "part": None,
            "author": "ivanov",
            "author_name": "Иванов Иван Иванович",
        },
        {
            "id": "author__petrova",
            "kind": "sign",
            "slot": "author",
            "part": None,
            "author": "petrova",
            "author_name": "Петрова Мария Сергеевна",
        },
    ]
    assert found["anchor_views"][3] == {
        "id": "author__ivanov.day",
        "kind": "date",
        "slot": "author",
        "part": "day",
        "author": "ivanov",
        "author_name": "Иванов Иван Иванович",
    }
