"""Контракт хранилища маршрутов подписания: одни и те же проверки на InMemory и Postgres.

Маршрут возвращается ровно таким, каким сохранён; версия не даёт затереть чужую запись; у точки один
незавершённый маршрут; документ держит один маршрут; запросы сценариев R5–R8 находят нужные маршруты.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from hse_doc_studio.core.signing_route.entities import (
    EventKind,
    RouteConflictError,
    RouteStatus,
    SigningRoute,
    StopReason,
)
from hse_doc_studio.core.signing_route.repositories import (
    DocumentOnRouteError,
    ISigningRouteRepository,
    OpenRouteExistsError,
    StaleRouteError,
)
from pytest_lazy_fixtures import lf

from tests.factories.signing_routes import (
    DOC,
    DOC2,
    T0,
    make_event,
    make_full_route,
    make_participant,
    make_route,
    stopped,
)
from tests.fakes.signing_routes import InMemorySigningRouteRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

P1 = UUID("00000000-0000-4000-8000-0000000000a1")
P2 = UUID("00000000-0000-4000-8000-0000000000a2")
_S = RouteStatus


@pytest_asyncio.fixture
async def memory_repo() -> ISigningRouteRepository:
    return InMemorySigningRouteRepository()


@pytest_asyncio.fixture
async def pg_repo(pg_migrated_engine: AsyncEngine) -> ISigningRouteRepository:
    from hse_doc_studio.infra.db.engine import create_sessionmaker
    from hse_doc_studio.infra.db.repositories.signing_routes import SqlSigningRouteRepository
    from hse_doc_studio.infra.db.session import SessionProvider

    from tests.factories.pg_projects import seed_project

    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))
    for project_id in (P1, P2):
        await seed_project(sessions, owner_user_id=None, project_id=project_id)
    return SqlSigningRouteRepository(sessions)


@pytest.fixture(params=[lf("memory_repo"), pytest.param(lf("pg_repo"), marks=pytest.mark.pg)], ids=["in_memory", "pg"])
def repo(request: pytest.FixtureRequest) -> ISigningRouteRepository:
    return request.param


# --- маршрут целиком ---


@pytest.mark.parametrize(
    "build",
    [
        pytest.param(lambda: make_route(P1), id="draft"),
        pytest.param(lambda: make_full_route(P1), id="active_full"),
        pytest.param(
            lambda: (lambda r: replace(stopped(r, r.participants[1]), completed_at=T0 + timedelta(days=1)))(
                make_full_route(P1)
            ),
            id="returned",
        ),
        pytest.param(
            lambda: (lambda r: stopped(r, r.participants[3], StopReason.participant_left))(make_full_route(P1)),
            id="paused",
        ),
        pytest.param(lambda: make_route(P1, participants=(), docs=()), id="empty"),
    ],
)
async def test__add__then_get__round_trips_every_field(repo: ISigningRouteRepository, build) -> None:
    route: SigningRoute = build()

    stored = await repo.add(route)
    loaded = await repo.get(P1, route.id)

    assert stored == replace(route, version=1)
    assert loaded == stored


async def test__get__keeps_order_of_docs_participants_snapshot_and_tokens(repo: ISigningRouteRepository) -> None:
    route = make_full_route(P1)
    await repo.add(route)

    loaded = await repo.get(P1, route.id)

    assert loaded is not None
    assert loaded.docs == (DOC2, DOC)
    assert [p.id for p in loaded.participants] == [p.id for p in route.participants]
    assert list(loaded.snapshot) == [DOC2, DOC]
    author = loaded.participants[0]
    assert author.approval is not None
    assert list(author.approval.tokens) == [DOC, DOC2]
    assert author.assignments == route.participants[0].assignments


async def test__get__other_project__none(repo: ISigningRouteRepository) -> None:
    route = make_route(P1)
    await repo.add(route)

    assert await repo.get(P2, route.id) is None
    assert await repo.get(P1, uuid4()) is None


async def test__add__already_stored_version__rejected(repo: ISigningRouteRepository) -> None:
    with pytest.raises(ValueError, match="already stored"):
        await repo.add(replace(make_route(P1), version=1))


async def test__add__participants_taken_from_previous_route__keep_their_ids(repo: ISigningRouteRepository) -> None:
    old = await repo.add(make_route(P1, status=_S.archived))

    new = await repo.add(make_route(P1, participants=old.participants))

    loaded = await repo.get(P1, new.id)
    assert loaded is not None
    assert loaded.participants == old.participants
    assert await repo.get(P1, old.id) == old


# --- версия ---


async def test__save__bumps_version_and_replaces_contents(repo: ISigningRouteRepository) -> None:
    route = await repo.add(make_route(P1))
    shorter = replace(route, participants=route.participants[:1], message="Только автор", docs=(DOC, DOC2))

    saved = await repo.save(shorter)
    loaded = await repo.get(P1, route.id)

    assert saved.version == 2
    assert loaded == saved
    assert loaded is not None
    assert len(loaded.participants) == 1


async def test__save__stale_version__rejected_and_stored_route_untouched(repo: ISigningRouteRepository) -> None:
    route = await repo.add(make_route(P1))
    first, second = replace(route, message="первый"), replace(route, message="второй")
    winner = await repo.save(first)

    with pytest.raises(StaleRouteError) as exc:
        await repo.save(second, events=[make_event(route, EventKind.approved)])

    assert exc.value.code == "stale_route"
    assert isinstance(exc.value, RouteConflictError)
    assert await repo.get(P1, route.id) == winner
    assert await repo.list_events(route.id) == []


async def test__save__after_reread__succeeds(repo: ISigningRouteRepository) -> None:
    route = await repo.add(make_route(P1))
    await repo.save(replace(route, message="первый"))

    fresh = await repo.get(P1, route.id)
    assert fresh is not None
    saved = await repo.save(replace(fresh, message="второй"))

    assert (saved.version, saved.message) == (3, "второй")


async def test__save__never_added__stale(repo: ISigningRouteRepository) -> None:
    with pytest.raises(StaleRouteError):
        await repo.save(replace(make_route(P1), version=1))


async def test__save__under_other_project__stale_and_untouched(repo: ISigningRouteRepository) -> None:
    stored = await repo.add(make_route(P1))

    with pytest.raises(StaleRouteError):
        await repo.save(replace(stored, project_id=P2))

    assert await repo.get(P1, stored.id) == stored
    assert await repo.get(P2, stored.id) is None


# --- события ---


async def test__events__appended_in_order_and_filtered_by_round(repo: ISigningRouteRepository) -> None:
    route = make_route(P1)
    sent = make_event(route, EventKind.sent, round=1)
    stored = await repo.add(route, events=[sent])
    returned = make_event(
        route,
        EventKind.returned,
        round=1,
        at=T0 + timedelta(hours=1),
        actor_id=route.participants[1].user_id,
        participant_id=route.participants[1].id,
        details={"comment": "Уточните цель", "docs": [DOC], "step": 2},
    )
    resent = make_event(route, EventKind.sent, round=2, at=T0 + timedelta(hours=2), actor_id=None)
    await repo.save(stored, events=[returned, resent])

    assert await repo.list_events(route.id) == [sent, returned, resent]
    assert await repo.list_events(route.id, round=1) == [sent, returned]
    assert await repo.list_events(uuid4()) == []


async def test__events__of_other_route__rejected(repo: ISigningRouteRepository) -> None:
    route = make_route(P1)

    with pytest.raises(ValueError, match="cannot be stored"):
        await repo.add(route, events=[make_event(make_route(P1))])

    assert await repo.get(P1, route.id) is None


# --- один незавершённый маршрут на точку ---


async def test__add__second_open_route_of_checkpoint__rejected(repo: ISigningRouteRepository) -> None:
    first = await repo.add(make_route(P1))

    with pytest.raises(OpenRouteExistsError) as exc:
        await repo.add(make_route(P1))

    assert exc.value.code == "route_exists"
    assert [r.id for r in await repo.list_for_project(P1)] == [first.id]


async def test__add__open_routes_of_other_checkpoint_or_project__allowed(repo: ISigningRouteRepository) -> None:
    await repo.add(make_route(P1))

    await repo.add(make_route(P1, profile_id="final"))
    await repo.add(make_route(P2))

    assert len(await repo.list_for_project(P1)) == 2


@pytest.mark.parametrize("closed", [_S.cancelled, _S.completed, _S.archived])
async def test__add__previous_route_closed__new_open_route_allowed(repo: ISigningRouteRepository, closed) -> None:
    old = await repo.add(make_route(P1))
    await repo.save(replace(old, status=closed))

    new = await repo.add(make_route(P1))

    assert (await repo.get_open(P1, "topic-approval")) == new


async def test__save__resend_cancelled_while_another_open__rejected(repo: ISigningRouteRepository) -> None:
    cancelled = await repo.save(replace(await repo.add(make_route(P1)), status=_S.cancelled))
    await repo.add(make_route(P1))

    with pytest.raises(OpenRouteExistsError):
        await repo.save(replace(cancelled, status=_S.active, round=1))

    assert await repo.get(P1, cancelled.id) == cancelled


# --- документ держит один маршрут ---


async def test__save__document_held_by_other_route__rejected_and_untouched(repo: ISigningRouteRepository) -> None:
    holder = await repo.add(make_route(P1, docs=(DOC,), status=_S.active))
    other = await repo.add(make_route(P1, profile_id="final", docs=(DOC2, DOC)))

    with pytest.raises(DocumentOnRouteError) as exc:
        await repo.save(replace(other, status=_S.active, round=1))

    assert exc.value.code == "doc_on_route"
    assert exc.value.doc_ids == (DOC,)
    assert await repo.get(P1, other.id) == other
    assert await repo.holding(P1, DOC) == holder
    assert await repo.holding(P1, DOC2) is None


async def test__add__holding_route_on_held_document__rejected(repo: ISigningRouteRepository) -> None:
    await repo.add(make_route(P1, docs=(DOC,), status=_S.completed, phase=None))

    with pytest.raises(DocumentOnRouteError):
        await repo.add(make_route(P1, profile_id="final", docs=(DOC,), status=_S.active))

    assert len(await repo.list_for_project(P1)) == 1


async def test__drafts__do_not_hold_documents(repo: ISigningRouteRepository) -> None:
    await repo.add(make_route(P1, docs=(DOC,)))
    await repo.add(make_route(P1, profile_id="final", docs=(DOC,)))

    assert await repo.holding(P1, DOC) is None


@pytest.mark.parametrize("released", [_S.archived, _S.cancelled])
async def test__holding__released_route__frees_document(repo: ISigningRouteRepository, released) -> None:
    holder = await repo.add(make_route(P1, docs=(DOC,), status=_S.completed))
    await repo.save(replace(holder, status=released))
    other = await repo.add(make_route(P1, profile_id="final", docs=(DOC,)))

    sent = await repo.save(replace(other, status=_S.active))

    assert await repo.holding(P1, DOC) == sent


@pytest.mark.parametrize("status", [_S.active, _S.paused, _S.returned, _S.completed])
async def test__holding__holding_statuses__found_only_in_own_project(repo: ISigningRouteRepository, status) -> None:
    route = await repo.add(make_route(P1, docs=(DOC,), status=status))

    assert await repo.holding(P1, DOC) == route
    assert await repo.holding(P2, DOC) is None


async def test__holding__same_doc_in_other_project__independent(repo: ISigningRouteRepository) -> None:
    mine = await repo.add(make_route(P1, docs=(DOC,), status=_S.active))
    theirs = await repo.add(make_route(P2, docs=(DOC,), status=_S.active))

    assert (await repo.holding(P1, DOC), await repo.holding(P2, DOC)) == (mine, theirs)


# --- запросы ---


async def test__get_open__open_route_of_checkpoint(repo: ISigningRouteRepository) -> None:
    await repo.add(make_route(P1, status=_S.archived))
    open_route = await repo.add(make_route(P1, status=_S.returned))
    await repo.add(make_route(P1, profile_id="final"))

    assert await repo.get_open(P1, "topic-approval") == open_route
    assert await repo.get_open(P2, "topic-approval") is None


async def test__get_open__only_closed_routes__none(repo: ISigningRouteRepository) -> None:
    await repo.add(make_route(P1, status=_S.completed))
    await repo.add(make_route(P1, status=_S.cancelled))

    assert await repo.get_open(P1, "topic-approval") is None


async def test__list_for_project__newest_first_with_filters(repo: ISigningRouteRepository) -> None:
    first = await repo.add(make_route(P1, status=_S.archived))
    second = await repo.add(make_route(P1, profile_id="final"))
    third = await repo.add(make_route(P1, status=_S.active))
    await repo.add(make_route(P2))

    assert await repo.list_for_project(P1) == [third, second, first]
    assert await repo.list_for_project(P1, profile_id="topic-approval") == [third, first]
    assert await repo.list_for_project(P1, statuses={_S.active, _S.draft}) == [third, second]
    assert await repo.list_for_project(P1, profile_id="final", statuses={_S.active}) == []


async def test__list_watching__active_and_completed(repo: ISigningRouteRepository) -> None:
    active = await repo.add(make_route(P1, status=_S.active))
    completed = await repo.add(make_route(P1, profile_id="final", status=_S.completed, docs=(DOC2,)))
    for status in (_S.draft, _S.paused, _S.returned, _S.cancelled, _S.archived):
        await repo.add(make_route(P1, profile_id=f"p-{status}", status=status, docs=(), participants=()))
        await repo.add(make_route(P2, profile_id=f"p-{status}", status=status, docs=(), participants=()))
    other = await repo.add(make_route(P2, status=_S.active))

    assert await repo.list_watching(P1) == [completed, active]
    assert await repo.list_watching() == [other, completed, active]


async def test__list_for_user__routes_where_user_participates(repo: ISigningRouteRepository) -> None:
    signer = make_participant(2, "supervisor", ["supervisor"])
    user = signer.user_id
    assert user is not None
    draft = await repo.add(make_route(P1, participants=(signer,)))
    active = await repo.add(
        make_route(P1, profile_id="final", participants=(replace(signer, id=uuid4()),), status=_S.active)
    )
    elsewhere = await repo.add(make_route(P2, participants=(replace(signer, id=uuid4()),), status=_S.active))
    await repo.add(make_route(P2, profile_id="final", created_by=user))

    assert await repo.list_for_user(user) == [elsewhere, active, draft]
    assert await repo.list_for_user(user, statuses={_S.active}) == [elsewhere, active]
    assert await repo.list_for_user(user, project_id=P1) == [active, draft]
    assert await repo.list_for_user(uuid4()) == []


async def test__list_for_invitation__routes_awaiting_invitee(repo: ISigningRouteRepository) -> None:
    route = await repo.add(make_full_route(P1))
    invitation_id = route.participants[3].invitation_id
    assert invitation_id is not None

    assert await repo.list_for_invitation(P1, invitation_id) == [route]
    assert await repo.list_for_invitation(P2, invitation_id) == []
    assert await repo.list_for_invitation(P1, "inv_other") == []


async def test__list_for_user__accepted_invitation__found_by_new_user(repo: ISigningRouteRepository) -> None:
    route = await repo.add(make_full_route(P1))
    invited = route.participants[3]
    user = uuid4()

    saved = await repo.save(route.with_participant(replace(invited, user_id=user)))

    assert await repo.list_for_user(user) == [saved]
