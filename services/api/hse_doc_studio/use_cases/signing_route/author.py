"""Сценарии автора маршрута подписания (docs/design/signing-route.md, разделы 3.1, 5.6 и 8).

Черновик точки, правка, список и ход, предпросмотр, отправка («Отправить и подписать»), отмена и снятие с контроля.
Права проверяет гард маршрута по таблице `ROUTE_ACTIONS` (`SUBMISSION_CREATE` или `OUTPUT_READ`); сценарий
дополнительно ограничивает подпись ключом своими слотами.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from hse_doc_studio.core.access.checker import ProjectForbiddenError
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.entities import SigningIdentity
from hse_doc_studio.core.enums import PlacementOrigin
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.signatures.plan import (
    SignMethod,
    SlotStatus,
    VisibleMark,
    mark_of,
    method_of,
    slot_persona,
    slot_state,
)
from hse_doc_studio.core.signatures.route_order import default_route
from hse_doc_studio.core.signing_route.audit import RouteAuditAction, signing_route_scope
from hse_doc_studio.core.signing_route.drafting import (
    PersonDraft,
    apply_people,
    assign_pairs,
    draft_participants,
    inherit_participants,
    resolve_unassigned,
)
from hse_doc_studio.core.signing_route.effects import Notify
from hse_doc_studio.core.signing_route.engine import Evaluation, RouteFacts, approval_token, evaluate, notice_for
from hse_doc_studio.core.signing_route.entities import (
    EDITABLE_STATUSES,
    HOLDING_STATUSES,
    NEW_VERSION_STATUSES,
    RETURN_COMMENT_MAX,
    SENDABLE_STATUSES,
    WATCHING_STATUSES,
    DocSlot,
    EventKind,
    NextAction,
    Notice,
    Participant,
    RouteConflictError,
    RouteEvent,
    RouteInputError,
    RoutePhase,
    RouteStatus,
    SigningRoute,
    StopReason,
    nothing_changed,
)
from hse_doc_studio.core.signing_route.preset import RoutePreset, preset_differs, preset_people
from hse_doc_studio.core.signing_route.readiness import (
    Blocker,
    BlockerCode,
    DocChangedError,
    OtherRoute,
    RouteBlockedError,
)
from hse_doc_studio.core.signing_route.repositories import OpenRouteExistsError
from hse_doc_studio.core.signing_route.signer import unsigned_crypto
from hse_doc_studio.core.signing_route.transitions import archive, cancel, send
from hse_doc_studio.core.signing_route.versions import (
    DocChange,
    VersionChanges,
    has_news,
    keeps_approval,
    losing_approval,
    version_changes,
)
from hse_doc_studio.core.value_objects import SignaturesState
from hse_doc_studio.use_cases.signatures.pack_places import PackPlaces
from hse_doc_studio.use_cases.signing_route.key_signer import KeyInfo, KeyRequest, RouteKeySigner
from hse_doc_studio.use_cases.signing_route.pinning import PinnedVersion, RoutePinning
from hse_doc_studio.use_cases.signing_route.point import RoutePoint
from hse_doc_studio.use_cases.signing_route.preset import (
    FRESH_ORIGINS,
    INHERITED_ORIGINS,
    PresetApplied,
    apply_optional,
    apply_places,
    mark_may_show,
    route_preset,
)
from hse_doc_studio.use_cases.signing_route.scenario import (
    RouteScenario,
    RouteServices,
    Settled,
    actor_uuid,
    closing_events,
    route_files,
)
from hse_doc_studio.use_cases.signing_route.views import (
    Membership,
    People,
    RouteDetails,
    SentVersion,
    build_details,
    method_of_participant,
    sent_version,
)

# «Отправить» не чаще раза в минуту на маршрут (раздел 7).
SEND_INTERVAL = timedelta(minutes=1)
MESSAGE_MAX = RETURN_COMMENT_MAX
# Новый маршрут точки снимает с контроля прежний завершённый и отменённый.
_SUPERSEDED = frozenset({RouteStatus.completed, RouteStatus.cancelled})


@dataclass(frozen=True)
class RouteUpdate:
    """PUT маршрута: шаги с людьми, включённые необязательные слоты, срок и сообщение целиком."""

    steps: tuple[tuple[PersonDraft, ...], ...]
    extra_slots: tuple[DocSlot, ...] = ()
    deadline: datetime | None = None
    message: str | None = None


@dataclass(frozen=True)
class SendRequest:
    """Отправка: отпечатки документов из предпросмотра и, для «Отправить и подписать», ключ Студии.

    `note` «Что изменилось» (12.6): заменяет сообщение маршрута и уходит подписантам с запросом; пустое не меняет.
    `new_version` можно ли отправить новую версию идущего или завершённого маршрута: MCP не может (12.10), это
    решение человека, потому что новая версия сбрасывает чужие согласия.
    """

    expected: Mapping[str, str]
    sign: KeyRequest | None = None
    note: str | None = None
    new_version: bool = True


class SentUnsignedError(Exception):
    """«Отправить и подписать»: маршрут отправлен, а подпись отправителя не поставлена (`sign_failed`, раздел 8.1).

    Отправка записана, документы зафиксированы: отправитель остаётся в `to_sign` и подписывает на своей странице.
    `cause` отказ подписи; его текст уходит в ответ.
    """

    def __init__(self, cause: Exception) -> None:
        super().__init__(str(cause))
        self.cause = cause


@dataclass(frozen=True)
class RouteSummary:
    route: SigningRoute
    profile_name: dict[str, str]
    status: RouteStatus
    phase: RoutePhase | None
    stop_reason: StopReason | None
    current_step: int | None
    # Чья очередь: имя (None, если человека нет) и персона.
    waiting_for: tuple[tuple[str | None, str], ...] = ()
    # Документы, рабочая сборка которых ушла от версии на подписи (12.9); считаются у маршрутов, держащих документы.
    changed_docs: tuple[str, ...] = ()

    @property
    def steps_total(self) -> int:
        return len(self.route.steps)


@dataclass(frozen=True)
class PreviewPerson:
    participant: Participant
    step: int
    name: str | None
    membership: Membership
    method: SignMethod | None
    methods: tuple[str, ...]
    chooses_method: bool
    image_ready: bool
    plate_ready: bool
    actions: int
    # Согласие переносится по всем его документам: после отправки он остаётся согласовавшим (12.9).
    keeps_approval: bool = False


@dataclass(frozen=True)
class PreviewDoc:
    """Документ предпросмотра: кандидат против версии на подписи (12.9).

    `built` и `token` по кандидату: `build:<sha>` текущей сборки, у несобранного документа с версией на подписи
    её отпечаток. `sent` нынешняя версия на подписи этого маршрута.
    """

    doc_id: str
    name: dict[str, str]
    built: bool
    token: str | None
    change: DocChange
    sent: SentVersion | None


@dataclass(frozen=True)
class RoutePreview:
    route: SigningRoute
    can_send: bool
    can_send_and_sign: bool
    visual_step: int
    docs: tuple[PreviewDoc, ...]
    participants: tuple[PreviewPerson, ...]
    blockers: tuple[Blocker, ...]
    sender_key: KeyInfo | None


@dataclass(frozen=True)
class _Readiness:
    """Что будет при отправке: помехи и расчёт отправленного маршрута (или текущего, если отправить нельзя)."""

    blockers: tuple[Blocker, ...]
    evaluation: Evaluation
    route: SigningRoute
    sender: Participant | None = None
    sendable: bool = False

    @property
    def can_send(self) -> bool:
        return self.sendable and not self.blockers

    @property
    def can_send_and_sign(self) -> bool:
        if not self.can_send or self.sender is None:
            return False
        return self.evaluation.participant(self.sender.id).next_action is NextAction.sign


def _invalid(status: RouteStatus, action: str) -> RouteConflictError:
    return RouteConflictError(
        "invalid_transition",
        localized_error(
            f"Маршрут в состоянии «{status}» нельзя {action}",
            f"A signing route in “{status}” cannot be changed this way",
        ),
    )


def _aware(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


def _message(value: str | None) -> str | None:
    text = (value or "").strip()
    if len(text) > MESSAGE_MAX:
        raise RouteInputError(
            "message_too_long",
            localized_error("Сообщение длиннее 2000 символов", "The message is longer than 2000 characters"),
        )
    return text or None


# --- черновик, правка, чтение ------------------------------------------------------------------------------------


class SigningRouteDrafts(RouteScenario):
    """Черновик точки, правка, ход маршрута и список маршрутов проекта."""

    async def create(self, actor: Actor, project_id: UUID, profile_id: str) -> tuple[RouteDetails, bool]:
        """Незавершённый маршрут точки (False) или новый из пака (True); новый снимает с контроля прежний."""
        actor_id = actor_uuid(actor)
        point = await self._s.points.load(project_id, profile_id)
        async with self._s.uow.begin():
            route = await self._s.routes.get_open(project_id, profile_id, lock=True)
            created = route is None
            if route is None:
                route = await self._add(point, actor_id)
        return await self._details(actor, point, route), created

    async def _add(self, point: RoutePoint, actor_id: UUID) -> SigningRoute:
        """Новый черновик точки (15.5): состав из прежнего маршрута точки, а без него из пресета пака; файлы
        (отметки `optional`, места и метки даты) пишутся до записи маршрута (5.8: сначала файлы), чтобы редактор сразу
        показал рамки.

        Если запись маршрута не удастся, записанные места остаются обычными местами из шаблона: они ничего не
        подписывают, а следующая попытка их переиспользует. Прежний завершённый маршрут точки снимается с контроля
        раньше: его документы пресет трогает только как документы без маршрута, а места над ЭП не трогает никогда.
        """
        previous = await self._s.routes.list_for_project(point.project_id, profile_id=point.profile.id)
        inherited = previous[0] if previous and previous[0].participants else None
        preset = route_preset(point)
        route = await self._new_route(point, actor_id, inherited, preset)
        for old in previous:
            if old.status in _SUPERSEDED:
                archived = await self._s.routes.save(archive(old))
                await self._audit(
                    RouteAuditAction.archive, archived, actor_id=actor_id, details={"superseded_by": str(route.id)}
                )
        applied: PresetApplied | None = None
        if preset is not None:
            pairs = [*point.required, *(pair for pair in route.pairs if pair not in point.allowed)]
            applied = await self._write_preset(
                point,
                route,
                preset,
                pairs=pairs if inherited is None else (),
                place_pairs=pairs,
                origins=FRESH_ORIGINS if inherited is None else INHERITED_ORIGINS,
            )
        try:
            added = await self._s.routes.add(route)
        except OpenRouteExistsError:
            # Черновик точки только что создал другой запрос: отдаём его.
            found = await self._s.routes.get_open(point.project_id, point.profile.id)
            if found is None:
                raise
            return found
        details = _composition(added)
        if preset is not None and applied is not None:
            details["preset"] = _preset_audit(preset, applied, inherited=inherited is not None)
        await self._audit(RouteAuditAction.create, added, actor_id=actor_id, details=details)
        return added

    async def _new_route(
        self, point: RoutePoint, actor_id: UUID, previous: SigningRoute | None, preset: RoutePreset | None
    ) -> SigningRoute:
        """Состав черновика: прежний маршрут точки (6.5), иначе пресет точки, а без него порядок 5.2."""
        extras: list[DocSlot] = []
        # По какой версии шаблона собран состав (15.7): у черновика после прежнего маршрута та же, что у прежнего.
        preset_version: str | None = None
        if previous is not None:
            participants = inherit_participants(previous)
            extras = [pair for pair in previous.pairs if point.is_optional(pair)]
            preset_version = previous.preset_version
        else:
            if preset is not None:
                extras = list(preset.extra_pairs)
                steps = preset.steps
                preset_version = preset.version
            else:
                steps = default_route(
                    point.version, point.profile, point.project, slot_ids=[pair.slot_id for pair in point.required]
                )
            candidates = await self._s.people.candidates(point.project_id)
            invitees = await self._s.people.invitees(point.project_id)
            participants = draft_participants(steps, candidates, invitees, prefer=actor_id)
        pairs = [*point.required, *extras]
        participants, _ = assign_pairs(participants, pairs)
        return SigningRoute(
            id=uuid4(),
            project_id=point.project_id,
            profile_id=point.profile.id,
            created_by=actor_id,
            docs=point.docs_of(pairs),
            participants=participants,
            preset_version=preset_version,
        )

    async def _write_preset(  # noqa: PLR0913 — что применить и к чему
        self,
        point: RoutePoint,
        route: SigningRoute,
        preset: RoutePreset,
        *,
        pairs: Sequence[DocSlot],
        place_pairs: Sequence[DocSlot],
        origins: Collection[PlacementOrigin | None],
        unset: bool = False,
        held: Sequence[str] = (),
        signed: Callable[[DocSlot], bool] | None = None,
    ) -> PresetApplied:
        """Отметки `optional` пар `pairs` и места пар `place_pairs` по пресету под `route_files` (15.5, 15.6).

        Документы, которые держит другой маршрут, не трогаются. Пишет состояние подписей, только если оно изменилось.
        """
        async with route_files(point.project):
            repo = self._s.effects.signatures
            state = repo.get_state(point.project.folder)
            elsewhere = await self._held_elsewhere(point, route)
            updated, marked, unmarked = apply_optional(
                point,
                state,
                pairs,
                preset,
                unset=unset,
                held=held,
                signed=signed or (lambda _pair: False),
                skip_docs=elsewhere,
            )
            places = PackPlaces.load(self._s.points.templates, point.project, point.version)
            updated, placed = apply_places(point, updated, place_pairs, places, origins=origins, skip_docs=elsewhere)
            if updated != state:
                repo.save_state(point.project.folder, updated)
        return PresetApplied(updated, placed, marked, unmarked)

    async def _held_elsewhere(self, point: RoutePoint, route: SigningRoute) -> frozenset[str]:
        """Документы маршрута, которые держит другой маршрут (`HOLDING_STATUSES`): пресет их не трогает."""
        held: set[str] = set()
        for doc_id in dict.fromkeys((*route.docs, *point.docs_of(point.required))):
            holder = await self._s.routes.holding(point.project_id, doc_id)
            if holder is not None and holder.id != route.id:
                held.add(doc_id)
        return frozenset(held)

    async def restore_preset(self, actor: Actor, project_id: UUID, route_id: UUID) -> RouteDetails:
        """«Вернуть как в шаблоне» (15.6): шаги, слоты сверх точки и отметки `optional` пар маршрута по пресету.

        Люди остаются по персоне (участник с той же персоной на её новом шаге со своим согласием), лишние
        убираются, недостающие подбираются, как в заготовке. Места ставятся только новым парам, как при создании;
        ручные места не трогаются. Повтор без изменений ничего не пишет и в аудит не попадает.
        """
        actor_id = actor_uuid(actor)
        async with self._s.uow.begin():
            route = await self._get(project_id, route_id, lock=True)
            if route.status not in EDITABLE_STATUSES:
                raise _invalid(route.status, "вернуть как в шаблоне")
            point = await self._s.points.load(project_id, route.profile_id)
            preset = route_preset(point)
            if preset is None:
                raise no_preset()
            loaded = await self._s.facts.load(point, route)
            before = preset_differs(preset, route, point.required, marked_pairs(loaded.facts.optional))
            participants = apply_people(route.participants, preset_people(route.participants, preset.steps))
            participants = await self._people_for(point, participants, (), actor_id)
            pairs = [*point.required, *preset.extra_pairs]
            participants, _ = assign_pairs(participants, pairs)
            restored = replace(
                route, participants=participants, docs=point.docs_of(pairs), preset_version=preset.version
            )
            held = route.docs if route.status in HOLDING_STATUSES else ()
            had = set(route.pairs)

            def signed(pair: DocSlot) -> bool:
                doc = loaded.facts.doc(pair.doc_id)
                state = slot_state(loaded.state, pair.doc_id, pair.slot_id, doc, profile_id=route.profile_id)
                return state.status is SlotStatus.signed

            applied = await self._write_preset(
                point,
                restored,
                preset,
                pairs=pairs,
                place_pairs=[pair for pair in pairs if pair not in had],
                origins=FRESH_ORIGINS,
                unset=True,
                held=held,
                signed=signed,
            )
            if restored == route and not (applied.placed or applied.marked or applied.unmarked):
                saved = route
            else:
                saved = await self._s.routes.save(restored) if restored != route else route
                await self._audit(
                    RouteAuditAction.restore_preset,
                    saved,
                    actor_id=actor_id,
                    details={
                        **_composition(saved),
                        "version": preset.version,
                        "differs": [diff.value for diff in before],
                        "extra_slots": [{"doc_id": p.doc_id, "slot_id": p.slot_id} for p in preset.extra_pairs],
                        "optional": [{"doc_id": p.doc_id, "slot_id": p.slot_id} for p in preset.optional],
                        "placements": len(applied.placed),
                    },
                )
        return await self._details(actor, point, saved)

    async def get(self, actor: Actor, project_id: UUID, route_id: UUID) -> RouteDetails:
        route = await self._get(project_id, route_id)
        point = await self._s.points.load(project_id, route.profile_id)
        return await self._details(actor, point, route)

    async def list_routes(self, project_id: UUID, profile_id: str | None = None) -> list[RouteSummary]:
        """Маршруты проекта или точки, новые первыми; ход считается только у идущих и завершённых."""
        points: dict[str, RoutePoint | None] = {}
        result: list[RouteSummary] = []
        for route in await self._s.routes.list_for_project(project_id, profile_id=profile_id):
            if route.profile_id not in points:
                points[route.profile_id] = await self._point_or_none(project_id, route.profile_id)
            point = points[route.profile_id]
            if point is not None:
                result.append(await self._summary(point, route))
        return result

    async def _point_or_none(self, project_id: UUID, profile_id: str) -> RoutePoint | None:
        try:
            return await self._s.points.load(project_id, profile_id)
        except NotFoundError:
            return None

    async def _summary(self, point: RoutePoint, route: SigningRoute) -> RouteSummary:
        base = RouteSummary(
            route=route,
            profile_name=dict(point.profile.name),
            status=route.status,
            phase=route.phase,
            stop_reason=route.stop_reason,
            current_step=None,
        )
        if route.status not in HOLDING_STATUSES:
            return base
        details = await self._details_light(point, route)
        base = replace(base, changed_docs=details.changed_docs)
        if route.status not in WATCHING_STATUSES:
            return base
        return replace(
            base,
            status=details.status,
            phase=details.phase,
            stop_reason=details.stop_reason,
            current_step=details.current_step,
            waiting_for=tuple((person.name, person.participant.persona) for person in details.waiting_for),
        )

    async def _details_light(self, point: RoutePoint, route: SigningRoute) -> RouteDetails:
        loaded = await self._s.facts.load(point, route)
        people = await self._people(point.project_id, route, loaded)
        return build_details(point, route, loaded.facts, evaluate(route, loaded.facts), people)

    async def update(self, actor: Actor, project_id: UUID, route_id: UUID, update: RouteUpdate) -> RouteDetails:
        """Шаги, люди, необязательные слоты, срок и сообщение; только у неотправленного или остановленного."""
        async with self._s.uow.begin():
            route = await self._get(project_id, route_id, lock=True)
            if route.status not in EDITABLE_STATUSES:
                raise _invalid(route.status, "изменить")
            point = await self._s.points.load(project_id, route.profile_id)
            extras = _extras(point, update.extra_slots)
            participants = apply_people(route.participants, update.steps)
            participants = await self._people_for(point, participants, extras, actor_uuid(actor))
            pairs = [*point.required, *extras]
            participants, _ = assign_pairs(participants, pairs)
            changed = replace(
                route,
                participants=participants,
                docs=point.docs_of(pairs),
                deadline=_aware(update.deadline),
                message=_message(update.message),
            )
            saved = await self._s.routes.save(changed)
            await self._audit(
                RouteAuditAction.update,
                saved,
                actor_id=actor_uuid(actor),
                details={
                    **_composition(saved),
                    "extra_slots": [{"doc_id": pair.doc_id, "slot_id": pair.slot_id} for pair in extras],
                    "deadline": saved.deadline.isoformat() if saved.deadline is not None else None,
                    "has_message": saved.message is not None,
                },
            )
        return await self._details(actor, point, saved)

    async def _people_for(
        self,
        point: RoutePoint,
        participants: tuple[Participant, ...],
        extras: Sequence[DocSlot],
        actor_id: UUID,
    ) -> tuple[Participant, ...]:
        """Люди по персонам: необязательному слоту без участника с его персоной заводится участник отдельным
        последним шагом; участнику без человека (новому или очищенному) человек подбирается, как в заготовке."""
        personas = {p.persona for p in participants}
        lacking = [
            persona
            for persona in dict.fromkeys(slot_persona(pair.slot_id) for pair in extras)
            if persona not in personas
        ]
        last = max((p.step for p in participants), default=0)
        added = tuple(
            Participant(id=uuid4(), step=number, persona=persona)
            for number, persona in enumerate(lacking, start=last + 1)
        )
        everyone = (*participants, *added)
        if all(p.user_id is not None or p.invitation_id is not None for p in everyone):
            return everyone
        candidates = await self._s.people.candidates(point.project_id)
        invitees = await self._s.people.invitees(point.project_id)
        return resolve_unassigned(everyone, candidates, invitees, prefer=actor_id)


def _composition(route: SigningRoute) -> dict[str, object]:
    """Состав маршрута для журнала аудита: документы, число шагов и участников."""
    return {"docs": list(route.docs), "steps": len(route.steps), "participants": len(route.participants)}


def _preset_audit(preset: RoutePreset, applied: PresetApplied, *, inherited: bool) -> dict[str, object]:
    """`preset` записи `signing_route.create` (15.12): версия, что шаблон добавил и отметил, сколько мест поставил.

    У черновика после прежнего маршрута точки состав прежний: слоты сверх точки и отметки пресета не применялись.
    """
    return {
        "version": preset.version,
        "extra_slots": [] if inherited else [{"doc_id": p.doc_id, "slot_id": p.slot_id} for p in preset.extra_pairs],
        "optional": [{"doc_id": p.doc_id, "slot_id": p.slot_id} for p in applied.marked],
        "placements": len(applied.placed),
    }


def marked_pairs(optional: Mapping[str, Iterable[str]]) -> frozenset[DocSlot]:
    """Пары с отметкой «Подпись необязательна» на точке маршрута (`RouteFacts.optional`)."""
    return frozenset(DocSlot(doc_id, slot_id) for doc_id, slots in optional.items() for slot_id in slots)


def no_preset() -> RouteConflictError:
    return RouteConflictError(
        "no_preset",
        localized_error(
            "Шаблон проекта не задаёт маршрут этой точки: возвращать нечего",
            "The project template has no route for this checkpoint: there is nothing to reset to",
        ),
    )


def _extras(point: RoutePoint, pairs: Iterable[DocSlot]) -> list[DocSlot]:
    """Необязательные пары из запроса: слот применим к документу точки; пары точки пропускаются."""
    extras: list[DocSlot] = []
    for pair in dict.fromkeys(pairs):
        if pair in point.allowed:
            continue
        if pair.doc_id not in point.docs_of(point.required):
            raise RouteInputError(
                "unknown_doc",
                localized_error(
                    f"Документ {pair.doc_id!r} не входит в контрольную точку",
                    f"Document {pair.doc_id!r} is not part of the checkpoint",
                ),
            )
        if not point.is_optional(pair):
            raise RouteInputError(
                "unknown_slot",
                localized_error(
                    f"Слот {pair.slot_id!r} не ставится на документ {pair.doc_id!r}",
                    f"Slot {pair.slot_id!r} does not apply to document {pair.doc_id!r}",
                ),
            )
        extras.append(pair)
    return extras


# --- предпросмотр и отправка ----------------------------------------------------------------------------------------


class SigningRouteSending(RouteScenario):
    """Предпросмотр и отправка (заново); «Отправить и подписать» подписывает слоты отправителя его ключом."""

    def __init__(self, services: RouteServices, signer: RouteKeySigner) -> None:
        super().__init__(services)
        self._signer = signer

    async def preview(self, actor: Actor, project_id: UUID, route_id: UUID) -> RoutePreview:
        """Что будет при отправке сохранённого маршрута; ничего не меняет.

        Считается на кандидате (12.6): источник каждого документа заменён текущей сборкой. У идущего и
        завершённого маршрута без изменений отправлять нечего: `can_send` ложно, помеха `nothing_changed`.
        """
        actor_id = actor_uuid(actor)
        route = await self._get(project_id, route_id)
        point = await self._s.points.load(project_id, route.profile_id)
        loaded = await self._s.facts.load(point, route)
        candidate = loaded.facts.candidate()
        people = await self._people(project_id, route, loaded)
        readiness = await self._readiness(point, route, candidate, people, actor_id, self._s.clock())
        changes = version_changes(route, candidate)
        return RoutePreview(
            route=route,
            can_send=readiness.can_send,
            can_send_and_sign=readiness.can_send_and_sign,
            visual_step=readiness.evaluation.last_visible_step,
            docs=_preview_docs(point, route, loaded.state, candidate, changes),
            participants=_preview_people(point, readiness, candidate, people, route),
            blockers=readiness.blockers,
            sender_key=await self._signer.default_key_info(),
        )

    async def send(self, actor: Actor, project_id: UUID, route_id: UUID, request: SendRequest) -> RouteDetails:
        """Отправить, отправить заново или отправить новую версию (5.6, 12.6). Ошибка подписи при «Отправить и
        подписать» не отменяет отправку: маршрут уходит, а ошибка возвращается после записи как
        `SentUnsignedError` (подписать можно на своей странице). Любой другой отказ значит, что ничего не
        отправлено."""
        actor_id = actor_uuid(actor)
        at = self._s.clock()
        deferred: Exception | None = None
        note = _message(request.note)
        async with self._s.uow.begin():
            route = await self._get(project_id, route_id, lock=True)
            if route.status not in SENDABLE_STATUSES or (
                route.status in NEW_VERSION_STATUSES and not request.new_version
            ):
                raise _invalid(route.status, "отправить")
            _check_interval(route, at)
            if note is not None:
                route = replace(route, message=note)
            point = await self._s.points.load(project_id, route.profile_id)
            identity = await self._signer.check(request.sign) if request.sign is not None else None
            async with route_files(point.project):
                sending = await self._send_files(point, route, actor_id, request, at)
                settled, events = sending.settled, sending.events
                if identity is not None and request.sign is not None:
                    try:
                        settled, signed = await self._sign_own(point, settled, actor_id, identity, request.sign, at)
                        events += signed
                    except (ValueError, PermissionError, NotFoundError, ProjectForbiddenError) as exc:
                        deferred = exc
            extra = _new_version_notice(route, sending.losing, settled, actor_id)
            saved = await self._commit(
                settled, [*events, *closing_events(settled, at)], actor_id=actor_id, at=at, extra=extra
            )
        if deferred is not None:
            raise SentUnsignedError(deferred) from deferred
        return await self._details(actor, point, saved)

    async def _send_files(
        self, point: RoutePoint, route: SigningRoute, actor_id: UUID, request: SendRequest, at: datetime
    ) -> _Sending:
        """Порядок 12.6: кандидат, изменения, сверка `expected` по кандидату, переход, снятие версий на подписи,
        затем расчёт по фактам с диска (они совпадают с кандидатом) и эффекты."""
        loaded = await self._s.facts.load(point, route)
        candidate = loaded.facts.candidate()
        changes = version_changes(route, candidate)
        if route.status in NEW_VERSION_STATUSES and not has_news(route, candidate):
            raise nothing_changed()
        people = await self._people(point.project_id, route, loaded)
        readiness = await self._readiness(point, route, candidate, people, actor_id, at)
        if readiness.blockers:
            raise RouteBlockedError(readiness.blockers)
        _check_expected(route, candidate, request.expected)
        sent = send(route, candidate, by=actor_id, at=at)
        pinning = RoutePinning(self._s.effects.signatures, self._s.points.template_service)
        to_pin = _to_pin(route, loaded.state, changes)
        expected = {doc_id: candidate.doc(doc_id).compiled_sha256 or "" for doc_id in to_pin}
        versions = await pinning.pin(point, sent, expected, at=at)
        settled = await self._settle(point, sent, at)
        details = _sent_details(changes, versions)
        events = [RouteEvent(sent.id, sent.round, at, EventKind.sent, actor_id=actor_id, details=details)]
        if readiness.sender is not None:
            events.append(
                RouteEvent(sent.id, sent.round, at, EventKind.approved, actor_id, participant_id=readiness.sender.id)
            )
        if settled.frozen:
            events.append(RouteEvent(sent.id, sent.round, at, EventKind.frozen, details={"docs": list(settled.frozen)}))
        return _Sending(settled, events, losing_approval(route, candidate))

    async def _sign_own(
        self,
        point: RoutePoint,
        settled: Settled,
        actor_id: UUID,
        identity: SigningIdentity,
        key: KeyRequest,
        at: datetime,
    ) -> tuple[Settled, list[RouteEvent]]:
        """Слоты ЭП отправителя, которые ждут его подписи после фиксации («Отправить и подписать»)."""
        route = settled.route
        me = next(
            (
                p
                for p in route.participants
                if p.user_id == actor_id and settled.evaluation.participant(p.id).next_action is NextAction.sign
            ),
            None,
        )
        if me is None:
            return settled, []
        pairs = unsigned_crypto(me, settled.loaded.facts)
        with signing_route_scope(route.id):
            signed = await self._signer.sign(point, pairs, identity, key.passphrase)
        events = [
            RouteEvent(
                route.id,
                route.round,
                at,
                EventKind.signed,
                actor_id,
                participant_id=me.id,
                details={"doc_id": pair.doc_id, "slot_id": pair.slot_id},
            )
            for pair in signed
        ]
        return await self._settle(point, route, at), events

    async def _readiness(  # noqa: PLR0913 — входы одного расчёта
        self,
        point: RoutePoint,
        route: SigningRoute,
        candidate: RouteFacts,
        people: People,
        actor_id: UUID,
        at: datetime,
    ) -> _Readiness:
        """Помехи и расчёт отправленного маршрута на кандидате (12.6)."""
        blockers = [
            *await self._doc_blockers(point, route, candidate),
            *_people_blockers(point, route, people),
            *_placement_blockers(point, route, candidate.state),
        ]
        if route.status not in SENDABLE_STATUSES or not route.participants:
            return _Readiness(tuple(blockers), evaluate(route, candidate), route)
        if route.status in NEW_VERSION_STATUSES and not has_news(route, candidate):
            # Новая версия без изменений: кнопку отправки не показывают, а не ловят 409 (12.9).
            blockers.append(Blocker(BlockerCode.nothing_changed))
            return _Readiness(tuple(blockers), evaluate(route, candidate), route)
        sent = send(route, candidate, by=actor_id, at=at)
        evaluation = evaluate(sent, candidate)
        first = sent.steps[0]
        sender = next((p for p in sent.participants if p.user_id == actor_id and p.step == first), None)
        if sender is not None:
            view = evaluation.participant(sender.id)
            if view.needs_image or view.needs_plate:
                blockers.append(Blocker(BlockerCode.sender_not_ready, participant_id=sender.id))
        return _Readiness(tuple(blockers), evaluation, sent, sender, sendable=True)

    async def _doc_blockers(self, point: RoutePoint, route: SigningRoute, facts: RouteFacts) -> list[Blocker]:
        blockers: list[Blocker] = []
        for doc_id in route.docs:
            if facts.doc(doc_id).compiled_sha256 is None:
                blockers.append(Blocker(BlockerCode.not_built, doc_id=doc_id))
            holder = await self._s.routes.holding(point.project_id, doc_id)
            if holder is not None and holder.id != route.id:
                # Какой маршрут держит документ: помеха называет его точку и говорит, отменить его или снять с
                # контроля. Завершённый держит документ, пока следит за ним (раздел 5.3), и это по дизайну.
                other = OtherRoute(holder.id, holder.profile_id, point.profile_name(holder.profile_id), holder.status)
                blockers.append(Blocker(BlockerCode.doc_in_other_route, doc_id=doc_id, other_route=other))
        return blockers


@dataclass(frozen=True)
class _Sending:
    """Итог отправки под `project_lock`: расчёт, события и кто потерял согласие (до перехода)."""

    settled: Settled
    events: list[RouteEvent]
    losing: tuple[UUID, ...]


def _to_pin(route: SigningRoute, state: SignaturesState, changes: VersionChanges) -> tuple[str, ...]:
    """У кого отправка снимает версию на подписи: изменившиеся и новые, а ещё документы без версии этого маршрута
    (маршрут 0.20.0 до переноса, версия снята мимо маршрута): после отправки она есть у каждого документа."""
    own = str(route.id)
    return tuple(
        doc_id
        for doc_id in route.docs
        if changes.docs[doc_id] is not DocChange.same
        or (pinned := state.pinned.get(doc_id)) is None
        or pinned.route_id != own
    )


def _sent_details(changes: VersionChanges, versions: Sequence[PinnedVersion]) -> dict[str, object]:
    """`details` события `sent` (12.6): новая ли версия, что изменилось, что осталось, что снято (sha256, размер)."""
    return {
        "new_version": changes.new_version,
        "changed": list(changes.changed),
        "kept": list(changes.kept),
        "versions": [{"doc_id": v.doc_id, "sha256": v.sha256, "size": v.size} for v in versions],
    }


def _new_version_notice(
    route: SigningRoute, losing: Sequence[UUID], settled: Settled, actor_id: UUID
) -> tuple[Notify, ...]:
    """`signing_new_version` (12.6) тем, кто согласовал или подписал изменившийся документ, кроме отправителя и
    тех, кому сейчас уходит запрос: их очередь ещё не настала, запрос придёт в неё."""
    requested = {pid for n in settled.notices if n.notice is Notice.request for pid in n.participant_ids}
    wanted = tuple(
        pid for pid in losing if pid not in requested and route.participant(pid).user_id not in (None, actor_id)
    )
    return (Notify(Notice.new_version, wanted),) if wanted else ()


def _preview_docs(
    point: RoutePoint, route: SigningRoute, state: SignaturesState, candidate: RouteFacts, changes: VersionChanges
) -> tuple[PreviewDoc, ...]:
    result: list[PreviewDoc] = []
    for doc_id in route.docs:
        facts = candidate.doc(doc_id)
        built = facts.compiled_sha256 is not None
        result.append(
            PreviewDoc(
                doc_id=doc_id,
                name=point.doc_name(doc_id),
                built=built,
                token=approval_token(facts) if built else None,
                change=changes.docs[doc_id],
                sent=sent_version(route, state, doc_id),
            )
        )
    return tuple(result)


def _people_blockers(point: RoutePoint, route: SigningRoute, people: People) -> list[Blocker]:
    if not route.participants:
        return [Blocker(BlockerCode.no_participants)]
    blockers = [
        Blocker(BlockerCode.participant_missing, participant_id=p.id)
        for p in route.participants
        if people.membership(p) is Membership.missing
    ]
    _, unassigned = assign_pairs(route.participants, point.required)
    blockers += [Blocker(BlockerCode.slot_unassigned, doc_id=pair.doc_id, slot_id=pair.slot_id) for pair in unassigned]
    return blockers


def _placement_blockers(point: RoutePoint, route: SigningRoute, state: SignaturesState) -> list[Blocker]:
    """Слоты маршрута, которые нельзя подписать: метка видна на странице, а места у неё нет.

    План считает такой слот ждущим (`placement_off`) при любой подписи: слот ЭП с плашкой не станет подписанным,
    и маршрут не завершится, а картинка после согласия в документ не попадёт. Место это включённое размещение
    автора: место из пака без него не ставится.
    """
    blockers: list[Blocker] = []
    for p in route.participants:
        for pair in p.assignments:
            placement = state.placements.get(pair.doc_id, {}).get(pair.slot_id)
            if (placement is None or not placement.enabled) and mark_may_show(point, pair, state):
                blockers.append(Blocker(BlockerCode.placement_off, pair.doc_id, pair.slot_id, p.id))
    return blockers


def _check_interval(route: SigningRoute, at: datetime) -> None:
    if route.sent_at is None:
        return
    left = SEND_INTERVAL - (at - route.sent_at)
    if left > timedelta(0):
        seconds = max(1, math.ceil(left.total_seconds()))
        raise IdentityError(IdentityErrorCode.rate_limited, retry_after_s=seconds, extra={"retry_after": seconds})


def _check_expected(route: SigningRoute, facts: RouteFacts, expected: Mapping[str, str]) -> None:
    changed = [doc_id for doc_id in route.docs if expected.get(doc_id) != approval_token(facts.doc(doc_id))]
    if changed:
        raise DocChangedError(changed)


def _preview_people(
    point: RoutePoint, readiness: _Readiness, facts: RouteFacts, people: People, before: SigningRoute
) -> tuple[PreviewPerson, ...]:
    """Люди отправленного маршрута; `keeps_approval` по согласию до отправки (`before`) против кандидата."""
    route = readiness.route
    previous = {p.id: p for p in before.participants}
    positions = {step: i for i, step in enumerate(route.steps, start=1)}
    return tuple(
        PreviewPerson(
            participant=p,
            step=positions[p.step],
            name=people.name(p),
            membership=people.membership(p),
            method=method_of_participant(p, facts),
            methods=point.methods(pair for pair in p.assignments if pair in point.allowed) if p.assignments else (),
            chooses_method=_chooses_method(point, p, facts.state),
            image_ready=_image_ready(p, facts),
            plate_ready=_plate_ready(p, facts),
            actions=readiness.evaluation.participant(p.id).remaining_actions,
            keeps_approval=keeps_approval(before, facts, previous.get(p.id, p)),
        )
        for p in route.participants
    )


def _chooses_method(point: RoutePoint, p: Participant, state: SignaturesState) -> bool:
    """Способ слота не принимается точкой: подписант выберет его при подписании (раздел 6.3)."""
    for pair in p.assignments:
        allowed = point.allowed.get(pair, ())
        slot = state.slots.get(pair.slot_id)
        method = method_of(slot.sign_mode) if slot is not None else SignMethod.image
        if allowed and method.value not in allowed:
            return True
    return False


def _image_ready(p: Participant, facts: RouteFacts) -> bool:
    for pair in p.assignments:
        slot = facts.state.slots.get(pair.slot_id)
        if mark_of(slot) is not VisibleMark.png:
            continue
        if slot is None or slot.png_path is None or not facts.doc(pair.doc_id).png_exists(slot.png_path):
            return False
    return True


def _plate_ready(p: Participant, facts: RouteFacts) -> bool:
    for pair in p.assignments:
        slot = facts.state.slots.get(pair.slot_id)
        if mark_of(slot) is not VisibleMark.plate:
            continue
        if (slot is None or slot.signer is None) and (p.user_id is None or p.user_id not in facts.plates):
            return False
    return True


# --- отмена и снятие с контроля --------------------------------------------------------------------------------------


class SigningRouteControl(RouteScenario):
    """«Отменить маршрут» и «Снять с контроля»."""

    async def cancel(self, actor: Actor, project_id: UUID, route_id: UUID) -> RouteDetails:
        """Отменить из `draft`, `active`, `paused`, `returned`: подписи и придержанные картинки остаются (5.6),
        версии на подписи снимаются (12.4)."""
        actor_id = actor_uuid(actor)
        at = self._s.clock()
        async with self._s.uow.begin():
            route = await self._get(project_id, route_id, lock=True)
            notice = notice_for(route, Notice.cancelled)
            cancelled = cancel(route)
            point = await self._s.points.load(project_id, route.profile_id)
            # Отмена снимает версии на подписи этого маршрута (12.4): документ снова подписывается по текущей
            # сборке, ЭП над B остаются в состоянии подписей.
            async with route_files(point.project):
                unpinned = RoutePinning(self._s.effects.signatures, self._s.points.template_service).unpin(point, route)
            event = RouteEvent(
                route.id, route.round, at, EventKind.cancelled, actor_id=actor_id, details={"unpinned": list(unpinned)}
            )
            saved = await self._s.routes.save(cancelled, events=[event])
            await self.notify(saved, [notice], actor_id=actor_id)
        return await self._details(actor, point, saved)

    async def archive(self, actor: Actor, project_id: UUID, route_id: UUID) -> RouteDetails:
        """Снять с контроля завершённый (и отменённый): маршрут больше не держит документы."""
        async with self._s.uow.begin():
            route = await self._get(project_id, route_id, lock=True)
            saved = await self._s.routes.save(archive(route))
            await self._audit(RouteAuditAction.archive, saved, actor_id=actor_uuid(actor))
        point = await self._s.points.load(project_id, saved.profile_id)
        return await self._details(actor, point, saved)
