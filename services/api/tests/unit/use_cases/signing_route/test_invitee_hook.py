"""Приглашённый подписант принял приглашение: аккаунт в маршруте и запрос, если его очередь (signing-route.md, 6.5)."""

from __future__ import annotations

from dataclasses import replace
from uuid import UUID, uuid4

from hse_doc_studio.core.signing_route.entities import Notice, RequestOutcome, RouteStatus
from hse_doc_studio.core.signing_route.repositories import StaleRouteError
from hse_doc_studio.use_cases.signing_route.invitations import SigningRouteInviteeHook

from tests.fakes.signing_routes import InMemorySigningRouteRepository, RecordingSigningNotifier
from tests.unit.core.signing_route.world import T0, Driver
from tests.unit.use_cases.signing_route.helpers import context, three_steps

INVITATION = "inv_0123456789abcdef"


def _invited(driver: Driver, index: int) -> UUID:
    """Участник `index` ещё не принял приглашение; возвращает его будущий аккаунт."""
    p = driver.route.participants[index]
    assert p.user_id is not None
    driver.route = driver.route.with_participant(replace(p, user_id=None, invitation_id=INVITATION))
    return p.user_id


_Hooked = tuple[SigningRouteInviteeHook, InMemorySigningRouteRepository, RecordingSigningNotifier]


async def _hook(driver: Driver) -> _Hooked:
    routes = InMemorySigningRouteRepository()
    await routes.add(driver.route)
    notifier = RecordingSigningNotifier()
    return SigningRouteInviteeHook(routes, context(driver), notifier, clock=lambda: T0), routes, notifier


async def test__invitee_whose_turn_it_is__gets_account_request_and_is_marked() -> None:
    driver = three_steps()
    author, supervisor, _ = driver.route.participants
    account = _invited(driver, 1)
    driver.send(author.user_id)  # type: ignore[arg-type]
    assert driver.route.participant(supervisor.id).notified is None
    hook, routes, notifier = await _hook(driver)

    await hook.on_invitation_accepted(driver.route.project_id, INVITATION, account.hex)

    stored = await routes.get(driver.route.project_id, driver.route.id)
    assert stored is not None
    bound = stored.participant(supervisor.id)
    assert (bound.user_id, bound.invitation_id) == (account, INVITATION)
    assert bound.notified is not None
    assert (bound.notified.round, bound.notified.outcome, bound.notified.at) == (1, RequestOutcome.approve, T0)
    [call] = notifier.delivered
    assert [(n.notice, n.participant_ids, n.outcome) for n in call.notices] == [
        (Notice.request, (supervisor.id,), RequestOutcome.approve)
    ]
    assert call.route.participant(supervisor.id).user_id == account


async def test__invitee_of_a_later_step__gets_account_without_request() -> None:
    driver = three_steps()
    author, _, academic = driver.route.participants
    account = _invited(driver, 2)
    driver.send(author.user_id)  # type: ignore[arg-type]
    hook, routes, notifier = await _hook(driver)

    await hook.on_invitation_accepted(driver.route.project_id, INVITATION, account.hex)

    stored = await routes.get(driver.route.project_id, driver.route.id)
    assert stored is not None
    assert stored.participant(academic.id).user_id == account
    assert stored.participant(academic.id).notified is None
    assert notifier.delivered == []


async def test__draft_route__binds_without_reading_facts() -> None:
    driver = three_steps()
    _, supervisor, _ = driver.route.participants
    account = _invited(driver, 1)
    routes = InMemorySigningRouteRepository()
    await routes.add(driver.route)
    ctx = context(driver)
    ctx.failing = True
    notifier = RecordingSigningNotifier()

    await SigningRouteInviteeHook(routes, ctx, notifier).on_invitation_accepted(
        driver.route.project_id, INVITATION, account.hex
    )

    stored = await routes.get(driver.route.project_id, driver.route.id)
    assert stored is not None
    assert stored.participant(supervisor.id).user_id == account
    assert notifier.delivered == []


async def test__unreadable_project__binds_and_skips_the_request() -> None:
    driver = three_steps()
    author, supervisor, _ = driver.route.participants
    account = _invited(driver, 1)
    driver.send(author.user_id)  # type: ignore[arg-type]
    routes = InMemorySigningRouteRepository()
    await routes.add(driver.route)
    ctx = context(driver)
    ctx.failing = True
    notifier = RecordingSigningNotifier()

    await SigningRouteInviteeHook(routes, ctx, notifier).on_invitation_accepted(
        driver.route.project_id, INVITATION, account.hex
    )

    stored = await routes.get(driver.route.project_id, driver.route.id)
    assert stored is not None
    assert stored.participant(supervisor.id).user_id == account
    assert notifier.delivered == []


async def test__other_invitation_archived_route_and_odd_user_id__nothing_changes() -> None:
    driver = three_steps()
    author, supervisor, _ = driver.route.participants
    account = _invited(driver, 1)
    driver.send(author.user_id)  # type: ignore[arg-type]
    hook, routes, notifier = await _hook(driver)

    await hook.on_invitation_accepted(driver.route.project_id, "inv_other", account.hex)
    await hook.on_invitation_accepted(uuid4(), INVITATION, account.hex)
    await hook.on_invitation_accepted(driver.route.project_id, INVITATION, "petr")

    stored = await routes.get(driver.route.project_id, driver.route.id)
    assert stored is not None
    assert stored.participant(supervisor.id).user_id is None
    archived = await routes.save(replace(stored, status=RouteStatus.archived, phase=None))
    await hook.on_invitation_accepted(driver.route.project_id, INVITATION, account.hex)
    after = await routes.get(driver.route.project_id, archived.id)
    assert after is not None
    assert after.participant(supervisor.id).user_id is None
    assert notifier.delivered == []


async def test__route_conflict__acceptance_is_not_broken() -> None:
    driver = three_steps()
    author, _, _ = driver.route.participants
    account = _invited(driver, 1)
    driver.send(author.user_id)  # type: ignore[arg-type]
    hook, routes, notifier = await _hook(driver)

    async def stale(*_a: object, **_kw: object) -> None:
        raise StaleRouteError(driver.route.id)

    routes.save = stale  # type: ignore[method-assign,assignment]

    await hook.on_invitation_accepted(driver.route.project_id, INVITATION, account.hex)

    assert notifier.delivered == []
