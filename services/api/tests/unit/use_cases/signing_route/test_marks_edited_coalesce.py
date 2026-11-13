"""Склейка подряд идущих `marks_edited` (docs/design/signing-route.md, 14.6).

Перетаскивание метки даты шлёт запрос на каждое отпускание: история маршрута не должна получать по событию на
каждый. Последнее событие того же автора и той же пары моложе 5 минут без сброса подписей обновляется.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
from hse_doc_studio.core.signing_route.entities import EventKind, RouteEvent
from hse_doc_studio.use_cases.signing_route.dates import COALESCE_WINDOW, _coalesced

from tests.factories.signing_routes import DOC, DOC2, T0, make_event, make_route

ROUTE = make_route(uuid4())
RESET = [{"doc_id": DOC, "slot_id": "supervisor"}]


def _marks(marks: int, *, at_s: int = 0, reset: list[Any] | None = None, **changes: Any) -> RouteEvent:
    details = {"doc_id": DOC, "slot_id": "supervisor", "marks": marks, "reset": reset or []}
    return make_event(ROUTE, EventKind.marks_edited, at=T0 + timedelta(seconds=at_s), details=details, **changes)


def _stored(event: RouteEvent, event_id: int = 7) -> RouteEvent:
    return replace(event, id=event_id)


def test__same_author_and_pair_within_window__last_event_updated() -> None:
    last = _stored(_marks(1))
    new = _marks(3, at_s=40)

    merged = _coalesced(new, [_stored(make_event(ROUTE), 6), last])

    assert merged.id == 7
    assert merged.at == new.at
    assert merged.details == {"doc_id": DOC, "slot_id": "supervisor", "marks": 3, "reset": []}


def test__no_history__new_event() -> None:
    new = _marks(1)

    assert _coalesced(new, []) is new


@pytest.mark.parametrize(
    "last",
    [
        pytest.param(_stored(_marks(1, actor_id=uuid4())), id="other_author"),
        pytest.param(_stored(_marks(1, round=ROUTE.round - 1)), id="other_round"),
        pytest.param(_stored(replace(_marks(1), details={**_marks(1).details, "slot_id": "co"})), id="other_slot"),
        pytest.param(_stored(replace(_marks(1), details={**_marks(1).details, "doc_id": DOC2})), id="other_doc"),
        pytest.param(_stored(_marks(1, reset=RESET)), id="last_reset_signatures"),
        pytest.param(_stored(make_event(ROUTE, EventKind.frozen)), id="other_kind_last"),
        pytest.param(_stored(_marks(1, at_s=-int(COALESCE_WINDOW.total_seconds()) + 40)), id="window_passed"),
    ],
)
def test__not_the_same_burst__new_event(last: RouteEvent) -> None:
    new = _marks(2, at_s=40)

    assert _coalesced(new, [last]) is new


def test__new_edit_resets_signatures__own_event() -> None:
    new = _marks(2, at_s=40, reset=RESET)

    assert _coalesced(new, [_stored(_marks(1))]) is new


def test__nine_drags_in_forty_seconds__one_event() -> None:
    history: list[RouteEvent] = []
    for i in range(9):
        event = _coalesced(_marks(i + 1, at_s=i * 5), history)
        history = [e for e in history if e.id != event.id] + [event if event.id is not None else _stored(event, i)]

    assert len(history) == 1
    assert (history[0].at, history[0].details["marks"]) == (T0 + timedelta(seconds=40), 9)
