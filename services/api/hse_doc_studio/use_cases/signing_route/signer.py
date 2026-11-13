"""Сценарии подписанта: задача и действия на странице `/sign/...` (docs/design/signing-route.md, 3.2, 4, 5.4, 6 и 8).

Задача, согласие (со сменой способа и «Согласовать и подписать»), подпись итогового PDF ключом Студии, возврат на
доработку, своя картинка и данные плашки. Действует только участник маршрута (`user_id` = актор), остальным 404;
на каждый свой слот нужно право `SIGN`.

Подписант это рецензент с персоной: права писать файлы проекта у него нет. Всё, что маршрут делает с документами
от его имени (открыть картинку, записать способ и плашку, зафиксировать), идёт через сценарий, а не через его
права: право на это дал отправитель маршрута (раздел 6.2).

Ход любого действия (раздел 5.1): под блокировкой строки маршрута и `project_lock` читаются факты; если документы
изменились вне маршрута, маршрут останавливается, а действие отклоняется (`doc_changed`); иначе проверяются очередь
и отпечатки (`expected`), всё проверяемое проверяется до записи файлов, затем переход, файловые эффекты расчёта
(картинки, плашки, фиксация), подпись, и одна транзакция с маршрутом, событиями и уведомлениями.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from uuid import UUID

from hse_doc_studio.core.access.actions import Action
from hse_doc_studio.core.access.checker import ProjectForbiddenError
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.entities import SigningIdentity
from hse_doc_studio.core.enums import SignMode
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import ISignatureRepository
from hse_doc_studio.core.signatures.errors import GpgUnavailableError
from hse_doc_studio.core.signatures.key_policy import SigningKeyStorageDeniedError
from hse_doc_studio.core.signatures.plan import (
    SignMethod,
    VisibleMark,
    mark_of,
    profile_restrictions,
    slot_mode_conflict,
)
from hse_doc_studio.core.signatures.ports import IMarkMeasure, IOpenPgpKeyImporter
from hse_doc_studio.core.signatures.signer_profile import (
    MAX_PROFILE_IMAGE_BYTES,
    IPublicKeyReader,
    PublicKeyKind,
    png_size,
)
from hse_doc_studio.core.signing_route.audit import RouteAuditAction, signing_route_scope
from hse_doc_studio.core.signing_route.engine import Evaluation, ParticipantView, evaluate, notice_for
from hse_doc_studio.core.signing_route.entities import (
    RETURN_COMMENT_MAX,
    EventKind,
    NextAction,
    Notice,
    Participant,
    RouteConflictError,
    RouteEvent,
    RouteInputError,
    SigningRoute,
    StopReason,
    not_your_turn,
)
from hse_doc_studio.core.signing_route.readiness import DocChangedError
from hse_doc_studio.core.signing_route.signer import (
    APPROVE_ACTIONS,
    SIGN_ACTIONS,
    InvalidFileError,
    MethodNotAllowedError,
    acting_participant,
    available_methods,
    changed_docs,
    check_expected,
    ensure_layer_open,
    ensure_turn,
    mode_for,
    no_place_for_method,
    own_slots,
    plates_without_signer,
    task_tokens,
    unsigned_crypto,
    with_method,
    with_signer,
)
from hse_doc_studio.core.signing_route.transitions import approve, refresh_snapshot, return_route
from hse_doc_studio.core.value_objects import SignaturesState, SignerInfo
from hse_doc_studio.use_cases.signatures._studio_signer import PlateSignerMismatchError
from hse_doc_studio.use_cases.signatures.upload_signature_png import UploadSignaturePngInput, UploadSignaturePngUC
from hse_doc_studio.use_cases.signer_profile.profile import SaveProfileImageUC
from hse_doc_studio.use_cases.signing_route.facts import LoadedFacts
from hse_doc_studio.use_cases.signing_route.key_signer import KeyNotFoundError, KeyRequest, RouteKeySigner
from hse_doc_studio.use_cases.signing_route.point import RoutePoint
from hse_doc_studio.use_cases.signing_route.scenario import (
    RouteScenario,
    RouteServices,
    Settled,
    actor_uuid,
    closing_events,
    frozen_events,
    route_files,
)
from hse_doc_studio.use_cases.signing_route.task_view import TaskDetails, TaskKeys, build_task

# Отказ подписи ключом Студии: нет ключа, нужен пароль, чужой слот, gpg отказал.
_KEY_ERRORS = (ValueError, PermissionError, NotFoundError, ProjectForbiddenError)


@dataclass(frozen=True)
class ApproveRequest:
    """Согласие: отпечатки показанного, новый способ своих слотов и ключ для «Согласовать и подписать»."""

    expected: Mapping[str, str]
    method: SignMethod | None = None
    sign: KeyRequest | None = None


@dataclass(frozen=True)
class SignRequest:
    """Подпись итогового PDF ключом Студии: отпечатки показанного и ключ (без id ключ по умолчанию)."""

    expected: Mapping[str, str]
    key: KeyRequest = field(default_factory=KeyRequest)


@dataclass(frozen=True)
class SignerTools:
    """Порты действий подписанта сверх общих портов маршрута."""

    signatures: ISignatureRepository
    upload_png: UploadSignaturePngUC
    profile_image: SaveProfileImageUC
    key_reader: IPublicKeyReader
    key_importer: IOpenPgpKeyImporter
    measure: IMarkMeasure


@dataclass(frozen=True)
class _Turn:
    """Действие участника: кто, когда и что известно о маршруте под блокировками."""

    actor: Actor
    actor_id: UUID
    at: datetime
    point: RoutePoint
    route: SigningRoute
    loaded: LoadedFacts
    evaluation: Evaluation
    me: Participant

    @property
    def view(self) -> ParticipantView:
        return self.evaluation.participant(self.me.id)

    @property
    def project_id(self) -> UUID:
        return self.point.project_id


@dataclass(frozen=True)
class _Outcome:
    """Итог действия: маршрут после эффектов, события и то, что сказать после записи.

    `deferred` отказ, который не отменяет сделанное (подпись не удалась после согласия и фиксации): маршрут
    записывается, отказ возвращается после записи. `returned` маршрут возвращён на доработку: уведомить автора.
    """

    settled: Settled
    events: Sequence[RouteEvent] = ()
    comment: str | None = None
    returned: bool = False
    deferred: Exception | None = None


_Step = Callable[[_Turn], Awaitable[_Outcome]]


class SigningTaskScenario(RouteScenario):
    """Задача подписанта и его действия."""

    def __init__(self, services: RouteServices, signer: RouteKeySigner, tools: SignerTools) -> None:
        super().__init__(services)
        self._signer = signer
        self._tools = tools

    # --- чтение -----------------------------------------------------------------------------------------------------

    async def get(self, actor: Actor, project_id: UUID, route_id: UUID) -> TaskDetails:
        """Моя задача; не участнику маршрута 404. Ничего не пишет."""
        route = await self._get(project_id, route_id)
        point = await self._s.points.load(project_id, route.profile_id)
        return await self._task(actor_uuid(actor), point, route)

    async def image(self, actor: Actor, project_id: UUID, route_id: UUID) -> bytes | None:
        """Своя картинка подписи, как она лежит в слоте (PNG); None, пока не загружена. Не участнику 404."""
        route = await self._get(project_id, route_id)
        point = await self._s.points.load(project_id, route.profile_id)
        loaded = await self._s.facts.load(point, route)
        me = acting_participant(route, evaluate(route, loaded.facts), actor_uuid(actor))
        for slot_id in own_slots(me):
            slot = loaded.state.slots.get(slot_id)
            path = point.project.folder / slot.png_path if slot is not None and slot.png_path else None
            if path is not None and path.is_file():
                return await asyncio.to_thread(path.read_bytes)
        return None

    async def _task(self, actor_id: UUID, point: RoutePoint, route: SigningRoute) -> TaskDetails:
        loaded = await self._s.facts.load(point, route)
        evaluation = evaluate(route, loaded.facts)
        me = acting_participant(route, evaluation, actor_id)
        events = await self._s.routes.list_events(route.id)
        people = await self._people_of(point.project_id, route, loaded, events)
        allowed = await self._signer.keys_allowed()
        keys = TaskKeys(allowed, await self._signer.default_key_info() if allowed else None)
        task = build_task(
            point,
            route,
            loaded.facts,
            evaluation,
            me,
            people,
            events,
            keys,
            self._tools.measure,
            manages=await self._manages(point.project_id),
        )
        if task.plate is None and me.assignments:
            # Данных плашки нет ни в слоте, ни в профиле: их даст ключ по умолчанию при согласии.
            task = replace(task, plate=await self._signer.default_plate())
        return task

    # --- действия ---------------------------------------------------------------------------------------------------

    async def approve(self, actor: Actor, project_id: UUID, route_id: UUID, request: ApproveRequest) -> TaskDetails:
        """«Согласовать» и «Согласовать и подписать»: согласие текущих сборок своих документов, в свою очередь.

        `method` меняет способ своих слотов (из разрешённых сейчас). `sign` подписывает свои слоты ЭП ключом
        Студии, если после согласия документы зафиксированы; плашку без подписанта заполняет этим же ключом. Ошибка
        подписи не отменяет согласие: маршрут записывается, ошибка возвращается после записи.
        """

        async def step(turn: _Turn) -> _Outcome:
            ensure_turn(turn.evaluation, turn.view, APPROVE_ACTIONS)
            check_expected(task_tokens(turn.route, turn.me, turn.view, turn.loaded.facts), request.expected)
            await self._require_sign(turn)
            identity = await self._signer.check(request.sign) if request.sign is not None else None
            state = await self._approval_state(turn, request.method, identity)
            changed = state != turn.loaded.state
            # Расчёт на ещё не записанном состоянии: отказ (нет картинки, нет данных плашки) ничего не меняет.
            # Способ и плашка это его собственная правка видимого слоя: снимок маршрута её принимает (раздел 5.5).
            loaded = await self._s.facts.load(turn.point, turn.route, state) if changed else turn.loaded
            route = refresh_snapshot(turn.route, loaded.facts) if changed else turn.route
            approved = approve(route, loaded.facts, turn.me.id, at=turn.at)
            if changed:
                self._tools.signatures.save_state(turn.point.project.folder, state)
                await self._audit_own_change(turn, state, request.method)
            settled = await self._settle(turn.point, approved, turn.at, None if changed else loaded)
            events = [self._event(turn, EventKind.approved), *frozen_events(settled, turn.at)]
            deferred: Exception | None = None
            if identity is not None and request.sign is not None:
                settled, signed, deferred = await self._sign_mine(turn, settled, identity, request.sign.passphrase)
                events += signed
            return _Outcome(settled, [*events, *closing_events(settled, turn.at)], deferred=deferred)

        return await self._act(actor, project_id, route_id, step)

    async def sign(self, actor: Actor, project_id: UUID, route_id: UUID, request: SignRequest) -> TaskDetails:
        """«Подписать»: свои слоты ЭП над зафиксированным PDF ключом Студии, когда маршрут ждёт подписи."""

        async def step(turn: _Turn) -> _Outcome:
            ensure_turn(turn.evaluation, turn.view, SIGN_ACTIONS)
            check_expected(task_tokens(turn.route, turn.me, turn.view, turn.loaded.facts), request.expected)
            await self._require_sign(turn)
            identity = await self._signer.check(request.key)
            before = Settled(turn.route, turn.loaded, turn.evaluation)
            settled, signed, deferred = await self._sign_mine(turn, before, identity, request.key.passphrase)
            if deferred is not None and not signed:
                # Ничего не подписано и не изменено: отказ как есть, маршрут не трогаем.
                raise deferred
            return _Outcome(settled, [*signed, *closing_events(settled, turn.at)], deferred=deferred)

        return await self._act(actor, project_id, route_id, step)

    async def return_for_rework(self, actor: Actor, project_id: UUID, route_id: UUID, comment: str) -> TaskDetails:
        """«Вернуть на доработку»: любой участник в свою очередь, с обязательным комментарием (раздел 5.6)."""
        text = comment.strip()
        if not text or len(text) > RETURN_COMMENT_MAX:
            raise RouteInputError(
                "bad_comment",
                localized_error(
                    "Комментарий обязателен, не длиннее 2000 символов",
                    "A comment of up to 2000 characters is required",
                ),
            )

        async def step(turn: _Turn) -> _Outcome:
            returned = return_route(turn.route, turn.loaded.facts, turn.me.id)
            settled = await self._settle(turn.point, returned, turn.at, turn.loaded)
            details = {"comment": text, "reason": StopReason.returned.value}
            return _Outcome(settled, [self._event(turn, EventKind.returned, details)], comment=text, returned=True)

        return await self._act(actor, project_id, route_id, step)

    async def set_image(
        self, actor: Actor, project_id: UUID, route_id: UUID, png: bytes, *, remember: bool
    ) -> TaskDetails:
        """Своя картинка подписи (загруженная или нарисованная) во все свои слоты; `remember` ещё и в профиль.

        Картинка остаётся придержанной до согласия: на документе её не видно (инвариант 2).
        """
        _check_png(png)

        async def step(turn: _Turn) -> _Outcome:
            ensure_layer_open(turn.evaluation, turn.view, turn.me)
            await self._require_sign(turn)
            if remember:
                await self._tools.profile_image.execute(turn.actor, png)
            for slot_id in own_slots(turn.me):
                await self._tools.upload_png.execute(
                    UploadSignaturePngInput(
                        project_id=turn.project_id, slot_id=slot_id, filename=f"{slot_id}.png", content=png
                    )
                )
            await self._audit(
                RouteAuditAction.signer_image,
                turn.route,
                actor_id=turn.actor_id,
                participant=turn.me,
                details={
                    "slot_ids": list(own_slots(turn.me)),
                    "sha256": hashlib.sha256(png).hexdigest(),
                    "size": len(png),
                    "remember": remember,
                },
            )
            return await self._after_own_change(turn)

        return await self._act(actor, project_id, route_id, step)

    async def set_plate_key(self, actor: Actor, project_id: UUID, route_id: UUID, identity_id: UUID) -> TaskDetails:
        """Данные плашки своих слотов из открытой части своего ключа Студии."""

        async def step(turn: _Turn) -> _Outcome:
            ensure_layer_open(turn.evaluation, turn.view, turn.me)
            await self._require_sign(turn)
            try:
                signer = await self._signer.plate_of(await self._signer.own_key(identity_id))
            except (KeyNotFoundError, SigningKeyStorageDeniedError):
                raise
            except ValueError as exc:
                # Ключ есть, но плашку из него не собрать (нет сертификата, нет в связке): для страницы это
                # тот же отказ, что и чужой ключ.
                raise KeyNotFoundError(str(exc)) from exc
            return await self._write_plate(turn, signer, source="studio")

        return await self._act(actor, project_id, route_id, step)

    async def set_plate_file(self, actor: Actor, project_id: UUID, route_id: UUID, blob: bytes) -> TaskDetails:
        """Данные плашки своих слотов из сертификата X.509 или открытого ключа OpenPGP файлом.

        Файл с закрытым ключом отвергается целиком. Открытый ключ OpenPGP попадает в связку ключей: им будет
        проверена открепленная подпись, которую подписант загрузит после фиксации.
        """

        async def step(turn: _Turn) -> _Outcome:
            ensure_layer_open(turn.evaluation, turn.view, turn.me)
            await self._require_sign(turn)
            try:
                parsed = await self._tools.key_reader.read(blob)
                if parsed.kind is PublicKeyKind.openpgp:
                    await asyncio.to_thread(self._tools.key_importer.import_public_key, parsed.data)
            except (ValueError, GpgUnavailableError) as exc:
                raise InvalidFileError(str(exc)) from exc
            return await self._write_plate(turn, parsed.plate, source="file")

        return await self._act(actor, project_id, route_id, step)

    # --- общий ход --------------------------------------------------------------------------------------------------

    async def _act(self, actor: Actor, project_id: UUID, route_id: UUID, step: _Step) -> TaskDetails:
        actor_id = actor_uuid(actor)
        at = self._s.clock()
        refusal: RouteConflictError | None = None
        outcome: _Outcome | None = None
        async with self._s.uow.begin():
            route = await self._get(project_id, route_id, lock=True)
            point = await self._s.points.load(project_id, route.profile_id)
            saved = route
            async with route_files(point.project):
                await self._migrate(point, route, at)
                loaded = await self._s.facts.load(point, route)
                evaluation = evaluate(route, loaded.facts)
                me = acting_participant(route, evaluation, actor_id)
                stopped = await self._stop_if_changed(point, route, loaded, at)
                if stopped is not None:
                    saved = stopped
                    docs = changed_docs(route, loaded.facts)
                    refusal = DocChangedError(docs) if docs else not_your_turn()
                else:
                    # Всё, что действие делает с подписями (фиксация, подпись, картинка в профиль), сделано в маршруте.
                    with signing_route_scope(route.id):
                        outcome = await step(_Turn(actor, actor_id, at, point, route, loaded, evaluation, me))
            if outcome is not None:
                saved = await self._commit(
                    outcome.settled, outcome.events, actor_id=actor_id, at=at, comment=outcome.comment
                )
                if outcome.returned:
                    await self.notify(
                        saved, [notice_for(saved, Notice.returned)], actor_id=actor_id, comment=outcome.comment
                    )
        if refusal is not None:
            raise refusal
        if outcome is not None and outcome.deferred is not None:
            raise outcome.deferred
        return await self._task(actor_id, point, saved)

    def _event(self, turn: _Turn, kind: EventKind, details: Mapping[str, object] | None = None) -> RouteEvent:
        route = turn.route
        return RouteEvent(
            route.id, route.round, turn.at, kind, turn.actor_id, participant_id=turn.me.id, details=details or {}
        )

    async def _require_sign(self, turn: _Turn) -> None:
        """Право `SIGN` на каждый свой слот: участник маршрута, у которого его отняли, не действует (403)."""
        for slot_id in own_slots(turn.me):
            await self._s.access.require(turn.project_id, Action.SIGN, slot_id)

    async def _after_own_change(self, turn: _Turn) -> _Outcome:
        """Подписант изменил своё на своей странице: перечитать факты, обновить снимок, довести расчёт."""
        settled = await self._settle(turn.point, turn.route, turn.at)
        return _Outcome(settled, [*frozen_events(settled, turn.at), *closing_events(settled, turn.at)])

    async def _write_plate(self, turn: _Turn, signer: SignerInfo, *, source: str) -> _Outcome:
        folder = turn.point.project.folder
        state = with_signer(turn.loaded.state, own_slots(turn.me), signer)
        if state != turn.loaded.state:
            self._tools.signatures.save_state(folder, state)
            await self._audit_plate(turn, state, source=source)
        # Плашка с данными меняет видимый слой; возможно, менять его больше некому, и расчёт зафиксирует документы.
        return await self._after_own_change(turn)

    async def _audit_own_change(self, turn: _Turn, state: SignaturesState, method: SignMethod | None) -> None:
        """Журнал аудита: что согласие изменило в своих слотах, способ подписи и данные плашки."""
        before = turn.loaded.state
        slots = own_slots(turn.me)
        if method is not None and _modes(before, slots) != _modes(state, slots):
            await self._audit(
                RouteAuditAction.signer_method,
                turn.route,
                actor_id=turn.actor_id,
                participant=turn.me,
                details={"slot_ids": list(slots), "method": method.value},
            )
        if _plates(before, slots) != _plates(state, slots):
            await self._audit_plate(turn, state, source="approval")

    async def _audit_plate(self, turn: _Turn, state: SignaturesState, *, source: str) -> None:
        """Журнал аудита: данные плашки своих слотов. Только открытые сведения, напечатанные на плашке:
        вид сертификата или ключа и его номер; сам ключ, сертификат и файл в журнал не попадают."""
        slots = own_slots(turn.me)
        before = _plates(turn.loaded.state, slots)
        changed = {
            slot_id: plate
            for slot_id, plate in _plates(state, slots).items()
            if plate is not None and before.get(slot_id) != plate
        }
        plate = next(iter(changed.values()), None)
        if plate is None:
            return
        await self._audit(
            RouteAuditAction.signer_plate,
            turn.route,
            actor_id=turn.actor_id,
            participant=turn.me,
            details={"slot_ids": list(changed), "source": source, "plate_kind": plate.kind, "cert_id": plate.cert_id},
        )

    async def _approval_state(
        self, turn: _Turn, method: SignMethod | None, identity: SigningIdentity | None
    ) -> SignaturesState:
        """Состояние подписей, с которым участник согласует: выбранный способ и плашка из ключа подписи.

        Ничего не пишет. Способ должен быть среди разрешённых сейчас и не конфликтовать с точками, которые требуют
        слот. Ключ, которым участник сейчас подпишет, заполняет его плашки без подписанта; плашка с другим
        подписантом это отказ до любых записей.
        """
        me = turn.me
        state = turn.loaded.state
        if method is not None:
            point_methods = turn.point.methods(pair for pair in me.assignments if pair in turn.point.allowed)
            server_keys = await self._signer.keys_allowed()
            allowed = available_methods(me, turn.view, state, point_methods, server_keys=server_keys)
            if method not in allowed:
                # Способ годился бы, но для его картинки или плашки нет места на странице: называем причину.
                unplaced = available_methods(
                    me, turn.view, state, point_methods, server_keys=server_keys, need_place=False
                )
                raise no_place_for_method() if method in unplaced else MethodNotAllowedError
            conflict = _method_conflict(turn.point, me, state, method, identity)
            if conflict is not None:
                raise MethodNotAllowedError(conflict)
            state = with_method(state, me, method)
        if identity is None:
            return await self._with_default_plate(turn, state)
        signer = await self._signer.plate_of(identity)
        for slot_id in own_slots(me):
            slot = state.slots.get(slot_id)
            plate = slot.signer if slot is not None and mark_of(slot) is VisibleMark.plate else None
            if plate is not None and plate.signer_id and signer.signer_id and plate.signer_id != signer.signer_id:
                raise PlateSignerMismatchError(plate.owner or plate.signer_id)
        # Плашка без подписанта бывает только до фиксации: перед ней расчёт заполняет плашки сам (`FillPlate`).
        missing = plates_without_signer(me, state)
        return with_signer(state, missing, signer) if missing else state

    async def _with_default_plate(self, turn: _Turn, state: SignaturesState) -> SignaturesState:
        """Согласие без подписи ключом: плашки без подписанта получают данные ключа по умолчанию участника.

        Только если серверу нечем их заполнить иначе (в профиле подписанта ключа нет): страница показывает ключ
        по умолчанию как известные данные плашки (`me.plate`), и согласие обязано с этим совпасть.
        """
        me = turn.me
        missing = plates_without_signer(me, state)
        if not missing or (me.user_id is not None and me.user_id in turn.loaded.facts.plates):
            return state
        signer = await self._signer.default_plate()
        return with_signer(state, missing, signer) if signer is not None else state

    async def _sign_mine(
        self, turn: _Turn, settled: Settled, identity: SigningIdentity, passphrase: str
    ) -> tuple[Settled, list[RouteEvent], Exception | None]:
        """Подписать свои слоты ЭП, если маршрут ждёт подписи участника; что подписано, видно по фактам после."""
        route = settled.route
        me = route.participant(turn.me.id)
        if settled.evaluation.participant(me.id).next_action is not NextAction.sign:
            return settled, [], None
        pending = unsigned_crypto(me, settled.loaded.facts)
        error: Exception | None = None
        try:
            await self._signer.sign(turn.point, pending, identity, passphrase)
        except _KEY_ERRORS as exc:
            error = exc
        after = await self._settle(turn.point, route, turn.at)
        # ЭП, сброшенные фиксацией перед подписью, остаются в итоге: их владельцам запрос заново (14.6).
        after = replace(after, reset=(*settled.reset, *after.reset))
        left = set(unsigned_crypto(after.route.participant(me.id), after.loaded.facts))
        events = [
            self._event(turn, EventKind.signed, {"doc_id": pair.doc_id, "slot_id": pair.slot_id})
            for pair in pending
            if pair not in left
        ]
        return after, events, error


def _modes(state: SignaturesState, slots: Sequence[str]) -> dict[str, SignMode | None]:
    return {slot_id: slot.sign_mode if (slot := state.slots.get(slot_id)) is not None else None for slot_id in slots}


def _plates(state: SignaturesState, slots: Sequence[str]) -> dict[str, SignerInfo | None]:
    return {slot_id: slot.signer if (slot := state.slots.get(slot_id)) is not None else None for slot_id in slots}


def _check_png(png: bytes) -> None:
    if not png:
        raise InvalidFileError(localized_error("Загружен пустой файл", "Empty file upload"))
    if len(png) > MAX_PROFILE_IMAGE_BYTES:
        raise InvalidFileError(
            localized_error(
                "Картинка подписи больше 2 МБ: уменьшите её или удалите фон в редакторе",
                "The signature image is larger than 2 MB: shrink it or remove the background in the editor",
            )
        )
    if png_size(png) is None:
        raise InvalidFileError(localized_error("Загруженный файл не является PNG", "Uploaded file is not a PNG"))


def _method_conflict(
    point: RoutePoint, me: Participant, state: SignaturesState, method: SignMethod, identity: SigningIdentity | None
) -> str | None:
    """Почему способ несовместим в принципе (`slot_mode_conflict`): PAdES ключом OpenPGP, способ вне точек слота."""
    project = point.project
    kind = identity.kind.value if identity is not None else None
    for slot_id in own_slots(me):
        slot = state.slots.get(slot_id)
        mode = mode_for(method, slot.sign_mode if slot is not None else SignMode.image)
        restrictions = profile_restrictions(project, point.version, slot_id, str(project.lang))
        conflict = slot_mode_conflict(mode, kind, restrictions)
        if conflict is not None:
            return conflict
    return None
