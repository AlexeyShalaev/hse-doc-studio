"""Маршруты подписания в Postgres (docs/design/signing-route.md, раздел 5.8).

Маршрут пишется целиком: строка маршрута с версией, документы, участники, новые события. Запись идёт в точке
сохранения (SAVEPOINT): нарушение правил точки и документов откатывает только её, внешняя транзакция сценария
остаётся живой и получает доменную ошибку. Порядок документов и участников хранится явно (`position`), снимок и
отпечатки согласий списками, потому что jsonb не держит порядок ключей.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Collection, Mapping, Sequence
from dataclasses import replace
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from hse_doc_studio.core.signing_route.entities import (
    HOLDING_STATUSES,
    OPEN_STATUSES,
    WATCHING_STATUSES,
    Approval,
    DocSlot,
    DocSnapshot,
    EventKind,
    Notified,
    Participant,
    RequestOutcome,
    RouteEvent,
    RoutePhase,
    RouteStatus,
    SigningRoute,
    StopReason,
)
from hse_doc_studio.core.signing_route.repositories import (
    DocumentOnRouteError,
    OpenRouteExistsError,
    StaleRouteError,
)
from hse_doc_studio.infra.db.orm.signing_routes import (
    SigningRouteDocRow,
    SigningRouteEventRow,
    SigningRouteParticipantRow,
    SigningRouteRow,
)
from hse_doc_studio.infra.db.session import SessionProvider

_R = SigningRouteRow
_D = SigningRouteDocRow
_P = SigningRouteParticipantRow
_E = SigningRouteEventRow

_OPEN_INDEX = "ux_signing_routes_open"
_DOCS_INDEX = "ux_signing_route_docs_active"


def _values(statuses: Collection[RouteStatus]) -> list[str]:
    return sorted(status.value for status in statuses)


# --- пользователи: в домене UUID, в базе как users.id (32 hex-символа) ---


def _user(value: UUID | None) -> str | None:
    return value.hex if value is not None else None


def _user_id(value: str | None) -> UUID | None:
    return UUID(value) if value else None


# --- jsonb ---


def _snapshot_json(snapshot: Mapping[str, DocSnapshot]) -> list[dict[str, Any]]:
    return [
        {
            "doc_id": doc_id,
            "compiled_sha256": seen.compiled_sha256,
            "marks_digest": seen.marks_digest,
            "frozen_sha256": seen.frozen_sha256,
            "sent_at": seen.sent_at.isoformat() if seen.sent_at is not None else None,
        }
        for doc_id, seen in snapshot.items()
    ]


def _snapshot(raw: Any) -> dict[str, DocSnapshot]:
    # `sent_at` нет у снимков маршрутов 0.20.0: тогда время версии это `sent_at` маршрута (12.11).
    return {
        str(item["doc_id"]): DocSnapshot(
            compiled_sha256=item.get("compiled_sha256"),
            marks_digest=str(item.get("marks_digest", "")),
            frozen_sha256=item.get("frozen_sha256"),
            sent_at=datetime.fromisoformat(item["sent_at"]) if item.get("sent_at") else None,
        )
        for item in raw or ()
    }


def _approval_json(approval: Approval | None) -> dict[str, Any] | None:
    if approval is None:
        return None
    return {
        "round": approval.round,
        "tokens": [{"doc_id": doc_id, "token": token} for doc_id, token in approval.tokens.items()],
        "at": approval.at.isoformat(),
        "phase": approval.phase.value,
    }


def _approval(raw: Any) -> Approval | None:
    if not raw:
        return None
    return Approval(
        round=int(raw["round"]),
        tokens={str(item["doc_id"]): str(item["token"]) for item in raw.get("tokens", ())},
        at=datetime.fromisoformat(raw["at"]),
        phase=RoutePhase(raw.get("phase", RoutePhase.approval.value)),
    )


def _notified_json(notified: Notified | None) -> dict[str, Any] | None:
    if notified is None:
        return None
    return {"round": notified.round, "outcome": notified.outcome.value, "at": notified.at.isoformat()}


def _notified(raw: Any) -> Notified | None:
    if not raw:
        return None
    return Notified(
        round=int(raw["round"]), outcome=RequestOutcome(raw["outcome"]), at=datetime.fromisoformat(raw["at"])
    )


# --- строки и сущности ---


def _route_values(route: SigningRoute) -> dict[str, Any]:
    return {
        "project_id": route.project_id,
        "profile_id": route.profile_id,
        "status": route.status.value,
        "phase": route.phase.value if route.phase is not None else None,
        "round": route.round,
        "snapshot": _snapshot_json(route.snapshot),
        "deadline": route.deadline,
        "message": route.message,
        "stop_reason": route.stop_reason.value if route.stop_reason is not None else None,
        "stopped_by": route.stopped_by,
        "created_by": route.created_by.hex,
        "sent_by": _user(route.sent_by),
        "sent_at": route.sent_at,
        "completed_at": route.completed_at,
    }


def _participant_values(route_id: UUID, position: int, p: Participant) -> dict[str, Any]:
    return {
        "id": p.id,
        "route_id": route_id,
        "position": position,
        "step": p.step,
        "persona": p.persona,
        "user_id": _user(p.user_id),
        "invitation_id": p.invitation_id,
        "assignments": [{"doc_id": pair.doc_id, "slot_id": pair.slot_id} for pair in p.assignments],
        "approval": _approval_json(p.approval),
        "notified": _notified_json(p.notified),
        "reminded_at": p.reminded_at,
        "reminders": p.reminders,
    }


def _event_values(event: RouteEvent) -> dict[str, Any]:
    return {
        "route_id": event.route_id,
        "round": event.round,
        "at": event.at,
        "actor_id": _user(event.actor_id),
        "participant_id": event.participant_id,
        "kind": event.kind.value,
        "details": dict(event.details),
    }


def _participant(row: SigningRouteParticipantRow) -> Participant:
    return Participant(
        id=row.id,
        step=row.step,
        persona=row.persona,
        user_id=_user_id(row.user_id),
        invitation_id=row.invitation_id,
        assignments=tuple(DocSlot(str(item["doc_id"]), str(item["slot_id"])) for item in row.assignments or ()),
        approval=_approval(row.approval),
        notified=_notified(row.notified),
        reminded_at=row.reminded_at,
        reminders=row.reminders,
    )


def _route(row: SigningRouteRow, docs: Sequence[str], participants: Sequence[Participant]) -> SigningRoute:
    return SigningRoute(
        id=row.id,
        project_id=row.project_id,
        profile_id=row.profile_id,
        created_by=UUID(row.created_by),
        status=RouteStatus(row.status),
        phase=RoutePhase(row.phase) if row.phase else None,
        round=row.round,
        docs=tuple(docs),
        participants=tuple(participants),
        snapshot=_snapshot(row.snapshot),
        deadline=row.deadline,
        message=row.message,
        sent_by=_user_id(row.sent_by),
        sent_at=row.sent_at,
        completed_at=row.completed_at,
        stop_reason=StopReason(row.stop_reason) if row.stop_reason else None,
        stopped_by=row.stopped_by,
        version=row.version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _event(row: SigningRouteEventRow) -> RouteEvent:
    return RouteEvent(
        route_id=row.route_id,
        round=row.round,
        at=row.at,
        kind=EventKind(row.kind),
        actor_id=_user_id(row.actor_id),
        participant_id=row.participant_id,
        details=dict(row.details or {}),
        id=row.id,
    )


def _violated(exc: IntegrityError) -> str | None:
    """Имя нарушенного ограничения: asyncpg кладёт его в причину ошибки драйвера, иначе ищем в тексте."""
    for candidate in (exc.orig, getattr(exc.orig, "__cause__", None)):
        name = getattr(candidate, "constraint_name", None)
        if isinstance(name, str):
            return name
    message = str(exc.orig)
    return next((name for name in (_OPEN_INDEX, _DOCS_INDEX) if name in message), None)


class SqlSigningRouteRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    # --- запись ---

    async def add(self, route: SigningRoute, *, events: Sequence[RouteEvent] = ()) -> SigningRoute:
        if route.version != 0:
            raise ValueError(f"signing route {route.id} is already stored (version {route.version})")
        _check_events(route, events)
        now = func.clock_timestamp()
        insert_route = (
            insert(_R)
            .values(id=route.id, version=1, created_at=now, updated_at=now, **_route_values(route))
            .returning(_R.created_at)
        )
        async with self._sessions.use() as session:
            try:
                async with session.begin_nested():
                    created_at = (await session.execute(insert_route)).scalar_one()
                    await _write_parts(session, route, events)
            except IntegrityError as exc:
                conflict = await _conflict(session, route, exc)
                if conflict is None:
                    raise
                raise conflict from exc
        return replace(route, version=1, created_at=created_at, updated_at=created_at)

    async def save(self, route: SigningRoute, *, events: Sequence[RouteEvent] = ()) -> SigningRoute:
        _check_events(route, events)
        stmt = (
            update(_R)
            .where(_R.id == route.id, _R.project_id == route.project_id, _R.version == route.version)
            .values(version=_R.version + 1, updated_at=func.clock_timestamp(), **_route_values(route))
            .returning(_R.version, _R.created_at, _R.updated_at)
            .execution_options(synchronize_session=False)
        )
        async with self._sessions.use() as session:
            try:
                async with session.begin_nested():
                    written = (await session.execute(stmt)).first()
                    if written is None:
                        raise StaleRouteError(route.id)
                    await _write_parts(session, route, events)
            except IntegrityError as exc:
                conflict = await _conflict(session, route, exc)
                if conflict is None:
                    raise
                raise conflict from exc
        return replace(route, version=written.version, created_at=written.created_at, updated_at=written.updated_at)

    # --- чтение ---

    async def get(self, project_id: UUID, route_id: UUID, *, lock: bool = False) -> SigningRoute | None:
        return await self._one(select(_R).where(_R.project_id == project_id, _R.id == route_id), lock=lock)

    async def get_open(self, project_id: UUID, profile_id: str, *, lock: bool = False) -> SigningRoute | None:
        stmt = select(_R).where(
            _R.project_id == project_id, _R.profile_id == profile_id, _R.status.in_(_values(OPEN_STATUSES))
        )
        return await self._one(stmt, lock=lock)

    async def list_for_project(
        self, project_id: UUID, *, profile_id: str | None = None, statuses: Collection[RouteStatus] | None = None
    ) -> list[SigningRoute]:
        stmt = select(_R).where(_R.project_id == project_id)
        if profile_id is not None:
            stmt = stmt.where(_R.profile_id == profile_id)
        return await self._fetch(_with_statuses(stmt, statuses))

    async def holding(self, project_id: UUID, doc_id: str) -> SigningRoute | None:
        held = select(_D.route_id).where(_D.project_id == project_id, _D.doc_id == doc_id, _D.active)
        stmt = select(_R).where(_R.project_id == project_id, _R.id.in_(held), _R.status.in_(_values(HOLDING_STATUSES)))
        return await self._one(stmt, lock=False)

    async def list_watching(self, project_id: UUID | None = None) -> list[SigningRoute]:
        stmt = select(_R).where(_R.status.in_(_values(WATCHING_STATUSES)))
        if project_id is not None:
            stmt = stmt.where(_R.project_id == project_id)
        return await self._fetch(stmt)

    async def list_for_user(
        self, user_id: UUID, *, project_id: UUID | None = None, statuses: Collection[RouteStatus] | None = None
    ) -> list[SigningRoute]:
        mine = select(_P.route_id).where(_P.user_id == user_id.hex)
        stmt = select(_R).where(_R.id.in_(mine))
        if project_id is not None:
            stmt = stmt.where(_R.project_id == project_id)
        return await self._fetch(_with_statuses(stmt, statuses))

    async def list_for_invitation(self, project_id: UUID, invitation_id: str) -> list[SigningRoute]:
        awaiting = select(_P.route_id).where(_P.invitation_id == invitation_id)
        return await self._fetch(select(_R).where(_R.project_id == project_id, _R.id.in_(awaiting)))

    async def list_events(self, route_id: UUID, *, round: int | None = None) -> list[RouteEvent]:
        stmt = select(_E).where(_E.route_id == route_id)
        if round is not None:
            stmt = stmt.where(_E.round == round)
        async with self._sessions.use() as session:
            rows = (await session.execute(stmt.order_by(_E.id).execution_options(populate_existing=True))).scalars()
            return [_event(row) for row in rows]

    async def _one(self, stmt: Select[SigningRouteRow], *, lock: bool) -> SigningRoute | None:
        routes = await self._fetch(stmt.with_for_update() if lock else stmt, ordered=False)
        return routes[0] if routes else None

    async def _fetch(self, stmt: Select[SigningRouteRow], *, ordered: bool = True) -> list[SigningRoute]:
        if ordered:
            stmt = stmt.order_by(_R.created_at.desc(), _R.id.desc())
        async with self._sessions.use() as session:
            rows = list((await session.execute(stmt.execution_options(populate_existing=True))).scalars())
            return await _assemble(session, rows)


def _with_statuses(stmt: Select[SigningRouteRow], statuses: Collection[RouteStatus] | None) -> Select[SigningRouteRow]:
    return stmt if statuses is None else stmt.where(_R.status.in_(_values(statuses)))


def _check_events(route: SigningRoute, events: Sequence[RouteEvent]) -> None:
    strangers = [event for event in events if event.route_id != route.id]
    if strangers:
        raise ValueError(f"events of route {strangers[0].route_id} cannot be stored with route {route.id}")


async def _write_parts(session: AsyncSession, route: SigningRoute, events: Sequence[RouteEvent]) -> None:
    """Документы и участники маршрута заново, события добавить. Только внутри точки сохранения."""
    holding = route.status in HOLDING_STATUSES
    await session.execute(delete(_D).where(_D.route_id == route.id).execution_options(synchronize_session=False))
    if route.docs:
        docs = [
            {"route_id": route.id, "doc_id": doc_id, "project_id": route.project_id, "position": i, "active": holding}
            for i, doc_id in enumerate(route.docs)
        ]
        await session.execute(insert(_D), docs)
    await session.execute(delete(_P).where(_P.route_id == route.id).execution_options(synchronize_session=False))
    if route.participants:
        people = [_participant_values(route.id, i, p) for i, p in enumerate(route.participants)]
        await session.execute(insert(_P), people)
    if events:
        await session.execute(insert(_E), [_event_values(event) for event in events])


async def _conflict(session: AsyncSession, route: SigningRoute, exc: IntegrityError) -> Exception | None:
    """Доменная ошибка по нарушенному правилу; None, если нарушено что-то другое (ошибка вызывающего)."""
    violated = _violated(exc)
    if violated == _OPEN_INDEX:
        return OpenRouteExistsError(route.project_id, route.profile_id)
    if violated == _DOCS_INDEX:
        held = select(_D.doc_id).where(
            _D.project_id == route.project_id, _D.doc_id.in_(route.docs), _D.active, _D.route_id != route.id
        )
        doc_ids = set((await session.execute(held)).scalars())
        return DocumentOnRouteError([doc_id for doc_id in route.docs if doc_id in doc_ids] or route.docs)
    return None


async def _assemble(session: AsyncSession, rows: list[SigningRouteRow]) -> list[SigningRoute]:
    if not rows:
        return []
    ids = [row.id for row in rows]
    docs: dict[UUID, list[str]] = defaultdict(list)
    doc_rows = await session.execute(
        select(_D.route_id, _D.doc_id).where(_D.route_id.in_(ids)).order_by(_D.route_id, _D.position)
    )
    for route_id, doc_id in doc_rows.all():
        docs[route_id].append(doc_id)
    people: dict[UUID, list[Participant]] = defaultdict(list)
    people_rows = await session.execute(
        select(_P)
        .where(_P.route_id.in_(ids))
        .order_by(_P.route_id, _P.position)
        .execution_options(populate_existing=True)
    )
    for row in people_rows.scalars():
        people[row.route_id].append(_participant(row))
    return [_route(row, docs[row.id], people[row.id]) for row in rows]
