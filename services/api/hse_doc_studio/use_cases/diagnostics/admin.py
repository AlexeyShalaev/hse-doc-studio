"""Админка «Самодиагностика»: обзор, ручной прогон, правка порогов."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from datetime import datetime

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.diagnostics.acceptance import (
    ACCEPTABLE,
    KEY_ACCEPTED,
    REASON_MAX,
    Acceptance,
    acceptances_from,
    acceptances_to,
    is_acceptable,
)
from hse_doc_studio.core.diagnostics.entities import CHECK_BY_ID, CHECKS, CheckSpec, DiagStatus
from hse_doc_studio.core.diagnostics.state import CheckState
from hse_doc_studio.core.diagnostics.thresholds import (
    BOUNDS,
    KEY_LAST_TICK,
    KEY_NOTIFY,
    KEY_PREFIX,
    DiagThresholds,
    misordered,
    thresholds_from,
)
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.protocols import IAuditLog, IInstanceSettingsRepository
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.settings_scope import SOURCE_ADMIN
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.admin.users import require_admin
from hse_doc_studio.use_cases.diagnostics.service import DiagnosticsService


@dataclass(frozen=True)
class CheckView:
    spec: CheckSpec
    state: CheckState | None
    # Принятие, которое сейчас гасит предупреждение этой проверки.
    accepted: Acceptance | None = None

    @property
    def acceptable(self) -> bool:
        """Предупреждение можно принять сейчас (и оно ещё не принято)."""
        if self.state is None or self.accepted is not None:
            return False
        r = self.state.result
        return is_acceptable(self.spec.id.value, r.status, r.reason)


@dataclass(frozen=True)
class AcceptedView:
    """Запись о принятии для списка «Принятые предупреждения»; `active`: предупреждение сейчас есть и погашено."""

    acceptance: Acceptance
    active: bool


@dataclass(frozen=True)
class DiagnosticsOverview:
    checks: list[CheckView]
    accepted: list[AcceptedView]
    overall: DiagStatus
    thresholds: DiagThresholds
    last_tick_at: datetime | None
    interval_s: float
    enabled: bool


def _overall(views: list[CheckView]) -> DiagStatus:
    """Худший статус; принятые осознанно предупреждения в итог не входят."""
    return max(
        (v.state.result.status for v in views if v.state is not None and v.accepted is None), default=DiagStatus.ok
    )


class GetDiagnosticsUC:
    def __init__(
        self,
        service: DiagnosticsService,
        settings: IInstanceSettingsRepository,
        *,
        interval_s: float,
        enabled: bool,
        clock: Clock = utc_now,
    ) -> None:
        self._service = service
        self._settings = settings
        self._interval = interval_s
        self._enabled = enabled
        self._clock = clock

    async def view(self) -> DiagnosticsOverview:
        states = await self._service.snapshot()
        stored = await self._settings.get_all()
        applying = self._service.accepted
        views = [CheckView(spec, states.get(spec.id.value), applying.get(spec.id.value)) for spec in CHECKS]
        now = self._clock()
        accepted = [
            AcceptedView(acc, acc.check_id in applying) for acc in acceptances_from(stored).values() if acc.live(now)
        ]
        raw = stored.get(KEY_LAST_TICK)
        tick = datetime.fromisoformat(raw) if isinstance(raw, str) else None
        return DiagnosticsOverview(
            views, accepted, _overall(views), thresholds_from(stored), tick, self._interval, self._enabled
        )

    async def execute(self, actor: Actor) -> DiagnosticsOverview:
        require_admin(actor)
        return await self.view()


class RunDiagnosticsUC:
    def __init__(self, service: DiagnosticsService, get: GetDiagnosticsUC, audit: IAuditLog) -> None:
        self._service = service
        self._get = get
        self._audit = audit

    async def execute(self, actor: Actor, check: str | None) -> DiagnosticsOverview:
        admin_id = require_admin(actor)
        if check is not None and check not in CHECK_BY_ID:
            raise IdentityError(IdentityErrorCode.not_found)
        await self._service.run(notify=False, only=check)
        await self._audit.record("diagnostics.run", actor_id=admin_id, target=check, details={})
        return await self._get.view()


class UpdateDiagnosticsThresholdsUC:
    def __init__(
        self, settings: IInstanceSettingsRepository, audit: IAuditLog, uow: IUnitOfWork, get: GetDiagnosticsUC
    ) -> None:
        self._settings = settings
        self._audit = audit
        self._uow = uow
        self._get = get

    async def execute(self, actor: Actor, values: Mapping[str, int], notify: bool) -> DiagnosticsOverview:
        admin_id = require_admin(actor)
        if set(values) != set(BOUNDS):
            raise IdentityError(IdentityErrorCode.input_invalid)
        for name, number in values.items():
            lo, hi = BOUNDS[name]
            if not lo <= number <= hi:
                raise IdentityError(IdentityErrorCode.input_invalid)
        if misordered(values):
            raise IdentityError(IdentityErrorCode.input_invalid)
        defaults = DiagThresholds()
        async with self._uow.begin():
            for name, number in values.items():
                if number == getattr(defaults, name):
                    await self._settings.delete(KEY_PREFIX + name)
                else:
                    await self._settings.set(KEY_PREFIX + name, number, source=SOURCE_ADMIN)
            await self._settings.set(KEY_NOTIFY, notify, source=SOURCE_ADMIN)
            await self._audit.record(
                "settings.diagnostics_update", actor_id=admin_id, details={**values, "notify": notify}
            )
        return await self._get.view()


class AcceptDiagnosticsWarningUC:
    """«Принимаю: не делаю сознательно»: запись о принятии с причиной и необязательным сроком; в журнал аудита."""

    def __init__(
        self,
        settings: IInstanceSettingsRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
        service: DiagnosticsService,
        get: GetDiagnosticsUC,
        *,
        clock: Clock = utc_now,
    ) -> None:
        self._settings = settings
        self._audit = audit
        self._uow = uow
        self._service = service
        self._get = get
        self._clock = clock

    async def execute(
        self, actor: Actor, check: str, reason: str, until: datetime | None = None
    ) -> DiagnosticsOverview:
        admin_id = require_admin(actor)
        if check not in CHECK_BY_ID:
            raise IdentityError(IdentityErrorCode.not_found)
        text = reason.strip()
        now = self._clock()
        if not text or len(text) > REASON_MAX or (until is not None and (until.tzinfo is None or until <= now)):
            raise IdentityError(IdentityErrorCode.input_invalid)
        state = (await self._service.snapshot()).get(check)
        if (
            check not in ACCEPTABLE
            or state is None
            or not is_acceptable(check, state.result.status, state.result.reason)
        ):
            # Сбои и проверки безопасности и целостности данных принять нельзя: только исправить.
            raise IdentityError(IdentityErrorCode.input_invalid)
        name = actor.name or actor.email or admin_id
        async with self._uow.begin():
            records = acceptances_from(await self._settings.get_all())
            records[check] = Acceptance(check, text, admin_id, name, now, until)
            await self._settings.set(KEY_ACCEPTED, acceptances_to(records), source=SOURCE_ADMIN)
            await self._audit.record(
                "diagnostics.accept",
                actor_id=admin_id,
                target=check,
                details={"reason": text, "until": until.isoformat() if until else None, "cause": state.result.reason},
            )
        return await self._get.view()


class RevokeDiagnosticsAcceptanceUC:
    """«Вернуть предупреждение»: снимает принятие; в журнал аудита."""

    def __init__(
        self,
        settings: IInstanceSettingsRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
        get: GetDiagnosticsUC,
    ) -> None:
        self._settings = settings
        self._audit = audit
        self._uow = uow
        self._get = get

    async def execute(self, actor: Actor, check: str) -> DiagnosticsOverview:
        admin_id = require_admin(actor)
        async with self._uow.begin():
            records = acceptances_from(await self._settings.get_all())
            removed = records.pop(check, None)
            if removed is None:
                raise IdentityError(IdentityErrorCode.not_found)
            if records:
                await self._settings.set(KEY_ACCEPTED, acceptances_to(records), source=SOURCE_ADMIN)
            else:
                await self._settings.delete(KEY_ACCEPTED)
            await self._audit.record(
                "diagnostics.accept_revoke", actor_id=admin_id, target=check, details={"reason": removed.reason}
            )
        return await self._get.view()


THRESHOLD_FIELDS = [f.name for f in fields(DiagThresholds) if f.name != "notify"]
