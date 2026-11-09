"""Черновик маршрута: люди по персонам и пары «документ, слот» по участникам (docs/design/signing-route.md, 5.2, 6.5).

Чистые функции для сценариев автора. Пары назначает сервер: слот принадлежит первому участнику с персоной его
владельца (`slot_persona`), автор передаёт только людей и шаги (раздел 8). Человек шага это участник проекта с
нужной персоной; если такого нет, ожидающее приглашение с этой персоной; иначе «нет в проекте».
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from uuid import UUID, uuid4

from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.signatures.plan import slot_persona
from hse_doc_studio.core.signing_route.entities import DocSlot, Participant, RouteInputError, SigningRoute
from hse_doc_studio.core.signing_route.ports import RouteCandidate, RouteInvitee

type IdFactory = Callable[[], UUID]


@dataclass(frozen=True)
class PersonDraft:
    """Человек в шаге при правке маршрута: участник маршрута (`id`) или новый (None).

    Без `user_id` и `invitation_id` человек «нет в проекте»: такой маршрут не отправить.
    """

    persona: str
    id: UUID | None = None
    user_id: UUID | None = None
    invitation_id: str | None = None


def assign_pairs(
    participants: Sequence[Participant], pairs: Iterable[DocSlot]
) -> tuple[tuple[Participant, ...], tuple[DocSlot, ...]]:
    """Участники с назначенными парами и пары, для которых участника с персоной нет.

    Пара достаётся первому по порядку участнику с персоной владельца слота; прежние назначения заменяются.
    """
    owner_of: dict[str, UUID] = {}
    for p in participants:
        owner_of.setdefault(p.persona, p.id)
    assigned: dict[UUID, list[DocSlot]] = {p.id: [] for p in participants}
    unassigned: list[DocSlot] = []
    for pair in dict.fromkeys(pairs):
        owner = owner_of.get(slot_persona(pair.slot_id))
        if owner is None:
            unassigned.append(pair)
        else:
            assigned[owner].append(pair)
    return tuple(replace(p, assignments=tuple(assigned[p.id])) for p in participants), tuple(unassigned)


def pick_person(
    persona: str,
    candidates: Sequence[RouteCandidate],
    invitees: Sequence[RouteInvitee],
    *,
    prefer: UUID | None = None,
) -> tuple[UUID | None, str | None]:
    """Кто займёт персону в заготовке: `prefer` (обычно отправитель), если у него она есть, иначе первый участник
    проекта с ней, иначе ожидающее приглашение с ней. (None, None): человека нет."""
    holders = [c.user_id for c in candidates if c.persona == persona]
    if prefer is not None and prefer in holders:
        return prefer, None
    if holders:
        return holders[0], None
    invitation = next((i.invitation_id for i in invitees if i.persona == persona), None)
    return None, invitation


def draft_participants(
    steps: Sequence[Sequence[str]],
    candidates: Sequence[RouteCandidate],
    invitees: Sequence[RouteInvitee],
    *,
    prefer: UUID | None = None,
    new_id: IdFactory = uuid4,
) -> tuple[Participant, ...]:
    """Участники заготовки из шагов персон (`default_route`): по человеку на персону, шаг с 1."""
    people: list[Participant] = []
    for number, personas in enumerate(steps, start=1):
        for persona in personas:
            user_id, invitation_id = pick_person(persona, candidates, invitees, prefer=prefer)
            people.append(
                Participant(id=new_id(), step=number, persona=persona, user_id=user_id, invitation_id=invitation_id)
            )
    return tuple(people)


def resolve_unassigned(
    participants: Sequence[Participant],
    candidates: Sequence[RouteCandidate],
    invitees: Sequence[RouteInvitee],
    *,
    prefer: UUID | None = None,
) -> tuple[Participant, ...]:
    """Человек участникам без `user_id` и `invitation_id`, как в заготовке, но без повторов.

    На персону ставится ещё не занятый в маршруте участник проекта (`prefer` первым), иначе ещё не занятое
    приглашение с этой персоной. Если все заняты, участник остаётся «нет в проекте»: например, второй научрук
    из «Добавить согласующего», когда в проекте научрук один.
    """
    users = {p.user_id for p in participants if p.user_id is not None}
    invited = {p.invitation_id for p in participants if p.invitation_id is not None}
    result: list[Participant] = []
    for p in participants:
        if p.user_id is not None or p.invitation_id is not None:
            result.append(p)
            continue
        free_people = [c for c in candidates if c.user_id not in users]
        free_invites = [i for i in invitees if i.invitation_id not in invited]
        user_id, invitation_id = pick_person(
            p.persona, free_people, free_invites, prefer=prefer if prefer not in users else None
        )
        result.append(replace(p, user_id=user_id, invitation_id=invitation_id))
        users |= {user_id} if user_id is not None else set()
        invited |= {invitation_id} if invitation_id is not None else set()
    return tuple(result)


def inherit_participants(previous: SigningRoute) -> tuple[Participant, ...]:
    """Состав прежнего маршрута точки для нового: люди, шаги и id те же, согласий и запросов нет."""
    return tuple(replace(p, approval=None, notified=None, reminded_at=None, reminders=0) for p in previous.participants)


def apply_people(
    current: Sequence[Participant], steps: Sequence[Sequence[PersonDraft]], *, new_id: IdFactory = uuid4
) -> tuple[Participant, ...]:
    """Люди и шаги из запроса правки поверх участников маршрута; номер шага это индекс шага плюс 1.

    Участник находится по `id`, а без него по той же персоне и тому же человеку: так согласие переживает правку и
    переносится при отправке заново. Сменился человек или персона: согласие и запросы сбрасываются. Неизвестный
    `id` заводит нового участника.
    """
    known = {p.id: p for p in current}
    used: set[UUID] = set()
    people: list[Participant] = []
    for number, drafts in enumerate(steps, start=1):
        if not drafts:
            raise RouteInputError("bad_step", localized_error("Шаг маршрута пуст", "A route step is empty"))
        for draft in drafts:
            found = _match(draft, known, used)
            if found is not None and found.id in used:
                raise RouteInputError(
                    "duplicate_participant", localized_error("Участник указан дважды", "A participant is listed twice")
                )
            people.append(_merge(found, draft, number, new_id))
            used.add(people[-1].id)
    return tuple(people)


def _match(draft: PersonDraft, known: dict[UUID, Participant], used: set[UUID]) -> Participant | None:
    if draft.id is not None and draft.id in known:
        return known[draft.id]
    if draft.user_id is None and draft.invitation_id is None:
        return None
    return next(
        (
            p
            for p in known.values()
            if p.id not in used
            and p.persona == draft.persona
            and p.user_id == draft.user_id
            and p.invitation_id == draft.invitation_id
        ),
        None,
    )


def _merge(found: Participant | None, draft: PersonDraft, step: int, new_id: IdFactory) -> Participant:
    fresh = Participant(
        id=new_id(), step=step, persona=draft.persona, user_id=draft.user_id, invitation_id=draft.invitation_id
    )
    if found is None:
        return fresh
    same = (found.persona, found.user_id, found.invitation_id) == (draft.persona, draft.user_id, draft.invitation_id)
    if same:
        return replace(found, step=step)
    return replace(fresh, id=found.id)
