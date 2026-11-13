"""Места подписей из шаблона при обновлении проекта (docs/design/signing-route.md, 15.9 и 15.10)."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

from hse_doc_studio.core.catalog import (
    SignatureDefaultDate,
    SignatureDefaultPlacement,
    SignaturesConfig,
    SignatureSlotDef,
    TemplateVersion,
)
from hse_doc_studio.core.enums import DateMarkFormat, DetachedFormat, DetachedOrigin, DetachedVerdict, SignMode
from hse_doc_studio.core.signatures.pack_places import is_from_pack, stamp_from_pack
from hse_doc_studio.core.signatures.stamps import PLATE_MIN_WIDTH_MM
from hse_doc_studio.core.template_update.signature_presets import (
    PresetKept,
    PresetKeptReason,
    PresetPlace,
    SignaturePresetsPlan,
    revert_places,
)
from hse_doc_studio.core.value_objects import (
    DetachedSignature,
    FrozenPdf,
    SignaturePlacement,
    SignatureSlot,
    SignaturesState,
)
from hse_doc_studio.use_cases.template_update.signature_presets import plan_signature_presets
from tests.factories import make_document, make_project, make_template_version

V0, V1, V2 = "2026.1.0", "2026.1.1", "2026.1.2"
OLDEST = SignatureDefaultPlacement(page=1, x_mm=100, y_mm=100, width_mm=40)
GENERAL = SignatureDefaultPlacement(page=1, x_mm=110, y_mm=130, width_mm=40)
REPORT = SignatureDefaultPlacement(page=1, x_mm=80, y_mm=139, width_mm=40)
DAY = SignatureDefaultDate(page=1, x_mm=81, y_mm=156, width_mm=7, height_mm=5, format=DateMarkFormat.day)


def _slot(slot_id: str = "supervisor", default: SignatureDefaultPlacement = GENERAL, **kwargs: Any) -> SignatureSlotDef:
    return SignatureSlotDef(
        id=slot_id, label={"ru": slot_id}, applies_to=("report", "proposal"), default_placement=default, **kwargs
    )


def _version(version: str, *slots: SignatureSlotDef) -> TemplateVersion:
    return replace(make_template_version(version=version), signatures_config=SignaturesConfig(slots=slots))


PRESET = _slot(placements=(("report", REPORT),), default_dates=(("report", (DAY,)),))
VERSIONS = {
    V0: _version(V0, _slot(default=OLDEST), _slot("author")),
    V1: _version(V1, _slot(), _slot("author")),
    V2: _version(V2, PRESET, _slot("author")),
}


class _Templates:
    def list_versions(self, pack_id: str, template_id: str) -> list[str]:
        return list(VERSIONS)

    def get_version(self, pack_id: str, template_id: str, version: str) -> TemplateVersion | None:
        return VERSIONS.get(version)


def _place(place: SignatureDefaultPlacement, **kwargs: Any) -> SignaturePlacement:
    fields: dict[str, Any] = {"enabled": False, **place.__dict__}
    fields.update(kwargs)
    return SignaturePlacement(**fields)


def _state(placements: dict[str, dict[str, SignaturePlacement]], **kwargs: Any) -> SignaturesState:
    return SignaturesState(slots=kwargs.pop("slots", {}), placements=placements, **kwargs)


def _plan(state: SignaturesState, held: tuple[str, ...] = ()) -> SignaturePresetsPlan:
    project = make_project(documents=[make_document("report"), make_document("proposal")])
    return plan_signature_presets(_Templates(), project, VERSIONS[V1], VERSIONS[V2], state, held)  # type: ignore[arg-type]


def test__seed__moves_to_the_document_place_with_marks_and_from_pack() -> None:
    plan = _plan(_state({"report": {"supervisor": _place(GENERAL)}}))

    assert plan.updated == (PresetPlace("report", "supervisor"),)
    assert plan.kept == ()
    new = plan.placements[0]
    assert (new.page, new.x_mm, new.y_mm, new.width_mm) == (1, 80, 139, 40)
    assert [(m.id, m.format, m.x_mm) for m in new.dates] == [("d1", DateMarkFormat.day, 81)]
    assert new.enabled is False
    assert new.from_pack is not None
    assert new.from_pack.version == V2
    assert is_from_pack(new)


def test__seed_of_an_earlier_version__is_still_a_seed() -> None:
    plan = _plan(_state({"report": {"supervisor": _place(OLDEST)}}))

    assert plan.updated == (PresetPlace("report", "supervisor"),)


def test__place_from_the_pack__keeps_enabled_and_sign_date() -> None:
    from_pack = stamp_from_pack(_place(GENERAL, enabled=True, sign_date="2026-11-13"), V1)

    plan = _plan(_state({"report": {"supervisor": from_pack}}))

    new = plan.placements[0]
    assert new.enabled is True
    assert new.sign_date == "2026-11-13"
    assert new.x_mm == 80


def test__manual_place__kept_only_where_the_pack_moved_it() -> None:
    manual = _place(GENERAL, enabled=True, x_mm=95)
    plan = _plan(_state({"report": {"supervisor": manual}, "proposal": {"supervisor": manual}}))

    # На «proposal» пак место научрука не менял (общее место то же): ручное место там не новость.
    assert plan.updated == ()
    assert plan.kept == (PresetKept("report", "supervisor", PresetKeptReason.manual),)


def test__place_already_as_in_the_new_version__not_in_the_plan() -> None:
    plan = _plan(_state({"proposal": {"supervisor": _place(GENERAL)}, "report": {"author": _place(GENERAL)}}))

    assert plan.is_empty


def test__document_held_by_a_route__kept_route_even_if_manual() -> None:
    state = _state({"report": {"supervisor": _place(GENERAL)}, "proposal": {"supervisor": _place(OLDEST)}})

    plan = _plan(state, held=("report", "proposal"))

    assert plan.updated == ()
    assert set(plan.kept) == {
        PresetKept("report", "supervisor", PresetKeptReason.route),
        PresetKept("proposal", "supervisor", PresetKeptReason.route),
    }


def _signed(state: SignaturesState, doc_id: str) -> SignaturesState:
    frozen = FrozenPdf(path="x.pdf", sha256="a", source_sha256="b", size=1, frozen_at="2026-11-13T00:00:00Z")
    detached = DetachedSignature(
        file="x.sig",
        format=DetachedFormat.cms,
        origin=DetachedOrigin.uploaded,
        pdf_sha256="a",
        verdict=DetachedVerdict.valid,
        signer="Иванов",
        signer_id="id",
        added_at="2026-11-13T00:00:00Z",
    )
    return replace(state, frozen={doc_id: frozen}, detached={doc_id: {"supervisor": detached}})


def test__document_signed_over_the_frozen_pdf__kept_signed() -> None:
    plan = _plan(_signed(_state({"report": {"supervisor": _place(GENERAL)}}), "report"))

    assert plan.kept == (PresetKept("report", "supervisor", PresetKeptReason.signed),)


def test__frozen_without_signatures__updates() -> None:
    state = _signed(_state({"report": {"supervisor": _place(GENERAL)}}), "report")

    plan = _plan(replace(state, detached={}))

    assert plan.updated == (PresetPlace("report", "supervisor"),)


def test__plate_slot__new_place_is_widened_and_stays_from_the_pack() -> None:
    slots = {"supervisor": SignatureSlot(None, None, None, sign_mode=SignMode.detached_text)}
    # Место из шаблона 2026.1.1, расширенное под плашку: пометка переписана под широкую рамку (`keep_from_pack`).
    placed = stamp_from_pack(_place(GENERAL, enabled=True, x_mm=80.0, width_mm=PLATE_MIN_WIDTH_MM), V1)

    plan = _plan(_state({"report": {"supervisor": placed}}, slots=slots))

    new = plan.placements[0]
    assert new.width_mm == PLATE_MIN_WIDTH_MM
    assert new.x_mm == 80 + 40 - PLATE_MIN_WIDTH_MM
    assert is_from_pack(new)


def test__per_author_slot_on_a_shared_document__skipped() -> None:
    plan = _plan(_state({"report": {"supervisor--ivan": _place(GENERAL)}}))

    assert plan.is_empty


def test__unknown_document_or_slot__skipped() -> None:
    plan = _plan(_state({"ghost": {"supervisor": _place(GENERAL)}, "report": {"nobody": _place(GENERAL)}}))

    assert plan.is_empty


def test__apply_and_fingerprint_lines() -> None:
    state = _state({"report": {"supervisor": _place(GENERAL), "author": _place(GENERAL, enabled=True, x_mm=1)}})
    plan = _plan(state)

    applied = plan.apply(state)

    assert applied.placements["report"]["supervisor"] == plan.placements[0]
    assert applied.placements["report"]["author"] == state.placements["report"]["author"]
    assert plan.fingerprint_lines() == ("signature_presets:updated:report:supervisor",)
    assert SignaturePresetsPlan().apply(state) is state


def _json(placement: SignaturePlacement) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(
        json.dumps(
            {
                "enabled": placement.enabled,
                "page": placement.page,
                "x_mm": placement.x_mm,
                "y_mm": placement.y_mm,
                "width_mm": placement.width_mm,
                "sign_date": placement.sign_date,
                "dates": [m.__dict__ | {"format": m.format.value, "align": m.align.value} for m in placement.dates],
                "signed_at": None,
                "from_pack": placement.from_pack.__dict__ if placement.from_pack else None,
            }
        )
    )
    return data


def _file(placement: SignaturePlacement, **extra: Any) -> dict[str, Any]:
    return {"slots": {}, "placements": {"report": {"supervisor": _json(placement)}}, "unknown": 1, **extra}


def test__revert_places__returns_the_untouched_place_and_keeps_enabled() -> None:
    before = _place(GENERAL)
    after = _plan(_state({"report": {"supervisor": before}})).placements[0]
    current = _file(replace(after, enabled=True))

    result, restored = revert_places(_file(before), _file(after), current)

    assert restored == (PresetPlace("report", "supervisor"),)
    assert result is not None
    place = result["placements"]["report"]["supervisor"]
    assert (place["x_mm"], place["dates"], place["from_pack"], place["enabled"]) == (110, [], None, True)
    assert result["unknown"] == 1


def test__revert_places__leaves_a_place_moved_after_the_update() -> None:
    before = _place(GENERAL)
    after = _plan(_state({"report": {"supervisor": before}})).placements[0]

    result, restored = revert_places(_file(before), _file(after), _file(replace(after, x_mm=50, from_pack=None)))

    assert (result, restored) == (None, ())


def test__revert_places__skips_held_and_signed_documents() -> None:
    before = _place(GENERAL)
    after = _plan(_state({"report": {"supervisor": before}})).placements[0]
    signed = _file(after, frozen={"report": {}}, detached={"report": {"supervisor": {}}})
    signed["detached"]["report"]["supervisor"] = {"file": "x.sig"}

    assert revert_places(_file(before), _file(after), _file(after), held_docs={"report"}) == (None, ())
    assert revert_places(_file(before), _file(after), signed) == (None, ())
