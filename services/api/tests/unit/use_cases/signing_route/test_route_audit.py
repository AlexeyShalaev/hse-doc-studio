"""Журнал аудита маршрута: хранилище с аудитом и пометка `route_id` у подписей (signing-route.md, 6.7)."""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest
from hse_doc_studio.core.signing_route.audit import RouteAuditAction, record_of, signing_route_scope
from hse_doc_studio.core.signing_route.entities import EventKind, RouteEvent, RouteStatus, StopReason
from hse_doc_studio.core.signing_route.repositories import ISigningRouteRepository, StaleRouteError
from hse_doc_studio.infra.signatures.audit import ServerSignatureAudit
from hse_doc_studio.use_cases.signing_route.audit import AuditedSigningRoutes, SigningRouteAudit

from tests.fakes.auth import InMemoryAuditLog
from tests.fakes.ops import NoopUow
from tests.fakes.signing_routes import InMemorySigningRouteRepository
from tests.unit.core.signing_route.world import DOC, T0, make_route, participant


def _routes() -> tuple[ISigningRouteRepository, InMemoryAuditLog]:
    log = InMemoryAuditLog()
    return AuditedSigningRoutes(InMemorySigningRouteRepository(), SigningRouteAudit(log)), log


async def test__save__events_are_written_to_the_audit_log_with_the_project_as_target() -> None:
    routes, log = _routes()
    author = participant(1, "author", ["author"])
    route = await routes.add(make_route([author, participant(2, "supervisor", ["supervisor"])]))
    sent = replace(route, status=RouteStatus.active, round=1, sent_by=author.user_id)
    events = [
        RouteEvent(route.id, 1, T0, EventKind.sent, actor_id=author.user_id),
        RouteEvent(route.id, 1, T0, EventKind.approved, actor_id=author.user_id, participant_id=author.id),
        RouteEvent(route.id, 1, T0, EventKind.frozen, details={"docs": [DOC]}),
    ]

    saved = await routes.save(sent, events=events)

    entries = list(reversed(await log.list()))
    assert [e.action for e in entries] == ["signing_route.send", "signing_route.approve"]
    assert {e.target for e in entries} == {str(route.project_id)}
    assert {e.actor_id for e in entries} == {author.user_id.hex}  # type: ignore[union-attr]
    assert entries[0].details["project_id"] == str(route.project_id)
    assert entries[0].details["route_id"] == str(route.id)
    assert entries[1].details["slots"] == [{"doc_id": DOC, "slot_id": "author"}]
    assert [e.kind for e in await routes.list_events(saved.id)] == [
        EventKind.sent,
        EventKind.approved,
        EventKind.frozen,
    ]


async def test__save__server_event_has_no_actor() -> None:
    routes, log = _routes()
    route = await routes.add(make_route([participant(1, "author", ["author"])]))
    paused = replace(route, status=RouteStatus.paused, round=1, stop_reason=StopReason.rebuilt)

    await routes.save(paused, events=[RouteEvent(route.id, 1, T0, EventKind.paused, details={"reason": "rebuilt"})])

    [entry] = await log.list()
    assert (entry.action, entry.actor_id, entry.details["reason"]) == ("signing_route.pause", None, "rebuilt")


async def test__save__refused_by_the_storage__nothing_in_the_audit_log() -> None:
    routes, log = _routes()
    route = await routes.add(make_route([participant(1, "author", ["author"])]))
    stale = replace(route, version=route.version + 5)

    with pytest.raises(StaleRouteError):
        await routes.save(stale, events=[RouteEvent(route.id, 0, T0, EventKind.cancelled, actor_id=uuid4())])

    assert await log.list() == []


async def test__audited_routes__reads_pass_through() -> None:
    routes, _ = _routes()
    author = participant(1, "author", ["author"])
    route = await routes.add(replace(make_route([author]), status=RouteStatus.active, round=1))

    assert await routes.get(route.project_id, route.id) == route
    assert await routes.get_open(route.project_id, route.profile_id) == route
    assert await routes.list_for_project(route.project_id, profile_id=route.profile_id) == [route]
    assert await routes.holding(route.project_id, DOC) == route
    assert await routes.list_watching(route.project_id) == [route]
    assert await routes.list_for_user(author.user_id) == [route]  # type: ignore[arg-type]
    assert await routes.list_for_invitation(route.project_id, "inv_1") == []


async def test__write__scenario_record_without_an_event() -> None:
    log = InMemoryAuditLog()
    route = make_route([participant(1, "author", ["author"])])
    actor = uuid4()

    await SigningRouteAudit(log).write(route, record_of(RouteAuditAction.create, route, actor_id=actor))

    [entry] = await log.list()
    assert (entry.action, entry.actor_id, entry.target) == ("signing_route.create", actor.hex, str(route.project_id))


async def test__signature_audit__inside_a_route__record_carries_the_route_id() -> None:
    log = InMemoryAuditLog()
    audit = ServerSignatureAudit(log, NoopUow())
    project_id, route_id = uuid4(), uuid4()

    await audit.record("signature.unfreeze", project_id=project_id, details={"doc_id": DOC})
    with signing_route_scope(route_id):
        await audit.record("signature.freeze", project_id=project_id, details={"doc_id": DOC, "sha256": "ab"})
        await audit.record("signature.profile_image", project_id=None, details={"sha256": "cd"})

    outside, frozen, image = reversed(await log.list())
    assert "route_id" not in outside.details
    assert frozen.details == {"project_id": str(project_id), "doc_id": DOC, "sha256": "ab", "route_id": str(route_id)}
    assert image.details == {"sha256": "cd", "route_id": str(route_id)}
