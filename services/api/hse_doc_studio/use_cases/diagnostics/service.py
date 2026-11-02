"""Прогон проверок: таймаут и изоляция сбоев, сохранение состояния, уведомления админам с антидребезгом."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Sequence
from datetime import timedelta

import structlog

from hse_doc_studio.core.diagnostics.entities import CheckResult, DiagStatus, Verdict
from hse_doc_studio.core.diagnostics.ports import IDiagCheck, IDiagStore
from hse_doc_studio.core.diagnostics.state import CheckState, advance
from hse_doc_studio.core.diagnostics.thresholds import KEY_LAST_TICK, DiagThresholds, thresholds_from
from hse_doc_studio.core.identity.protocols import IInstanceSettingsRepository
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.invitations.entities import NotificationKind, NotificationPayload
from hse_doc_studio.core.invitations.protocols import INotifier
from hse_doc_studio.core.lifecycle.ports import IAdminDirectory

logger = structlog.get_logger(__name__)


class DiagnosticsService:
    def __init__(
        self,
        checks: Sequence[IDiagCheck],
        store: IDiagStore,
        settings: IInstanceSettingsRepository,
        notifier: INotifier,
        admins: IAdminDirectory,
        *,
        timeout_s: float,
        clock: Clock = utc_now,
    ) -> None:
        self._checks = list(checks)
        self._store = store
        self._settings = settings
        self._notifier = notifier
        self._admins = admins
        self._timeout = timeout_s
        self._clock = clock
        self._lock = asyncio.Lock()
        self.last: dict[str, CheckState] = {}  # для /metrics этого процесса

    @property
    def check_ids(self) -> list[str]:
        return [c.spec.id.value for c in self._checks]

    async def snapshot(self) -> dict[str, CheckState]:
        self.last = await self._store.load()
        return self.last

    async def tick(self) -> None:
        """Плановый проход (под лидерским локом): все проверки, уведомления, метка живости."""
        await self.run(notify=True)
        await self._settings.set(KEY_LAST_TICK, self._clock().isoformat(), source="system")

    async def run(self, *, notify: bool, only: str | None = None) -> dict[str, CheckState]:
        """Ручной прогон не двигает счётчик уведомлений: в нём `notify=False`, отметки о рассылке сохраняются."""
        async with self._lock:
            thresholds = thresholds_from(await self._settings.get_all())
            targets = [c for c in self._checks if only is None or c.spec.id.value == only]
            results = await asyncio.gather(*(self._one(c, thresholds) for c in targets))
            previous = await self._store.load()
            for result in results:
                await self._record(previous.get(result.check_id), result, thresholds, notify=notify)
            self.last = await self._store.load()
            return self.last

    async def _one(self, check: IDiagCheck, thresholds: DiagThresholds) -> CheckResult:
        started = time.monotonic()
        now = self._clock()
        try:
            verdict = await asyncio.wait_for(check.run(thresholds, now), self._timeout)
        except TimeoutError:
            verdict = Verdict(DiagStatus.fail, "check_timeout", {"seconds": round(self._timeout)})
        except Exception as exc:
            logger.warning("diagnostics_check_failed", check=check.spec.id.value, exc_info=True)
            verdict = Verdict(DiagStatus.fail, "check_error", {"error": type(exc).__name__})
        return CheckResult(
            check_id=check.spec.id.value,
            status=verdict.status,
            reason=verdict.reason,
            values=dict(verdict.values),
            checked_at=now,
            duration_ms=int((time.monotonic() - started) * 1000),
        )

    async def _record(
        self, prev: CheckState | None, result: CheckResult, thresholds: DiagThresholds, *, notify: bool
    ) -> None:
        now = self._clock()
        state, notice = advance(
            prev, result, confirm_runs=thresholds.confirm_runs, repeat=timedelta(hours=thresholds.repeat_hours), now=now
        )
        if not notify:
            # Ручной прогон: статус и серия обновляются, рассылку и её отметки оставляем как были.
            state = CheckState(
                state.result,
                state.status_since,
                state.streak,
                prev.notified_status if prev else None,
                prev.notified_at if prev else None,
            )
            notice = None
        await self._store.save(state)
        if notice is not None and thresholds.notify:
            await self._alert(result, notice)

    async def _alert(self, result: CheckResult, notice: str) -> None:
        payload = NotificationPayload(outcome=notice, ref_id=result.check_id, excerpt=result.reason)
        day = self._clock().date().isoformat()
        try:
            for admin_id in await self._admins.active_admin_ids():
                await self._notifier.notify(
                    admin_id,
                    NotificationKind.system_alert,
                    payload,
                    dedupe_key=f"diag:{result.check_id}:{notice}:{day}",
                )
        except Exception:
            logger.exception("diagnostics_alert_failed", check=result.check_id)
