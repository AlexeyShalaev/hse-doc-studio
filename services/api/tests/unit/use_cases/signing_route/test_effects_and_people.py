"""Файловые эффекты маршрута и люди маршрута глазами автора (docs/design/signing-route.md, 6.1, 6.2 и 8.2)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from hse_doc_studio.core.enums import SignMode
from hse_doc_studio.core.signing_route.effects import FillPlate, Release, Withhold
from hse_doc_studio.core.signing_route.entities import Approval, EventKind, Participant, RouteEvent
from hse_doc_studio.core.signing_route.ports import RouteInvitee
from hse_doc_studio.core.value_objects import SignaturePlacement, SignatureSlot, SignaturesState, SignerInfo
from hse_doc_studio.use_cases.signing_route.effects import _apply, _date_plates
from hse_doc_studio.use_cases.signing_route.views import Membership, People, _event

from tests.factories.signing_routes import make_route

T0 = datetime(2026, 11, 12, 21, 30, tzinfo=UTC)
PETROV = UUID(int=2)
SIGNER = SignerInfo(kind="openpgp", owner="Петров П. П.", cert_id="1A2B", signer_id="ABCD")


def _placement(date: str | None = None) -> SignaturePlacement:
    return SignaturePlacement(enabled=True, page=1, x_mm=10, y_mm=10, width_mm=30, sign_date=date)


def _state(**changes: Any) -> SignaturesState:
    state = SignaturesState(
        slots={
            "supervisor": SignatureSlot(png_path="s.png", natural_width_px=1, natural_height_px=1),
            "plate": SignatureSlot(None, None, None, sign_mode=SignMode.detached_text),
        },
        placements={"doc": {"supervisor": _placement("2026-01-01"), "plate": _placement("2026-01-01")}},
    )
    return replace(state, **changes)


def test__withhold_then_release__slot_held_and_back_with_approval_date() -> None:
    route = make_route(uuid4())
    supervisor = route.participants[1]
    route = route.with_participant(
        Participant(
            id=supervisor.id,
            step=2,
            persona="supervisor",
            user_id=supervisor.user_id,
            approval=Approval(round=1, tokens={}, at=T0),
        )
    )

    held = _apply(_state(), route, Withhold("doc", "supervisor"))
    again = _apply(held, route, Withhold("doc", "supervisor"))
    released = _apply(held, route, Release("doc", "supervisor", supervisor.id))

    assert held.withheld == {"doc": frozenset({"supervisor"})}
    assert again is held
    assert released.withheld == {}
    assert released.placements["doc"]["supervisor"].sign_date == "2026-11-12"
    assert released.placements["doc"]["plate"].sign_date == "2026-01-01"


def test__release__placement_without_date__date_not_added() -> None:
    route = make_route(uuid4())
    state = _state(placements={"doc": {"supervisor": _placement(None)}}, withheld={"doc": frozenset({"supervisor"})})

    released = _apply(state, route, Release("doc", "supervisor", route.participants[1].id))

    assert released.placements["doc"]["supervisor"].sign_date is None
    assert released.withheld == {}


def test__fill_plate__only_empty_plate_is_filled() -> None:
    route = make_route(uuid4())
    other = SignerInfo(kind="x509", owner="Другой", cert_id="99")

    filled = _apply(_state(), route, FillPlate("plate", route.participants[1].id, SIGNER))
    kept = _apply(filled, route, FillPlate("plate", route.participants[1].id, other))

    assert filled.slots["plate"].signer == SIGNER
    assert kept.slots["plate"].signer == SIGNER


def test__freeze_date__only_plates_get_the_freeze_date() -> None:
    dated = _date_plates(_state(), "doc", T0)

    assert dated.placements["doc"]["plate"].sign_date == "2026-11-12"
    assert dated.placements["doc"]["supervisor"].sign_date == "2026-01-01"


def _people() -> People:
    return People(
        names={PETROV: "Петров П. П."},
        invitees={"inv_1": RouteInvitee("inv_1", "academic_supervisor", "a***@hse.ru")},
        personas={PETROV: frozenset({"supervisor"})},
    )


def test__people__membership_and_names() -> None:
    people = _people()
    member = Participant(id=uuid4(), step=1, persona="supervisor", user_id=PETROV)
    left = Participant(id=uuid4(), step=1, persona="co_supervisor", user_id=PETROV)
    acted = Participant(id=uuid4(), step=1, persona="co_supervisor", user_id=PETROV, approval=Approval(1, {}, T0))
    invited = Participant(id=uuid4(), step=2, persona="academic_supervisor", invitation_id="inv_1")
    expired = Participant(id=uuid4(), step=2, persona="academic_supervisor", invitation_id="inv_gone")
    nobody = Participant(id=uuid4(), step=2, persona="academic_supervisor")

    assert [people.membership(p) for p in (member, left, invited, expired, nobody)] == [
        Membership.member,
        Membership.missing,
        Membership.invited,
        Membership.missing,
        Membership.missing,
    ]
    # Чужого человека без персоны шага не называем, пока он не действовал в маршруте.
    assert [people.name(p) for p in (member, left, acted, invited, expired, nobody)] == [
        "Петров П. П.",
        None,
        "Петров П. П.",
        "a***@hse.ru",
        None,
        None,
    ]


def test__event__return_comment_only_for_those_who_may_see_it() -> None:
    route = make_route(uuid4())
    event = RouteEvent(
        route.id,
        1,
        T0,
        EventKind.returned,
        actor_id=PETROV,
        details={"comment": "Уточните цель", "reason": "returned"},
    )

    shown = _event(event, _people(), show_comments=True)
    hidden = _event(event, _people(), show_comments=False)

    assert (shown.who, shown.comment, shown.reason) == ("Петров П. П.", "Уточните цель", "returned")
    assert (hidden.who, hidden.comment) == ("Петров П. П.", None)
