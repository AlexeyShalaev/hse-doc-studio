"""Черновик маршрута: люди по персонам, пары по участникам, правка людей (docs/design/signing-route.md, 5.2, 6.5)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.signing_route.drafting import (
    PersonDraft,
    apply_people,
    assign_pairs,
    draft_participants,
    inherit_participants,
    pick_person,
)
from hse_doc_studio.core.signing_route.entities import (
    Approval,
    DocSlot,
    Notified,
    Participant,
    RequestOutcome,
    RouteInputError,
)
from hse_doc_studio.core.signing_route.ports import RouteCandidate, RouteInvitee

from tests.factories.signing_routes import make_route

AUTHOR = UUID(int=1)
PETROV = UUID(int=2)
SIDOROV = UUID(int=3)
T0 = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
CANDIDATES = [
    RouteCandidate(AUTHOR, "Иванов", "author"),
    RouteCandidate(PETROV, "Петров", "supervisor"),
    RouteCandidate(SIDOROV, "Сидоров", "supervisor"),
]
INVITEES = [RouteInvitee("inv_academic", "academic_supervisor", "a***@hse.ru")]


def test__pick_person__member_first_then_invitation_then_nobody() -> None:
    assert pick_person("supervisor", CANDIDATES, INVITEES) == (PETROV, None)
    assert pick_person("supervisor", CANDIDATES, INVITEES, prefer=SIDOROV) == (SIDOROV, None)
    assert pick_person("supervisor", CANDIDATES, INVITEES, prefer=AUTHOR) == (PETROV, None)
    assert pick_person("academic_supervisor", CANDIDATES, INVITEES) == (None, "inv_academic")
    assert pick_person("co_supervisor", CANDIDATES, INVITEES) == (None, None)


def test__draft_participants__one_person_per_persona_steps_from_one() -> None:
    steps = (("author",), ("supervisor", "co_supervisor"), ("academic_supervisor",))

    people = draft_participants(steps, CANDIDATES, INVITEES, prefer=AUTHOR)

    assert [(p.step, p.persona, p.user_id, p.invitation_id) for p in people] == [
        (1, "author", AUTHOR, None),
        (2, "supervisor", PETROV, None),
        (2, "co_supervisor", None, None),
        (3, "academic_supervisor", None, "inv_academic"),
    ]
    assert len({p.id for p in people}) == 4
    assert all(not p.assignments for p in people)


def test__assign_pairs__slot_to_first_participant_with_its_persona() -> None:
    first = Participant(id=uuid4(), step=1, persona="author")
    second = Participant(id=uuid4(), step=2, persona="supervisor", assignments=(DocSlot("old", "supervisor"),))
    twin = Participant(id=uuid4(), step=2, persona="supervisor")
    pairs = [
        DocSlot("proposal", "supervisor"),
        DocSlot("application", "author"),
        DocSlot("application", "supervisor"),
        DocSlot("application", "academic_supervisor"),
        DocSlot("application", "author"),
    ]

    assigned, unassigned = assign_pairs([first, second, twin], pairs)

    assert [p.assignments for p in assigned] == [
        (DocSlot("application", "author"),),
        (DocSlot("proposal", "supervisor"), DocSlot("application", "supervisor")),
        (),
    ]
    assert unassigned == (DocSlot("application", "academic_supervisor"),)


def test__assign_pairs__team_author_slot__goes_to_author_slug() -> None:
    anna = Participant(id=uuid4(), step=1, persona="anna")
    boris = Participant(id=uuid4(), step=1, persona="boris")

    assigned, unassigned = assign_pairs([anna, boris], [DocSlot("tz", "author--boris"), DocSlot("tz", "author--anna")])

    assert [p.assignments for p in assigned] == [(DocSlot("tz", "author--anna"),), (DocSlot("tz", "author--boris"),)]
    assert unassigned == ()


def test__inherit_participants__people_and_ids_kept_consent_dropped() -> None:
    route = make_route(uuid4())
    voted = route.participants[0]
    previous = route.with_participant(
        Participant(
            id=voted.id,
            step=voted.step,
            persona=voted.persona,
            user_id=voted.user_id,
            assignments=voted.assignments,
            approval=Approval(round=2, tokens={"d": "build:x"}, at=T0),
            notified=Notified(round=2, outcome=RequestOutcome.approve, at=T0),
            reminded_at=T0,
            reminders=2,
        )
    )

    people = inherit_participants(previous)

    assert [(p.id, p.step, p.persona, p.user_id) for p in people] == [
        (p.id, p.step, p.persona, p.user_id) for p in previous.participants
    ]
    assert all(p.approval is None and p.notified is None and p.reminders == 0 for p in people)


def _current() -> tuple[Participant, Participant]:
    author = Participant(
        id=uuid4(),
        step=1,
        persona="author",
        user_id=AUTHOR,
        approval=Approval(round=1, tokens={"d": "build:x"}, at=T0),
    )
    supervisor = Participant(id=uuid4(), step=2, persona="supervisor", user_id=PETROV)
    return author, supervisor


def test__apply_people__by_id_keeps_consent_and_renumbers_steps() -> None:
    author, supervisor = _current()

    people = apply_people(
        [author, supervisor],
        [
            [PersonDraft("supervisor", supervisor.id, PETROV)],
            [PersonDraft("author", author.id, AUTHOR), PersonDraft("academic_supervisor", invitation_id="inv_1")],
        ],
    )

    assert [(p.step, p.persona) for p in people] == [(1, "supervisor"), (2, "author"), (2, "academic_supervisor")]
    assert people[1].id == author.id
    assert people[1].approval == author.approval
    assert people[2].invitation_id == "inv_1"
    assert people[2].id not in {author.id, supervisor.id}


def test__apply_people__same_person_without_id__matched_by_persona_and_user() -> None:
    author, supervisor = _current()

    people = apply_people([author, supervisor], [[PersonDraft("author", user_id=AUTHOR)]])

    assert people == (Participant(id=author.id, step=1, persona="author", user_id=AUTHOR, approval=author.approval),)


def test__apply_people__other_person_in_same_participant__consent_dropped_id_kept() -> None:
    author, supervisor = _current()

    people = apply_people([author, supervisor], [[PersonDraft("author", author.id, SIDOROV)]])

    assert people == (Participant(id=author.id, step=1, persona="author", user_id=SIDOROV),)


def test__apply_people__unknown_id__new_participant() -> None:
    author, _ = _current()
    stranger = uuid4()

    people = apply_people([author], [[PersonDraft("author", stranger, AUTHOR)]])

    assert people[0].id != stranger
    assert people[0].id == author.id  # тот же человек с той же персоной: найден без id


def test__apply_people__empty_step__bad_step() -> None:
    author, _ = _current()

    with pytest.raises(RouteInputError) as exc:
        apply_people([author], [[PersonDraft("author", author.id, AUTHOR)], []])

    assert exc.value.code == "bad_step"


def test__apply_people__same_participant_twice__duplicate_participant() -> None:
    author, _ = _current()
    twice = PersonDraft("author", author.id, AUTHOR)

    with pytest.raises(RouteInputError) as exc:
        apply_people([author], [[twice], [twice]])

    assert exc.value.code == "duplicate_participant"
