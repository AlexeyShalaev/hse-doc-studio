"""Места на якорях при обновлении шаблона проекта (docs/design/signing-route.md, 15.17.10)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from hse_doc_studio.core.catalog import (
    AnchorPlace,
    SignatureDefaultPlacement,
    SignaturesConfig,
    SignatureSlotDef,
    TemplateVersion,
)
from hse_doc_studio.core.enums import DateMarkAlign
from hse_doc_studio.core.signatures.anchors import AnchorKind, BuildAnchor, BuildAnchors
from hse_doc_studio.core.signatures.pack_places import SourceAnchors, is_from_pack, stamp_from_pack
from hse_doc_studio.core.template_update.signature_presets import PresetPlace, SignaturePresetsPlan
from hse_doc_studio.core.value_objects import CustomFileOverride, SignaturePlacement, SignaturesState
from hse_doc_studio.use_cases.template_update.signature_presets import plan_signature_presets
from tests.factories import make_document, make_project, make_template_version

V1, V2 = "2026.1.4", "2026.1.5"
REPORT = SignatureDefaultPlacement(page=1, x_mm=80, y_mm=139, width_mm=40)
GENERAL = SignatureDefaultPlacement(page=1, x_mm=110, y_mm=130, width_mm=40)
ANCHORED = AnchorPlace("supervisor", align=DateMarkAlign.right, width_mm=28)
LINE = BuildAnchor("supervisor", AnchorKind.sign, 1, 169.5, 186.8, 25.5)


def _slot(**kwargs: Any) -> SignatureSlotDef:
    return SignatureSlotDef(
        id="supervisor", label={"ru": "supervisor"}, applies_to=("report",), default_placement=GENERAL, **kwargs
    )


def _version(version: str, slot: SignatureSlotDef) -> TemplateVersion:
    return replace(make_template_version(version=version), signatures_config=SignaturesConfig(slots=(slot,)))


VERSIONS = {
    V1: _version(V1, _slot(placements=(("report", REPORT),))),
    V2: _version(V2, _slot(placements=(("report", ANCHORED),))),
}


class _Templates:
    def list_versions(self, pack_id: str, template_id: str) -> list[str]:
        return list(VERSIONS)

    def get_version(self, pack_id: str, template_id: str, version: str) -> TemplateVersion | None:
        return VERSIONS.get(version)


def _state(placement: SignaturePlacement) -> SignaturesState:
    return SignaturesState(slots={}, placements={"report": {"supervisor": placement}})


def _from_pack() -> SignaturePlacement:
    return stamp_from_pack(SignaturePlacement(enabled=True, page=1, x_mm=80, y_mm=139, width_mm=40), V1)


def _plan(state: SignaturesState, src: SourceAnchors, **doc: Any) -> SignaturePresetsPlan:
    project = make_project(documents=[make_document("report", **doc)])
    anchors = {"report": src}
    return plan_signature_presets(_Templates(), project, VERSIONS[V1], VERSIONS[V2], state, (), anchors)  # type: ignore[arg-type]


def test__mm_to_anchor__known_anchors__place_on_the_line() -> None:
    plan = _plan(_state(_from_pack()), SourceAnchors(BuildAnchors("a" * 64, (LINE,))))

    assert plan.updated == (PresetPlace("report", "supervisor"),)
    new = plan.placements[0]
    assert (new.x_mm, new.y_mm, new.width_mm, new.enabled) == (167.0, 176.8, 28.0, True)
    assert new.from_pack is not None
    assert (new.from_pack.version, new.from_pack.anchor, new.from_pack.build) == (V2, "supervisor", "a" * 16)


def test__mm_to_anchor__unknown_anchors__place_stays_with_the_new_mark_after_build() -> None:
    plan = _plan(_state(_from_pack()), SourceAnchors())

    assert plan.updated == (PresetPlace("report", "supervisor", after_build=True),)
    assert "signature_presets:updated:report:supervisor:after_build" in plan.fingerprint_lines()
    new = plan.placements[0]
    assert (new.x_mm, new.y_mm, new.width_mm) == (80, 139, 40)
    assert new.from_pack is not None
    assert (new.from_pack.version, new.from_pack.anchor, new.from_pack.build) == (V2, "supervisor", None)
    assert is_from_pack(new)


def test__mm_to_anchor__known_anchors_without_the_line__switched_off() -> None:
    plan = _plan(_state(_from_pack()), SourceAnchors(BuildAnchors("a" * 64, ())))

    new = plan.placements[0]
    assert (new.x_mm, new.y_mm, new.enabled) == (80, 139, False)
    assert new.from_pack is not None
    assert new.from_pack.version == V2


def test__mm_to_anchor__own_uploaded_pdf__not_in_the_plan() -> None:
    custom = CustomFileOverride(
        original_filename="r.pdf", stored_path="report/_custom/r.pdf", ext=".pdf", uploaded_at=""
    )

    plan = _plan(_state(_from_pack()), SourceAnchors(own_pdf=True), custom_file=custom)

    assert plan.is_empty


def test__manual_place__kept_manual_when_the_record_changed() -> None:
    manual = SignaturePlacement(enabled=True, page=1, x_mm=95, y_mm=139, width_mm=40)

    plan = _plan(_state(manual), SourceAnchors())

    assert [(k.doc_id, k.reason.value) for k in plan.kept] == [("report", "manual")]
    assert plan.updated == ()
