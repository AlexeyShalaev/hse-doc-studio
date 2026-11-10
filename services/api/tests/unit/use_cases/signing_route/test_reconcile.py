"""Сверка маршрута с проектом и сторожа без сервера (docs/design/signing-route.md, разделы 5.5, 6.1 и 6.10).

Проект в памяти (`World` тестов расчёта), хранилище-двойник и настоящие `RouteReconciler` и `SigningRouteGate`:
что останавливает маршрут, что не меняет ничего, чьи правки закрыты и что маршрут отдаёт плану подписей.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.access.context import set_current_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.enums import SignMode
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.signing_route.effects import Effect
from hse_doc_studio.core.signing_route.entities import (
    DocSlot,
    EventKind,
    Notice,
    ParticipantState,
    RouteConflictError,
    RoutePhase,
    RouteStatus,
    SigningRoute,
    StopReason,
)
from hse_doc_studio.core.signing_route.ports import NoRouteWatch, NoSigningRoutes, PlanRoutes
from hse_doc_studio.core.signing_route.transitions import approve, cancel
from hse_doc_studio.core.value_objects import SignaturePlacement
from hse_doc_studio.use_cases.signing_route.facts import LoadedFacts
from hse_doc_studio.use_cases.signing_route.gate import SigningRouteGate
from hse_doc_studio.use_cases.signing_route.reconcile import RouteReconciler
from hse_doc_studio.use_cases.signing_route.scenario import RouteServices

from tests.fakes.signing_routes import InMemorySigningRouteRepository, RecordingSigningNotifier
from tests.unit.core.signing_route.world import (
    DOC,
    DOC2,
    T0,
    Driver,
    World,
    by_persona,
    make_route,
    participant,
    signer,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence

PROFILE = "topic-approval"


class _Uow:
    @asynccontextmanager
    async def begin(self) -> AsyncIterator[None]:
        yield


@dataclass
class _Project:
    """Проект маршрута в памяти: мир с подписями и сборками; `broken` проект, который не прочитать."""

    world: World
    broken: bool = False
    extra_placements: dict[str, dict[str, SignaturePlacement]] = field(default_factory=dict)


@dataclass
class _Projects:
    """Точка сдачи, факты и файловые эффекты маршрута поверх миров в памяти."""

    by_id: dict[UUID, _Project] = field(default_factory=dict)
    applied: list[Effect] = field(default_factory=list)

    # RoutePointLoader
    async def load(self, project_id: UUID, profile_id: str) -> Any:
        found = self.by_id.get(project_id)
        if found is None or found.broken:
            raise NotFoundError(f"точка {profile_id} проекта {project_id} не найдена")
        return SimpleNamespace(project=SimpleNamespace(id=project_id), project_id=project_id)

    @property
    def points(self) -> Any:
        return self

    @property
    def facts(self) -> Any:
        return _Facts(self)

    @property
    def effects(self) -> Any:
        return _Effects(self)


@dataclass
class _Facts:
    projects: _Projects

    async def load(self, point: Any, route: SigningRoute, state: Any = None) -> LoadedFacts:
        project = self.projects.by_id[point.project_id]
        facts = project.world.facts()
        current = facts.state
        if project.extra_placements:
            placements = {doc: {**slots} for doc, slots in current.placements.items()}
            for doc_id, slots in project.extra_placements.items():
                placements.setdefault(doc_id, {}).update(slots)
            current = replace(current, placements=placements)
            facts = replace(facts, state=current)
        return LoadedFacts(current, facts)


@dataclass
class _Effects:
    projects: _Projects

    async def apply(
        self, point: Any, route: SigningRoute, effects: Sequence[Effect], *, at: datetime | None = None
    ) -> tuple[str, ...]:
        self.projects.applied += list(effects)
        self.projects.by_id[point.project_id].world.apply(effects)
        return ()


@dataclass
class _Stand:
    driver: Driver
    routes: InMemorySigningRouteRepository
    notifier: RecordingSigningNotifier
    projects: _Projects

    @property
    def services(self) -> RouteServices:
        return RouteServices(
            routes=self.routes,
            points=self.projects.points,
            facts=self.projects.facts,
            effects=self.projects.effects,
            people=cast("Any", None),
            notifier=self.notifier,
            uow=_Uow(),
            access=cast("Any", None),
            clock=lambda: T0,
        )

    @property
    def reconciler(self) -> RouteReconciler:
        return RouteReconciler(self.services)

    @property
    def gate(self) -> SigningRouteGate:
        return SigningRouteGate(self.services)

    @property
    def world(self) -> World:
        return self.driver.world

    @property
    def project_id(self) -> UUID:
        return self.driver.route.project_id

    async def stored(self) -> SigningRoute:
        route = await self.routes.get(self.project_id, self.driver.route.id)
        assert route is not None
        return route

    async def kinds(self) -> list[EventKind]:
        return [e.kind for e in await self.routes.list_events(self.driver.route.id)]

    async def store(self) -> None:
        """Записать маршрут прогона в хранилище (после действий участников в памяти)."""
        current = await self.routes.get(self.project_id, self.driver.route.id)
        if current is None:
            self.driver.route = await self.routes.add(self.driver.route)
        else:
            self.driver.route = await self.routes.save(replace(self.driver.route, version=current.version))


def _driver(modes: dict[str, SignMode], docs: tuple[str, ...] = (DOC,)) -> Driver:
    world = World(modes, docs=docs)
    route = make_route(
        [participant(step, persona, [persona], docs=docs) for step, persona in enumerate(modes, 1)], docs=docs
    )
    return Driver(world, route)


async def _sent(
    modes: dict[str, SignMode] | None = None,
    docs: tuple[str, ...] = (DOC,),
    projects: _Projects | None = None,
    routes: InMemorySigningRouteRepository | None = None,
    notifier: RecordingSigningNotifier | None = None,
) -> _Stand:
    """Маршрут отправлен автором: его согласие записано, очередь научрука."""
    driver = _driver(modes or {"author": SignMode.image, "supervisor": SignMode.image}, docs)
    author = by_persona(driver.route)["author"]
    assert author.user_id is not None
    driver.send(author.user_id)
    projects = projects or _Projects()
    projects.by_id[driver.route.project_id] = _Project(driver.world)
    stand = _Stand(driver, routes or InMemorySigningRouteRepository(), notifier or RecordingSigningNotifier(), projects)
    await stand.store()
    return stand


def _as(user_id: UUID | None) -> None:
    set_current_actor(Actor.user(user_id.hex) if user_id is not None else None)


@pytest.fixture(autouse=True)
def _no_actor() -> Any:
    yield
    set_current_actor(None)


# --- сверка -----------------------------------------------------------------------------------------------------------


async def test__reconcile__nothing_changed__route_not_rewritten() -> None:
    stand = await _sent()
    before = await stand.stored()

    changed = await stand.reconciler.project(stand.project_id)

    after = await stand.stored()
    assert changed == 0
    assert (after, after.version) == (before, before.version)
    assert stand.notifier.delivered == []
    assert stand.projects.applied == []


async def test__reconcile__pinned_version_replaced__paused_once_with_notice_and_images_withheld() -> None:
    stand = await _sent()
    stand.world.pinned[DOC] = "c" * 64

    first = await stand.reconciler.project(stand.project_id)
    second = await stand.reconciler.project(stand.project_id)

    route = await stand.stored()
    assert (first, second) == (1, 0)
    assert (route.status, route.stop_reason, route.phase) == (RouteStatus.paused, StopReason.sent_changed, None)
    events = await stand.routes.list_events(route.id)
    assert [(e.kind, e.actor_id, dict(e.details)) for e in events] == [
        (EventKind.paused, None, {"reason": "sent_changed"})
    ]
    # Согласие автора относилось к прежней версии на подписи: его картинка снова придержана.
    assert stand.world.withheld[DOC] == {"author", "supervisor"}
    assert [(n.notice, n.sender) for n in stand.notifier.notices] == [(Notice.paused, True)]
    assert stand.notifier.delivered[0].actor_id is None


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (
            lambda world: world.slots.update(author=replace(world.slots["author"], png_path="new.png")),
            StopReason.marks_changed,
        ),
        (lambda world: world.frozen.pop(DOC), StopReason.frozen_changed),
    ],
)
async def test__reconcile__signatures_changed_outside_the_route__paused(change: Any, reason: StopReason) -> None:
    modes = {"author": SignMode.image, "supervisor": SignMode.image, "academic_supervisor": SignMode.detached_text}
    stand = await _sent(modes)
    # Научрук согласовал: видимый слой окончателен, документ зафиксирован, академрук подписывает ЭП.
    stand.world.plates[cast("UUID", by_persona(stand.driver.route)["academic_supervisor"].user_id)] = _plate()
    stand.driver.act(by_persona(stand.driver.route)["supervisor"].id)
    await stand.store()
    assert DOC in stand.world.frozen

    change(stand.world)
    changed = await stand.reconciler.project(stand.project_id)

    route = await stand.stored()
    assert changed == 1
    assert (route.status, route.stop_reason) == (RouteStatus.paused, reason)


def _plate() -> Any:
    return signer("academic_supervisor")


async def test__reconcile__participant_left_the_project__paused_and_named() -> None:
    stand = await _sent()
    people = {p.user_id: frozenset({p.persona}) for p in stand.driver.route.participants if p.user_id is not None}
    supervisor = by_persona(stand.driver.route)["supervisor"]
    stand.world.personas = {**people, cast("UUID", supervisor.user_id): frozenset()}

    changed = await stand.reconciler.project(stand.project_id)

    route = await stand.stored()
    assert changed == 1
    assert (route.status, route.stop_reason, route.stopped_by) == (
        RouteStatus.paused,
        StopReason.participant_left,
        supervisor.id,
    )
    # Сборка та же: согласие автора в силе, картинки не трогаются; уведомление только автору.
    assert stand.projects.applied == []
    assert [(n.notice, n.participant_ids, n.sender) for n in stand.notifier.notices] == [(Notice.paused, (), True)]


async def test__reconcile__completed_route_lost_a_signature__goes_on_without_stopping() -> None:
    stand = await _sent({"author": SignMode.image, "supervisor": SignMode.detached_text})
    supervisor = by_persona(stand.driver.route)["supervisor"]
    stand.world.plates[cast("UUID", supervisor.user_id)] = _plate()
    stand.driver.run()
    await stand.store()
    assert (await stand.stored()).status is RouteStatus.completed

    stand.world.unsign(DocSlot(DOC, "supervisor"))
    changed = await stand.reconciler.project(stand.project_id)

    route = await stand.stored()
    assert changed == 1
    assert (route.status, route.phase, route.stop_reason) == (RouteStatus.active, RoutePhase.signing, None)
    assert await stand.kinds() == []


async def test__reconcile__stopped_and_cancelled_routes__not_watched() -> None:
    stand = await _sent()
    stand.driver.route = cancel(await stand.stored())
    await stand.store()
    stand.world.pinned[DOC] = "c" * 64

    assert await stand.reconciler.project(stand.project_id) == 0
    assert await stand.reconciler.sweep() == 0
    assert (await stand.stored()).status is RouteStatus.cancelled


async def test__sweep__completed_routes__left_to_the_hooks() -> None:
    stand = await _sent()
    stand.driver.run()
    await stand.store()
    assert (await stand.stored()).status is RouteStatus.completed
    stand.world.pinned[DOC] = "c" * 64

    # Периодический проход читает PDF каждого документа, а завершённых маршрутов со временем много.
    swept = await stand.reconciler.sweep()
    hooked = await stand.reconciler.project(stand.project_id)

    assert (swept, hooked) == (0, 1)
    assert ((await stand.stored()).status, (await stand.stored()).stop_reason) == (
        RouteStatus.paused,
        StopReason.sent_changed,
    )


async def test__sweep__every_project__broken_one_does_not_stop_the_rest() -> None:
    first = await _sent()
    second = await _sent(projects=first.projects, routes=first.routes, notifier=first.notifier)
    third = await _sent(projects=first.projects, routes=first.routes, notifier=first.notifier)
    first.projects.by_id[first.project_id].broken = True
    second.world.pinned[DOC] = "c" * 64

    changed = await first.reconciler.sweep()
    again = await first.reconciler.sweep()

    assert (changed, again) == (1, 0)
    assert (await first.stored()).status is RouteStatus.active
    assert ((await second.stored()).status, (await second.stored()).stop_reason) == (
        RouteStatus.paused,
        StopReason.sent_changed,
    )
    assert (await third.stored()).status is RouteStatus.active


# --- подпись другим входом (6.10) -------------------------------------------------------------------------------------


async def _to_sign(docs: tuple[str, ...] = (DOC, DOC2)) -> _Stand:
    """Научрук согласовал после фиксации без ключа Студии: маршрут ждёт его ЭП на двух документах."""
    stand = await _sent({"author": SignMode.image, "supervisor": SignMode.detached_text}, docs)
    supervisor = by_persona(stand.driver.route)["supervisor"]
    stand.world.plates[cast("UUID", supervisor.user_id)] = _plate()
    stand.driver.route = approve(stand.driver.route, stand.world.facts(), supervisor.id, at=T0)
    stand.driver.settle()
    await stand.store()
    return stand


async def test__signature_written__signed_event_once_per_slot__completion_after_the_last() -> None:
    stand = await _to_sign()
    supervisor = by_persona(stand.driver.route)["supervisor"]
    _as(supervisor.user_id)
    gate = stand.gate

    stand.world.sign(DocSlot(DOC, "supervisor"))
    await gate.signature_written(stand.project_id, DOC, "supervisor")
    # Повторная загрузка файла подписи того же слота.
    await gate.signature_written(stand.project_id, DOC, "supervisor")
    assert await stand.kinds() == [EventKind.signed]
    assert (await stand.stored()).status is RouteStatus.active

    stand.world.sign(DocSlot(DOC2, "supervisor"))
    await gate.signature_written(stand.project_id, DOC2, "supervisor")

    assert await stand.kinds() == [EventKind.signed, EventKind.signed, EventKind.completed]
    events = await stand.routes.list_events(stand.driver.route.id)
    assert {(e.actor_id, e.participant_id) for e in events if e.kind is EventKind.signed} == {
        (supervisor.user_id, supervisor.id)
    }
    assert (await stand.stored()).status is RouteStatus.completed


async def test__signatures_written__several_slots__one_recalculation_signed_before_completed() -> None:
    stand = await _to_sign()
    _as(by_persona(stand.driver.route)["supervisor"].user_id)
    pairs = [DocSlot(DOC, "supervisor"), DocSlot(DOC2, "supervisor")]
    for pair in pairs:
        stand.world.sign(pair)

    await stand.gate.signatures_written(stand.project_id, pairs)

    assert await stand.kinds() == [EventKind.signed, EventKind.signed, EventKind.completed]
    assert (await stand.stored()).version == stand.driver.route.version + 1


async def test__signature_written__slot_still_unsigned_or_not_crypto__no_event() -> None:
    stand = await _to_sign()
    _as(by_persona(stand.driver.route)["supervisor"].user_id)

    # Подпись с вердиктом `invalid` слот подписанным не делает; слот автора подписывается картинкой.
    await stand.gate.signature_written(stand.project_id, DOC, "supervisor")
    await stand.gate.signature_written(stand.project_id, DOC, "author")

    assert await stand.kinds() == []
    assert (await stand.stored()).version == stand.driver.route.version


# --- правки подписей (5.5) --------------------------------------------------------------------------------------------


async def _locked(call: Any) -> str | None:
    try:
        await call
    except RouteConflictError as exc:
        return exc.code
    return None


async def test__require_unlocked__active_route__document_and_its_slots_locked() -> None:
    stand = await _sent()
    gate, project_id = stand.gate, stand.project_id

    assert await _locked(gate.require_unlocked(project_id, doc_id=DOC)) == "route_locked"
    assert await _locked(gate.require_unlocked(project_id, slot_id="supervisor")) == "route_locked"
    # Другой документ и слот, которого нет ни в маршруте, ни на его документах, свободны.
    assert await _locked(gate.require_unlocked(project_id, doc_id=DOC2)) is None
    assert await _locked(gate.require_unlocked(project_id, slot_id="reviewer")) is None
    assert await _locked(gate.require_unlocked(uuid4(), doc_id=DOC, slot_id="supervisor")) is None


async def test__require_unlocked__slot_placed_on_a_route_document__locked_only_while_enabled() -> None:
    stand = await _sent()
    project = stand.projects.by_id[stand.project_id]
    placement = SignaturePlacement(enabled=True, page=1, x_mm=10, y_mm=10, width_mm=30)

    project.extra_placements = {DOC: {"reviewer": placement}}
    enabled = await _locked(stand.gate.require_unlocked(stand.project_id, slot_id="reviewer"))
    project.extra_placements = {DOC: {"reviewer": replace(placement, enabled=False)}}
    disabled = await _locked(stand.gate.require_unlocked(stand.project_id, slot_id="reviewer"))

    assert (enabled, disabled) == ("route_locked", None)


@pytest.mark.parametrize("how", ["cancelled", "sent_changed", "completed", "broken"])
async def test__require_unlocked__route_not_going__edits_allowed(how: str) -> None:
    stand = await _sent()
    if how == "cancelled":
        stand.driver.route = cancel(await stand.stored())
        await stand.store()
    elif how == "sent_changed":
        # В хранилище маршрут ещё идёт, по расчёту уже остановлен.
        stand.world.pinned[DOC] = "c" * 64
    elif how == "completed":
        stand.driver.run()
        await stand.store()
    else:
        stand.projects.by_id[stand.project_id].broken = True

    assert await _locked(stand.gate.require_unlocked(stand.project_id, doc_id=DOC, slot_id="supervisor")) is None


# --- «Подписать комплект» (6.10) --------------------------------------------------------------------------------------


async def test__hold__only_the_participant_in_turn_to_sign__gets_signable_slots() -> None:
    stand = await _to_sign()
    people = by_persona(stand.driver.route)
    gate, project_id, route_id = stand.gate, stand.project_id, stand.driver.route.id

    _as(people["supervisor"].user_id)
    mine = await gate.hold(project_id, DOC)
    _as(people["author"].user_id)
    author = await gate.hold(project_id, DOC)
    _as(None)
    nobody = await gate.hold(project_id, DOC)

    assert mine is not None
    assert (mine.route_id, mine.profile_id, mine.signable) == (route_id, PROFILE, frozenset({"supervisor"}))
    assert (author, nobody) == (replace(mine, signable=frozenset()), replace(mine, signable=frozenset()))
    # Подписанный слот больше не предлагается; документ без идущего маршрута свободен.
    stand.world.sign(DocSlot(DOC, "supervisor"))
    _as(people["supervisor"].user_id)
    signed = await gate.hold(project_id, DOC)
    assert signed is not None
    assert signed.signable == frozenset()
    assert await gate.hold(project_id, "report") is None


async def test__hold__before_the_participant_approved__nothing_signable() -> None:
    stand = await _sent({"author": SignMode.image, "supervisor": SignMode.detached_text})
    supervisor = by_persona(stand.driver.route)["supervisor"]
    stand.world.plates[cast("UUID", supervisor.user_id)] = _plate()
    _as(supervisor.user_id)

    held = await stand.gate.hold(stand.project_id, DOC)

    # Согласие это решение человека на странице подписи: комплект его не заменяет.
    assert held is not None
    assert held.signable == frozenset()


async def test__hold__route_stopped_by_calculation__document_free() -> None:
    stand = await _to_sign()
    stand.world.pinned[DOC] = "c" * 64

    assert await stand.gate.hold(stand.project_id, DOC) is None


# --- маршрут в плане подписей (6.1) -----------------------------------------------------------------------------------


async def test__plan_routes__route_of_the_checkpoint_or_document__and_slot_states() -> None:
    stand = await _sent(docs=(DOC, DOC2))
    gate, project_id = stand.gate, stand.project_id
    _as(uuid4())

    by_point = await gate.plan_routes(project_id, profile_id=PROFILE)
    by_doc = await gate.plan_routes(project_id, doc_id=DOC2)
    other_point = await gate.plan_routes(project_id, profile_id="final")
    other_doc = await gate.plan_routes(project_id, doc_id="report")
    whole = await gate.plan_routes(project_id)

    route = by_point.route
    assert route is not None
    assert (route.id, route.profile_id, route.status, route.phase, route.round) == (
        stand.driver.route.id,
        PROFILE,
        RouteStatus.active,
        RoutePhase.approval,
        1,
    )
    assert (route.current_step, route.steps_total, route.stop_reason) == (2, 2, None)
    assert by_doc.route == route
    assert (other_point.route, other_doc.route, whole.route) == (None, None, None)
    states = {
        DocSlot(DOC, "author"): ParticipantState.done,
        DocSlot(DOC2, "author"): ParticipantState.done,
        DocSlot(DOC, "supervisor"): ParticipantState.to_approve,
        DocSlot(DOC2, "supervisor"): ParticipantState.to_approve,
    }
    assert by_point.slot_states == states
    assert whole.slot_states == states


async def test__plan_routes__calculated_state__stop_shown_before_it_is_recorded() -> None:
    stand = await _sent()
    stand.world.pinned[DOC] = "c" * 64
    _as(uuid4())

    shown = (await stand.gate.plan_routes(stand.project_id, profile_id=PROFILE)).route

    assert shown is not None
    assert (shown.status, shown.stop_reason, shown.phase, shown.current_step) == (
        RouteStatus.paused,
        StopReason.sent_changed,
        None,
        None,
    )
    assert (await stand.stored()).status is RouteStatus.active


async def test__plan_routes__guest_or_link_reader__route_not_disclosed() -> None:
    stand = await _sent()
    member = Actor.user(uuid4().hex)
    readers = {
        "member": member,
        "member by link": member.with_link("lnk_1"),
        "guest": Actor.guest("gs_1", link_id="lnk_1"),
        "server task": None,
    }
    shown: dict[str, bool] = {}

    for name, actor in readers.items():
        set_current_actor(actor)
        shown[name] = (await stand.gate.plan_routes(stand.project_id, profile_id=PROFILE)).route is not None

    # Ход маршрута видят участники проекта (раздел 7): по ссылке и гостю план приходит без маршрута.
    assert shown == {"member": True, "member by link": False, "guest": False, "server task": False}


async def test__plan_routes__draft_cancelled_and_unreadable_routes__not_shown() -> None:
    stand = await _sent()
    _as(uuid4())
    stand.projects.by_id[stand.project_id].broken = True
    unreadable = await stand.gate.plan_routes(stand.project_id, profile_id=PROFILE)
    stand.projects.by_id[stand.project_id].broken = False
    stand.driver.route = cancel(await stand.stored())
    await stand.store()

    cancelled = await stand.gate.plan_routes(stand.project_id, profile_id=PROFILE)

    assert (unreadable, cancelled) == (PlanRoutes(), PlanRoutes())


# --- без маршрутов (локальная Студия, 6.9) ---------------------------------------------------------------------------


async def test__no_signing_routes__nothing_is_locked_held_or_shown() -> None:
    gate = NoSigningRoutes()
    project_id = uuid4()

    await gate.require_turn(project_id, DOC, "author")
    await gate.require_unlocked(project_id, doc_id=DOC, slot_id="author")
    await gate.signature_written(project_id, DOC, "author")
    await gate.signatures_written(project_id, [DocSlot(DOC, "author")])

    assert await gate.hold(project_id, DOC) is None
    assert await gate.plan_routes(project_id, profile_id=PROFILE) == PlanRoutes()
    assert NoRouteWatch().on_project_changed(project_id) is None
