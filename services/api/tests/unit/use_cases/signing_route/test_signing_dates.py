"""Дата подписания в сценариях маршрута (docs/design/signing-route.md, 14.4 и 14.6): запись момента согласия у
размещения, сброшенные перефиксацией ЭП и повторный запрос подписи их владельцам."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

from hse_doc_studio.core.enums import DateMarkFormat, DetachedFormat, DetachedOrigin, DetachedVerdict, SignedAtSource
from hse_doc_studio.core.signing_route.effects import Notify, RecordSignedAt
from hse_doc_studio.core.signing_route.engine import Evaluation, ParticipantView, RouteFacts
from hse_doc_studio.core.signing_route.entities import (
    DocSlot,
    NextAction,
    Notice,
    ParticipantState,
    RequestOutcome,
    RoutePhase,
    RouteStatus,
    SigningRoute,
)
from hse_doc_studio.core.value_objects import (
    DateMark,
    DetachedSignature,
    FrozenPdf,
    SignaturePlacement,
    SignaturesState,
    SignedAt,
)
from hse_doc_studio.use_cases.signing_route.effects import _apply, record_signed_at
from hse_doc_studio.use_cases.signing_route.facts import LoadedFacts
from hse_doc_studio.use_cases.signing_route.scenario import Settled, dropped_signatures, resign_requests

from tests.factories.signing_routes import DOC, DOC2, make_route

_AT = datetime(2026, 11, 12, 22, 30, tzinfo=UTC)  # 13 ноября 01:30 по Москве
_MARK = DateMark("d1", 1, 120.0, 250.0, 8.0, 5.0, DateMarkFormat.day)
_B = "c" * 64


def _placed(*, dates: tuple[DateMark, ...] = (_MARK,), signed_at: SignedAt | None = None) -> SignaturesState:
    placement = SignaturePlacement(enabled=True, page=1, x_mm=10, y_mm=10, width_mm=30, dates=dates)
    return replace(SignaturesState.empty(), placements={DOC: {"supervisor": replace(placement, signed_at=signed_at)}})


def _signature(slot_id: str) -> DetachedSignature:
    return DetachedSignature(
        file=f".hse-studio/detached/{DOC}/{slot_id}.asc",
        format=DetachedFormat.openpgp,
        origin=DetachedOrigin.studio,
        pdf_sha256="a" * 64,
        verdict=DetachedVerdict.valid,
        signer=slot_id,
        signer_id=slot_id,
        added_at=_AT.isoformat(),
    )


def _frozen(sha256: str) -> FrozenPdf:
    return FrozenPdf(path="f.pdf", sha256=sha256, source_sha256="s", size=1, frozen_at=_AT.isoformat())


def test__record_signed_at__moment_in_utc_with_the_token() -> None:
    moscow = timezone(timedelta(hours=3))

    state = record_signed_at(_placed(), RecordSignedAt(DOC, "supervisor", _AT.astimezone(moscow), "build:x"))

    assert state.placements[DOC]["supervisor"].signed_at == SignedAt(
        at="2026-11-12T22:30:00+00:00", source=SignedAtSource.approval, token="build:x"
    )


def test__record_signed_at__replaces_a_manual_date__same_record_changes_nothing() -> None:
    manual = _placed(signed_at=SignedAt(at="2026-11-01", source=SignedAtSource.manual))
    effect = RecordSignedAt(DOC, "supervisor", _AT, "build:x")

    once = _apply(manual, make_route(uuid4()), effect)

    assert once.placements[DOC]["supervisor"].signed_at is not None
    assert once.placements[DOC]["supervisor"].signed_at.source is SignedAtSource.approval
    assert record_signed_at(once, effect) is once


def test__record_signed_at__no_placement__nothing_written() -> None:
    state = SignaturesState.empty()

    assert record_signed_at(state, RecordSignedAt(DOC, "supervisor", _AT, "build:x")) is state


def test__dropped_signatures__only_signatures_gone_from_refrozen_documents() -> None:
    before = replace(
        SignaturesState.empty(),
        detached={
            DOC: {"author": _signature("author"), "supervisor": _signature("supervisor")},
            DOC2: {"x": _signature("x")},
        },
    )
    after = replace(before, detached={DOC: {"author": _signature("author")}})

    assert dropped_signatures(before, after, (DOC,)) == (DocSlot(DOC, "supervisor"),)


def _settled(route: SigningRoute, actions: dict[str, NextAction], reset: tuple[DocSlot, ...]) -> Settled:
    views = tuple(
        ParticipantView(
            participant_id=p.id,
            step=p.step,
            state=ParticipantState.to_sign if actions[p.persona] is NextAction.sign else ParticipantState.waiting,
            next_action=actions[p.persona],
            remaining_actions=1,
            changes_visible=False,
        )
        for p in route.participants
    )
    evaluation = Evaluation(RouteStatus.active, RoutePhase.signing, 0, 3, route.steps, views)
    state = replace(SignaturesState.empty(), frozen={DOC: _frozen(_B)})
    return Settled(route, LoadedFacts(state, RouteFacts(docs={}, state=state)), evaluation, (DOC,), reset)


def test__resign_requests__owners_waiting_to_sign_get_a_request_with_the_new_b() -> None:
    route = make_route(uuid4(), status=RouteStatus.active, round=1)
    people = {p.persona: p for p in route.participants}
    actions = {"author": NextAction.sign, "supervisor": NextAction.done, "academic_supervisor": NextAction.sign}
    reset = (DocSlot(DOC, "author"), DocSlot(DOC, "supervisor"))

    requests = resign_requests(_settled(route, actions, reset), ())

    assert requests == (Notify(Notice.request, (people["author"].id,), outcome=RequestOutcome.sign, again=_B[:12]),)


def test__resign_requests__already_asked_in_this_pass_or_nothing_reset__no_second_request() -> None:
    route = make_route(uuid4(), status=RouteStatus.active, round=1)
    author = next(p for p in route.participants if p.persona == "author")
    actions = {"author": NextAction.sign, "supervisor": NextAction.done, "academic_supervisor": NextAction.wait}
    asked = (Notify(Notice.request, (author.id,), outcome=RequestOutcome.sign),)

    assert resign_requests(_settled(route, actions, (DocSlot(DOC, "author"),)), asked) == ()
    assert resign_requests(_settled(route, actions, ()), ()) == ()
