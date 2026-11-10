"""«На подпись»: задачи человека по расчёту маршрута на текущих фактах (docs/design/signing-route.md, 6.6)."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4

from hse_doc_studio.core.enums import SignMode
from hse_doc_studio.core.signing_route.entities import NextAction
from hse_doc_studio.use_cases.signing_route.tasks import ListSigningTasksUC

from tests.fakes.signing_routes import InMemorySigningRouteRepository, StaticRouteContext
from tests.unit.core.signing_route.world import T0, Driver, World, make_route, participant
from tests.unit.use_cases.signing_route.helpers import PROFILE_NAME, context, people, three_steps


async def _uc(driver: Driver, ctx: StaticRouteContext | None = None) -> ListSigningTasksUC:
    routes = InMemorySigningRouteRepository()
    await routes.add(driver.route)
    ctx = ctx or context(driver)
    return ListSigningTasksUC(routes, ctx, ctx, people(driver.route))


async def test__sent_route__task_only_for_whose_turn_it_is() -> None:
    driver = three_steps()
    author, supervisor, academic = driver.route.participants
    driver.send(author.user_id)  # type: ignore[arg-type]
    driver.route = replace(driver.route, deadline=T0 + timedelta(days=3))
    uc = await _uc(driver)

    [task] = await uc.execute(supervisor.user_id.hex)  # type: ignore[union-attr]

    route = driver.route
    assert (task.project_id, task.project_name, task.route_id) == (route.project_id, "Bertie", route.id)
    assert (task.profile_id, dict(task.profile_name), task.round) == ("topic-approval", PROFILE_NAME, 1)
    assert (task.sender, task.deadline, task.next_action) == ("Иван", T0 + timedelta(days=3), NextAction.approve)
    assert route.participants[1].notified is not None
    assert task.since == route.participants[1].notified.at
    assert task.participant_id == supervisor.id
    assert await uc.execute(author.user_id.hex) == []  # type: ignore[union-attr]
    assert await uc.execute(academic.user_id.hex) == []  # type: ignore[union-attr]
    assert await uc.count_for_user(supervisor.user_id.hex) == 1  # type: ignore[union-attr]
    assert await uc.count_for_user(academic.user_id.hex) == 0  # type: ignore[union-attr]


async def test__after_approval__task_moves_to_the_next_step() -> None:
    driver = three_steps()
    author, supervisor, academic = driver.route.participants
    driver.send(author.user_id)  # type: ignore[arg-type]
    driver.act(supervisor.id)
    uc = await _uc(driver)

    assert await uc.execute(supervisor.user_id.hex) == []  # type: ignore[union-attr]
    assert [t.next_action for t in await uc.execute(academic.user_id.hex)] == [NextAction.approve]  # type: ignore[union-attr]


async def test__pinned_version_replaced__reading_already_sees_the_stop_and_no_task() -> None:
    driver = three_steps()
    author, supervisor, _ = driver.route.participants
    driver.send(author.user_id)  # type: ignore[arg-type]
    uc = await _uc(driver)
    driver.world.pinned["topic_application"] = "c" * 64

    assert await uc.execute(supervisor.user_id.hex) == []  # type: ignore[union-attr]


async def test__crypto_signer_who_changes_the_visible_layer_last__approves_and_signs_in_one_go() -> None:
    world = World({"author": SignMode.image, "supervisor": SignMode.detached})
    route = make_route([participant(1, "author", ["author"]), participant(2, "supervisor", ["supervisor"])])
    driver = Driver(world, route)
    author, supervisor = route.participants
    driver.send(author.user_id)  # type: ignore[arg-type]
    uc = await _uc(driver)

    [task] = await uc.execute(supervisor.user_id.hex)  # type: ignore[union-attr]

    assert task.next_action is NextAction.approve_and_sign


async def test__unreadable_project_or_unknown_user__no_tasks_but_others_still_listed() -> None:
    driver = three_steps()
    author, supervisor, _ = driver.route.participants
    driver.send(author.user_id)  # type: ignore[arg-type]
    broken = context(driver)
    broken.failing = True
    no_facts = context(driver)
    no_facts.facts_of = lambda _route: None

    assert await (await _uc(driver, broken)).execute(supervisor.user_id.hex) == []  # type: ignore[union-attr]
    assert await (await _uc(driver, no_facts)).execute(supervisor.user_id.hex) == []  # type: ignore[union-attr]
    assert await (await _uc(driver)).execute("petr") == []
    assert await (await _uc(driver)).execute(uuid4().hex) == []


async def test__several_tasks__nearest_deadline_first_and_without_deadline_last() -> None:
    routes = InMemorySigningRouteRepository()
    contexts: dict[UUID, Driver] = {}
    signer = uuid4()
    drivers = []
    for days in (None, 7, 2):
        driver = three_steps()
        supervisor = replace(driver.route.participants[1], user_id=signer)
        driver.route = replace(
            driver.route,
            participants=(driver.route.participants[0], supervisor, driver.route.participants[2]),
            deadline=None if days is None else T0 + timedelta(days=days),
        )
        driver.send(driver.route.participants[0].user_id)  # type: ignore[arg-type]
        await routes.add(driver.route)
        contexts[driver.route.id] = driver
        drivers.append(driver)
    ctx = StaticRouteContext(
        facts_of=lambda route: contexts[route.id].world.facts(),
        projects={d.route.project_id: context(d).projects[d.route.project_id] for d in drivers},
    )
    uc = ListSigningTasksUC(routes, ctx, ctx, people(drivers[0].route))

    tasks = await uc.execute(signer.hex)

    assert [t.deadline for t in tasks] == [T0 + timedelta(days=2), T0 + timedelta(days=7), None]
