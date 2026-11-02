"""Админка «Самодиагностика»: обзор, ручной прогон, правка порогов."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from datetime import datetime

from hse_doc_studio.core.access.entities import Actor
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
from hse_doc_studio.core.settings_scope import SOURCE_ADMIN
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.admin.users import require_admin
from hse_doc_studio.use_cases.diagnostics.service import DiagnosticsService


@dataclass(frozen=True)
class CheckView:
    spec: CheckSpec
    state: CheckState | None


@dataclass(frozen=True)
class DiagnosticsOverview:
    checks: list[CheckView]
    overall: DiagStatus
    thresholds: DiagThresholds
    last_tick_at: datetime | None
    interval_s: float
    enabled: bool


def _overall(views: list[CheckView]) -> DiagStatus:
    return max((v.state.result.status for v in views if v.state is not None), default=DiagStatus.ok)


class GetDiagnosticsUC:
    def __init__(
        self, service: DiagnosticsService, settings: IInstanceSettingsRepository, *, interval_s: float, enabled: bool
    ) -> None:
        self._service = service
        self._settings = settings
        self._interval = interval_s
        self._enabled = enabled

    async def view(self) -> DiagnosticsOverview:
        states = await self._service.snapshot()
        stored = await self._settings.get_all()
        views = [CheckView(spec, states.get(spec.id.value)) for spec in CHECKS]
        raw = stored.get(KEY_LAST_TICK)
        tick = datetime.fromisoformat(raw) if isinstance(raw, str) else None
        return DiagnosticsOverview(views, _overall(views), thresholds_from(stored), tick, self._interval, self._enabled)

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


THRESHOLD_FIELDS = [f.name for f in fields(DiagThresholds) if f.name != "notify"]
