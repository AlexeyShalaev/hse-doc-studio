"""Пересчёт мест подписей на якорях после сборки (docs/design/signing-route.md, 15.17.9).

Сборку заменяют PDF рядом с исходником и `anchors.json` в `.build`, как их оставляет публикация сборки.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from hse_doc_studio.core.catalog import (
    AnchorPlace,
    SignatureDefaultPlacement,
    SignaturesConfig,
    SignatureSlotDef,
    TemplateVersion,
)
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import DateMarkAlign, DetachedFormat, DetachedOrigin, DetachedVerdict, SignMode
from hse_doc_studio.core.signatures.anchors import AnchorKind, BuildAnchor, BuildAnchors, encode_anchors
from hse_doc_studio.core.signatures.pack_places import SourceAnchors, is_from_pack, pack_placement
from hse_doc_studio.core.value_objects import (
    CustomFileOverride,
    DetachedSignature,
    FrozenPdf,
    PinnedPdf,
    SignaturePlacement,
    SignatureSlot,
    SignaturesState,
)
from hse_doc_studio.infra.persistence.signature import JsonSignatureRepository
from hse_doc_studio.use_cases.signatures.anchor_places import BuildPlaces, rebuild_places

from tests.factories import make_document, make_project, make_template_version

V = "2026.1.5"
GENERAL = SignatureDefaultPlacement(page=1, x_mm=110, y_mm=130, width_mm=40)
ENTRY = AnchorPlace("supervisor", align=DateMarkAlign.right, width_mm=28)
SLOT = SignatureSlotDef(
    id="supervisor",
    label={"ru": "Научный руководитель"},
    applies_to=("topic_application", "report"),
    default_placement=GENERAL,
    placements=(("topic_application", ENTRY),),
)
VERSION = replace(make_template_version(version=V), signatures_config=SignaturesConfig(slots=(SLOT,)))
RU = BuildAnchor("supervisor", AnchorKind.sign, 1, 169.5, 186.8, 25.5)
EN = BuildAnchor("supervisor", AnchorKind.sign, 1, 169.5, 158.0, 25.5)


def _src(*lines: BuildAnchor) -> SourceAnchors:
    return SourceAnchors(BuildAnchors("b" * 64, lines))


def _placed(line: BuildAnchor, **kwargs: Any) -> SignaturePlacement:
    placement = pack_placement(SLOT, "topic_application", None, V, _src(line))
    assert placement is not None
    return replace(placement, **kwargs)


def _state(placement: SignaturePlacement, **kwargs: Any) -> SignaturesState:
    return SignaturesState(
        slots=kwargs.pop("slots", {}), placements={"topic_application": {"supervisor": placement}}, **kwargs
    )


def _project(folder: Path = Path("/tmp/p"), **doc: Any) -> Project:
    return make_project(folder=folder, documents=[make_document("topic_application", **doc)])


# --- чистый пересчёт ---


def test__rebuild__place_from_the_template_follows_the_line() -> None:
    state = _state(_placed(RU, enabled=True))

    rebuilt = rebuild_places(state, _project(), VERSION, _project().documents[0], _src(EN))

    moved = rebuilt.placements["topic_application"]["supervisor"]
    assert (moved.x_mm, moved.y_mm, moved.enabled) == (167.0, 148.0, True)
    assert is_from_pack(moved)


def test__rebuild__manual_place_stays() -> None:
    manual = replace(_placed(RU, enabled=True), x_mm=150.0)  # человек сдвинул: отпечаток разошёлся
    state = _state(manual)

    assert rebuild_places(state, _project(), VERSION, _project().documents[0], _src(EN)) == state


def test__rebuild__line_gone__place_switched_off_where_it_was() -> None:
    state = _state(_placed(RU, enabled=True))

    rebuilt = rebuild_places(state, _project(), VERSION, _project().documents[0], _src())

    off = rebuilt.placements["topic_application"]["supervisor"]
    assert (off.x_mm, off.y_mm, off.enabled) == (167.0, 176.8, False)
    assert is_from_pack(off)


def test__rebuild__unknown_anchors__nothing_moves() -> None:
    state = _state(_placed(RU, enabled=True))

    assert rebuild_places(state, _project(), VERSION, _project().documents[0], SourceAnchors()) == state


def test__rebuild__same_build__no_change() -> None:
    state = _state(_placed(RU, enabled=True))

    assert rebuild_places(state, _project(), VERSION, _project().documents[0], _src(RU)).placements == state.placements


def test__rebuild__plate_widens_the_moved_place() -> None:
    state = _state(
        _placed(RU, enabled=True),
        slots={"supervisor": SignatureSlot(None, None, None, sign_mode=SignMode.detached_text)},
    )

    moved = rebuild_places(state, _project(), VERSION, _project().documents[0], _src(EN)).placements
    place = moved["topic_application"]["supervisor"]

    assert (place.width_mm, place.x_mm + place.width_mm) == (70.0, 195.0)
    assert is_from_pack(place)


# --- после публикации сборки ---


class _Templates:
    def get_version(self, pack_id: str, template_id: str, version: str) -> TemplateVersion | None:
        return VERSION


class _Projects:
    def __init__(self, project: Project) -> None:
        self.project = project

    def get(self, folder: Path) -> Project | None:
        return self.project


class _Sources:
    """Исходник `topic_application/main.tex`, сборка `topic_application/main.pdf`."""

    def resolve_instance_source(self, project: Project, doc: Any, version: Any) -> tuple[str, str]:
        return "topic_application/main.tex", "topic_application/main.pdf"

    def resolve_signing_output(self, project: Project, doc: Any, version: Any) -> str:
        return "topic_application/main.pdf"


class _Routes:
    def __init__(self, held: bool = False) -> None:
        self.held = held

    async def apply(self, project_id: UUID, doc_id: str, state: SignaturesState, src: SourceAnchors) -> Any:
        return None if self.held else state


def _build(folder: Path, line: BuildAnchor, text: str = "build") -> str:
    pdf = folder / "topic_application" / "main.pdf"
    pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf.write_bytes(f"%PDF-1.7 {text}".encode())
    sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
    anchors = folder / "topic_application" / ".build" / "topic_application" / "main.anchors.json"
    anchors.parent.mkdir(parents=True, exist_ok=True)
    anchors.write_bytes(encode_anchors(BuildAnchors(sha, (line,))))
    return sha


def _places(project: Project, routes: _Routes | None = None) -> BuildPlaces:
    return BuildPlaces(
        _Projects(project),  # type: ignore[arg-type]
        _Templates(),  # type: ignore[arg-type]
        JsonSignatureRepository(),
        _Sources(),  # type: ignore[arg-type]
        routes or _Routes(),
    )


async def _after(tmp_path: Path, state: SignaturesState, routes: _Routes | None = None, **doc: Any) -> tuple[int, Any]:
    project = _project(tmp_path, **doc)
    repo = JsonSignatureRepository()
    repo.save_state(tmp_path, state)
    moved = await _places(project, routes).after_build(project.id, tmp_path, "topic_application")
    return moved, repo.get_state(tmp_path).placements["topic_application"]["supervisor"]


async def test__after_build__moves_and_counts(tmp_path: Path) -> None:
    _build(tmp_path, EN)

    moved, place = await _after(tmp_path, _state(_placed(RU, enabled=True)))

    assert moved == 1
    assert (place.y_mm, place.from_pack.build) == (
        148.0,
        hashlib.sha256((tmp_path / "topic_application" / "main.pdf").read_bytes()).hexdigest()[:16],
    )


async def test__after_build__anchors_of_another_pdf__nothing(tmp_path: Path) -> None:
    # Сборка раннером прежней версии: в `.build` якоря прошлой сборки, PDF новый.
    _build(tmp_path, EN)
    (tmp_path / "topic_application" / "main.pdf").write_bytes(b"%PDF-1.7 another")

    moved, place = await _after(tmp_path, _state(_placed(RU, enabled=True)))

    assert (moved, place.y_mm) == (0, 176.8)


async def test__after_build__held_by_a_route__nothing(tmp_path: Path) -> None:
    _build(tmp_path, EN)

    moved, place = await _after(tmp_path, _state(_placed(RU, enabled=True)), _Routes(held=True))

    assert (moved, place.y_mm) == (0, 176.8)


async def test__after_build__signing_version__nothing(tmp_path: Path) -> None:
    _build(tmp_path, EN)
    pinned = PinnedPdf(path=".hse-studio/frozen/topic_application.source.pdf", sha256="c" * 64, size=1, pinned_at="")

    moved, place = await _after(tmp_path, _state(_placed(RU, enabled=True), pinned={"topic_application": pinned}))

    assert (moved, place.y_mm) == (0, 176.8)


async def test__after_build__e_signature_over_b__nothing(tmp_path: Path) -> None:
    _build(tmp_path, EN)
    frozen = FrozenPdf(path="f.pdf", sha256="d" * 64, size=1, frozen_at="", source_sha256="e" * 64)
    signature = DetachedSignature(
        file="x.sig",
        format=DetachedFormat.cms,
        origin=DetachedOrigin.uploaded,
        verdict=DetachedVerdict.valid,
        signer="",
        signer_id="",
        added_at="",
        pdf_sha256="d" * 64,
    )
    state = _state(
        _placed(RU, enabled=True),
        frozen={"topic_application": frozen},
        detached={"topic_application": {"supervisor": signature}},
    )

    moved, place = await _after(tmp_path, state)

    assert (moved, place.y_mm) == (0, 176.8)


async def test__after_build__own_uploaded_pdf__nothing(tmp_path: Path) -> None:
    _build(tmp_path, EN)
    custom = CustomFileOverride(
        original_filename="main.pdf", stored_path="topic_application/main.pdf", ext=".pdf", uploaded_at=""
    )

    moved, place = await _after(tmp_path, _state(_placed(RU, enabled=True)), custom_file=custom)

    assert (moved, place.y_mm) == (0, 176.8)


async def test__after_build__no_change__file_not_written(tmp_path: Path) -> None:
    _build(tmp_path, RU)
    state = _state(_placed(RU, enabled=True))
    project = _project(tmp_path)
    JsonSignatureRepository().save_state(tmp_path, state)
    path = tmp_path / ".hse-studio" / "signatures.json"
    before = path.stat().st_mtime_ns

    moved = await _places(project).after_build(project.id, tmp_path, "topic_application")

    assert moved == 0
    assert path.stat().st_mtime_ns == before


@pytest.mark.parametrize("raw", [b"", b"{broken"])
async def test__after_build__broken_anchors__nothing(tmp_path: Path, raw: bytes) -> None:
    _build(tmp_path, EN)
    (tmp_path / "topic_application" / ".build" / "topic_application" / "main.anchors.json").write_bytes(raw)

    moved, _ = await _after(tmp_path, _state(_placed(RU, enabled=True)))

    assert moved == 0
