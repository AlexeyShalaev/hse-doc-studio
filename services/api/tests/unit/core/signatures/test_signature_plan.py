from __future__ import annotations

from dataclasses import replace

import pytest
from hse_doc_studio.core.access.entities import Grant, Role
from hse_doc_studio.core.enums import (
    DetachedFormat,
    DetachedOrigin,
    DetachedVerdict,
    ProjectStaffing,
    SignMode,
)
from hse_doc_studio.core.signatures.plan import (
    AUTHOR_PERSONA,
    DocFacts,
    DocPlan,
    PlanReason,
    PlanSlot,
    SignaturePlan,
    SignerRef,
    SignMethod,
    SlotState,
    SlotStatus,
    VisibleMark,
    author_personas,
    grant_personas,
    method_of,
    reason_hint,
    slot_mode_conflict,
    slot_persona,
    slot_state,
)
from hse_doc_studio.core.value_objects import (
    Author,
    DetachedSignature,
    EmbeddedSignature,
    FrozenPdf,
    SignaturePlacement,
    SignatureSlot,
    SignaturesState,
    SkippedSlot,
)

from tests.factories import make_project

_DOC = "annotation"
_SRC = "s" * 64
_FROZEN = "f" * 64
_MARKS = "m" * 64


def _slot(mode: SignMode, png: str | None = "sig.png") -> SignatureSlot:
    return SignatureSlot(png_path=png, natural_width_px=10, natural_height_px=4, sign_mode=mode)


def _placement(enabled: bool = True) -> SignaturePlacement:
    return SignaturePlacement(enabled=enabled, page=1, x_mm=10, y_mm=10, width_mm=30)


def _frozen() -> FrozenPdf:
    return FrozenPdf(
        path=".hse-studio/frozen/annotation.pdf",
        sha256=_FROZEN,
        source_sha256=_SRC,
        size=10,
        frozen_at="2026-11-09T10:00:00+00:00",
        stamps_digest=_MARKS,
    )


def _detached(verdict: DetachedVerdict = DetachedVerdict.valid, pdf_sha: str = _FROZEN) -> DetachedSignature:
    return DetachedSignature(
        file=".hse-studio/detached/annotation/supervisor.asc",
        format=DetachedFormat.openpgp,
        origin=DetachedOrigin.uploaded,
        pdf_sha256=pdf_sha,
        verdict=verdict,
        signer="Петров П.",
        signer_id="ABCD",
        added_at="2026-11-09T10:00:00+00:00",
    )


def _embedded(base: str = _FROZEN, verdict: DetachedVerdict = DetachedVerdict.valid) -> EmbeddedSignature:
    return EmbeddedSignature(
        field_name="Sig_supervisor",
        base_sha256=base,
        revision_size=20,
        revision_sha256="r" * 64,
        verdict=verdict,
        signer="Петров П.",
        signer_id="CERT",
        added_at="2026-11-09T10:00:00+00:00",
    )


def _state(mode: SignMode, **kw: object) -> SignaturesState:
    base = SignaturesState(
        slots={"supervisor": _slot(mode)},
        placements={_DOC: {"supervisor": _placement()}},
    )
    return replace(base, **kw)  # type: ignore[arg-type]


_FACTS = DocFacts(compiled_sha256=_SRC, marks_digest=_MARKS)


@pytest.mark.parametrize(
    ("mode", "method", "mark"),
    [
        (SignMode.image, SignMethod.image, VisibleMark.png),
        (SignMode.image_crypto, SignMethod.pades, VisibleMark.png),
        (SignMode.crypto_invisible, SignMethod.pades, VisibleMark.none),
        (SignMode.detached, SignMethod.detached, VisibleMark.png),
        (SignMode.detached_text, SignMethod.detached, VisibleMark.plate),
    ],
)
def test__slot_state__every_mode__maps_to_method_and_mark(
    mode: SignMode, method: SignMethod, mark: VisibleMark
) -> None:
    result = slot_state(_state(mode), _DOC, "supervisor", _FACTS)

    assert (result.method, result.mark) == (method, mark)
    assert method_of(mode) is method


def test__slot_state__image_with_png__signed_and_not_crypto() -> None:
    result = slot_state(_state(SignMode.image), _DOC, "supervisor", _FACTS)

    assert result.status is SlotStatus.signed
    assert result.crypto is False


def test__slot_state__image_without_png__pending_no_image() -> None:
    state = SignaturesState(
        slots={"supervisor": _slot(SignMode.image, png=None)}, placements={_DOC: {"supervisor": _placement()}}
    )

    result = slot_state(state, _DOC, "supervisor", _FACTS)

    assert (result.status, result.reason) == (SlotStatus.pending, PlanReason.no_image)


def test__slot_state__placement_off__pending() -> None:
    state = SignaturesState(
        slots={"supervisor": _slot(SignMode.detached_text)}, placements={_DOC: {"supervisor": _placement(False)}}
    )

    result = slot_state(state, _DOC, "supervisor", _FACTS)

    assert result.reason is PlanReason.placement_off


def test__slot_state__invisible_pades_without_placement__does_not_need_one() -> None:
    state = SignaturesState(slots={"supervisor": _slot(SignMode.crypto_invisible, png=None)}, placements={})

    result = slot_state(state, _DOC, "supervisor", _FACTS)

    assert result.reason is PlanReason.not_frozen


def test__slot_state__detached_frozen_without_file__explains_what_is_missing() -> None:
    state = _state(SignMode.detached_text, frozen={_DOC: _frozen()})

    result = slot_state(state, _DOC, "supervisor", _FACTS)

    assert (result.status, result.reason) == (SlotStatus.pending, PlanReason.no_signature_file)
    assert ".asc" in reason_hint(result.reason)


def test__slot_state__detached_not_built__pending_not_built() -> None:
    result = slot_state(
        _state(SignMode.detached_text), _DOC, "supervisor", DocFacts(compiled_sha256=None, marks_digest=_MARKS)
    )

    assert result.reason is PlanReason.not_built


def test__slot_state__detached_valid__signed_with_check() -> None:
    state = _state(SignMode.detached_text, frozen={_DOC: _frozen()}, detached={_DOC: {"supervisor": _detached()}})

    result = slot_state(state, _DOC, "supervisor", _FACTS)

    assert result.status is SlotStatus.signed
    assert result.check is not None
    assert (result.check.format, result.check.signer) == ("openpgp", "Петров П.")


@pytest.mark.parametrize(
    ("verdict", "status", "reason"),
    [
        (DetachedVerdict.invalid, SlotStatus.invalid, PlanReason.invalid_signature),
        (DetachedVerdict.unknown_key, SlotStatus.pending, PlanReason.unknown_key),
        (DetachedVerdict.unverified, SlotStatus.signed, None),
    ],
)
def test__slot_state__detached_verdicts(verdict: DetachedVerdict, status: SlotStatus, reason: PlanReason) -> None:
    state = _state(
        SignMode.detached_text, frozen={_DOC: _frozen()}, detached={_DOC: {"supervisor": _detached(verdict)}}
    )

    result = slot_state(state, _DOC, "supervisor", _FACTS)

    assert (result.status, result.reason) == (status, reason)


def test__slot_state__detached_of_other_freeze__stale() -> None:
    state = _state(
        SignMode.detached_text, frozen={_DOC: _frozen()}, detached={_DOC: {"supervisor": _detached(pdf_sha="0" * 64)}}
    )

    result = slot_state(state, _DOC, "supervisor", _FACTS)

    assert (result.status, result.reason) == (SlotStatus.stale, PlanReason.other_pdf)


def test__slot_state__rebuilt_after_signing__stale() -> None:
    state = _state(SignMode.detached_text, frozen={_DOC: _frozen()}, detached={_DOC: {"supervisor": _detached()}})

    result = slot_state(state, _DOC, "supervisor", DocFacts(compiled_sha256="n" * 64, marks_digest=_MARKS))

    assert (result.status, result.reason) == (SlotStatus.stale, PlanReason.rebuilt)


def test__slot_state__marks_changed_before_signing__pending() -> None:
    state = _state(SignMode.detached_text, frozen={_DOC: _frozen()})

    result = slot_state(state, _DOC, "supervisor", DocFacts(compiled_sha256=_SRC, marks_digest="x" * 64))

    assert (result.status, result.reason) == (SlotStatus.pending, PlanReason.marks_changed)


def test__slot_state__pades_signed_on_current_freeze__signed() -> None:
    state = _state(SignMode.image_crypto, frozen={_DOC: _frozen()}, embedded={_DOC: {"supervisor": _embedded()}})

    result = slot_state(state, _DOC, "supervisor", _FACTS)

    assert result.status is SlotStatus.signed
    assert result.check is not None
    assert result.check.format == "pades"


def test__slot_state__pades_frozen_without_signature__pending_no_embedded() -> None:
    state = _state(SignMode.image_crypto, frozen={_DOC: _frozen()})

    result = slot_state(state, _DOC, "supervisor", _FACTS)

    assert result.reason is PlanReason.no_embedded


def test__slot_state__pades_on_other_freeze__stale() -> None:
    state = _state(
        SignMode.image_crypto, frozen={_DOC: _frozen()}, embedded={_DOC: {"supervisor": _embedded(base="0" * 64)}}
    )

    result = slot_state(state, _DOC, "supervisor", _FACTS)

    assert result.status is SlotStatus.stale


def test__slot_state__method_not_allowed_by_profile__pending() -> None:
    state = _state(SignMode.image_crypto, frozen={_DOC: _frozen()}, embedded={_DOC: {"supervisor": _embedded()}})

    result = slot_state(state, _DOC, "supervisor", _FACTS, allowed=("image", "detached"))

    assert (result.status, result.reason) == (SlotStatus.pending, PlanReason.method_not_allowed)


def test__slot_state__image_on_frozen_doc_after_marks_changed__stale_when_doc_uses_frozen() -> None:
    state = _state(SignMode.image, frozen={_DOC: _frozen()})
    facts = DocFacts(compiled_sha256=_SRC, marks_digest="x" * 64)

    assert slot_state(state, _DOC, "supervisor", facts, uses_frozen=True).status is SlotStatus.stale
    assert slot_state(state, _DOC, "supervisor", facts, uses_frozen=False).status is SlotStatus.signed


_HELD = {_DOC: frozenset({"supervisor"})}


@pytest.mark.parametrize("mode", [SignMode.image, SignMode.image_crypto, SignMode.detached, SignMode.detached_text])
def test__slot_state__withheld_visible_mark__pending_awaiting_approval(mode: SignMode) -> None:
    state = _state(mode, withheld=_HELD)

    result = slot_state(state, _DOC, "supervisor", _FACTS)

    assert (result.status, result.reason) == (SlotStatus.pending, PlanReason.awaiting_approval)
    assert reason_hint(result.reason)


def test__slot_state__withheld__a_signed_detached_slot_still_waits_for_approval() -> None:
    signed = _state(SignMode.detached_text, frozen={_DOC: _frozen()}, detached={_DOC: {"supervisor": _detached()}})

    result = slot_state(replace(signed, withheld=_HELD), _DOC, "supervisor", _FACTS)

    assert (result.status, result.reason) == (SlotStatus.pending, PlanReason.awaiting_approval)


def test__slot_state__withheld__checked_after_placement_off_and_before_no_image() -> None:
    off = SignaturesState(
        slots={"supervisor": _slot(SignMode.image)},
        placements={_DOC: {"supervisor": _placement(False)}},
        withheld=_HELD,
    )
    no_png = SignaturesState(
        slots={"supervisor": _slot(SignMode.image, png=None)},
        placements={_DOC: {"supervisor": _placement()}},
        withheld=_HELD,
    )

    assert slot_state(off, _DOC, "supervisor", _FACTS).reason is PlanReason.placement_off
    assert slot_state(no_png, _DOC, "supervisor", _FACTS).reason is PlanReason.awaiting_approval


def test__slot_state__withheld__invisible_pades_and_other_docs_and_slots_are_not_affected() -> None:
    invisible = SignaturesState(
        slots={"supervisor": _slot(SignMode.crypto_invisible, png=None)}, placements={}, withheld=_HELD
    )
    other_doc = _state(SignMode.image, withheld={"thesis": frozenset({"supervisor"})})
    other_slot = _state(SignMode.image, withheld={_DOC: frozenset({"author"})})

    assert slot_state(invisible, _DOC, "supervisor", _FACTS).reason is PlanReason.not_frozen
    assert slot_state(other_doc, _DOC, "supervisor", _FACTS).status is SlotStatus.signed
    assert slot_state(other_slot, _DOC, "supervisor", _FACTS).status is SlotStatus.signed


@pytest.mark.parametrize(
    ("slot_id", "persona"),
    [
        ("author", AUTHOR_PERSONA),
        ("author--ivanov", "ivanov"),
        ("supervisor", "supervisor"),
        ("co_supervisor", "co_supervisor"),
        ("academic_supervisor", "academic_supervisor"),
    ],
)
def test__slot_persona__maps_slot_to_project_persona(slot_id: str, persona: str) -> None:
    assert slot_persona(slot_id) == persona


def test__grant_personas__owner_of_solo_is_author_and_bound_persona_counts() -> None:
    project = make_project()

    assert grant_personas(project, Grant(role=Role.owner)) == {AUTHOR_PERSONA}
    assert grant_personas(project, Grant(role=Role.reviewer, persona_slug="supervisor")) == {"supervisor"}
    assert grant_personas(project, Grant(role=Role.editor)) == frozenset()
    assert grant_personas(project, None) == frozenset()


def test__author_personas__team_lists_managed_author_slugs() -> None:
    project = replace(
        make_project(),
        staffing=ProjectStaffing.team,
        authors=[Author(name="A", slug="a"), Author(name="B", slug="b", managed=False)],
    )

    assert author_personas(project) == {"a"}
    assert author_personas(make_project()) == {AUTHOR_PERSONA}


def test__slot_mode_conflict__pades_with_openpgp_key__rejected() -> None:
    message = slot_mode_conflict(SignMode.image_crypto, "openpgp", [])

    assert message is not None
    assert "X.509" in message


def test__slot_mode_conflict__method_no_checkpoint_accepts__rejected() -> None:
    message = slot_mode_conflict(SignMode.image_crypto, "pkcs12", [("Заявка", ("image", "detached"))])

    assert message is not None
    assert "Заявка" in message


def test__slot_mode_conflict__one_checkpoint_accepts__allowed() -> None:
    restrictions = [("Заявка", ("image", "detached")), ("Защита", ())]

    assert slot_mode_conflict(SignMode.image_crypto, "pkcs12", restrictions) is None
    assert slot_mode_conflict(SignMode.detached_text, "openpgp", [("Заявка", ("image", "detached"))]) is None


_SKIP = SkippedSlot(profile_id="topic-approval", route_id="r1", round=1, at="2026-11-13T10:00:00+00:00")


def test__slot_state__skipped_on_the_point__skipped_before_any_other_check() -> None:
    # Пропущенный слот ничего не ждёт: ни размещения, ни файла подписи (signing-route.md, 13.3).
    state = _state(SignMode.detached, frozen={_DOC: _frozen()}, skipped={_DOC: {"supervisor": _SKIP}})

    on_point = slot_state(state, _DOC, "supervisor", _FACTS, profile_id="topic-approval")
    anywhere = slot_state(state, _DOC, "supervisor", _FACTS)
    other_point = slot_state(state, _DOC, "supervisor", _FACTS, profile_id="defence")

    assert (on_point.status, on_point.reason, on_point.method) == (SlotStatus.skipped, None, SignMethod.detached)
    assert anywhere.status is SlotStatus.skipped
    assert (other_point.status, other_point.reason) == (SlotStatus.pending, PlanReason.no_signature_file)


def _plan_slot(slot_id: str, status: SlotStatus, *, optional: bool = False, crypto: bool = False) -> PlanSlot:
    method = SignMethod.detached if crypto else SignMethod.image
    return PlanSlot(
        doc_id=_DOC,
        slot_id=slot_id,
        label={"ru": slot_id},
        signer=SignerRef(slot_id),
        mode=SignMode.detached if crypto else SignMode.image,
        state=SlotState(method, VisibleMark.png, status),
        optional=optional,
        skipped=_SKIP if status is SlotStatus.skipped else None,
        is_mine=True,
    )


def test__signature_plan__counter_leaves_out_skipped_and_optional_unsigned() -> None:
    plan = SignaturePlan(
        docs=(
            DocPlan(
                doc_id=_DOC,
                built=True,
                frozen=None,
                frozen_outdated=None,
                slots=(
                    _plan_slot("author", SlotStatus.signed),
                    _plan_slot("supervisor", SlotStatus.pending),
                    _plan_slot("co_supervisor", SlotStatus.signed, optional=True),
                    _plan_slot("academic_supervisor", SlotStatus.pending, optional=True),
                    _plan_slot("reviewer", SlotStatus.skipped, optional=True, crypto=True),
                ),
            ),
        )
    )

    assert (plan.signed, plan.total, plan.optional_pending) == (2, 3, 1)
    assert plan.waiting_for_me == 2
    # Пропущенная ЭП не делает документ документом с ЭП (13.3, инвариант 6).
    assert not plan.docs[0].has_crypto
