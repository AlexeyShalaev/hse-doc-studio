"""Файловые эффекты `Skip` и `Unskip` (docs/design/signing-route.md, 13.3): запись в состоянии подписей."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from hse_doc_studio.core.signing_route.effects import Skip, Unskip
from hse_doc_studio.core.signing_route.entities import DocSlot, ParticipantSkip, SigningRoute
from hse_doc_studio.core.value_objects import SignaturesState, SkippedSlot
from hse_doc_studio.use_cases.signing_route.effects import _apply

from tests.factories.signing_routes import DOC, make_participant, make_route

_AT = datetime(2026, 11, 13, 9, 30, tzinfo=UTC)


def _route() -> SigningRoute:
    pair = DocSlot(DOC, "academic_supervisor")
    skipped = ParticipantSkip(round=2, at=_AT, by=uuid4(), pairs=(pair,), kept_marks=(DOC,))
    people = (make_participant(3, "academic_supervisor", ["academic_supervisor"], skipped=skipped),)
    return make_route(uuid4(), participants=people, round=2)


def test__skip__writes_the_record_with_route_round_time_and_keep_mark() -> None:
    route = _route()

    state = _apply(SignaturesState.empty(), route, Skip(DOC, "academic_supervisor", True))

    assert state.skipped == {
        DOC: {
            "academic_supervisor": SkippedSlot(
                profile_id=route.profile_id,
                route_id=str(route.id),
                round=2,
                at="2026-11-13T09:30:00+00:00",
                keep_mark=True,
            )
        }
    }


def test__skip__twice__changes_nothing() -> None:
    route = _route()
    once = _apply(SignaturesState.empty(), route, Skip(DOC, "academic_supervisor", True))

    assert _apply(once, route, Skip(DOC, "academic_supervisor", True)) is once


def test__skip__pair_nobody_skipped__changes_nothing() -> None:
    state = SignaturesState.empty()

    assert _apply(state, _route(), Skip(DOC, "supervisor", False)) is state


def test__unskip__removes_the_record_and_empty_documents() -> None:
    route = _route()
    skipped = _apply(SignaturesState.empty(), route, Skip(DOC, "academic_supervisor", False))

    state = _apply(skipped, route, Unskip(DOC, "academic_supervisor"))

    assert state.skipped == {}
    assert _apply(state, route, Unskip(DOC, "academic_supervisor")) is state
