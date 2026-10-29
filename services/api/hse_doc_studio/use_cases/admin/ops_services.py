"""Здоровье сервисов установки для экрана админа: проверки готовности, раннеры и почта.

Недоступный сервис даёт статус и причину, а не ошибку запроса: экран нужен именно тогда, когда что-то сломалось.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.jobs.admin import RunnerStatus, runner_status
from hse_doc_studio.core.jobs.runners import IRunnerRepository
from hse_doc_studio.use_cases.admin.users import require_admin
from hse_doc_studio.use_cases.identity.smtp_settings import SmtpSettingsService

# Проверки готовности, которые регистрируют срезы хранилища и сервисов; незарегистрированная даёт `not_configured`.
PROBED_SERVICES = ("database", "s3", "languagetool", "onlyoffice")


class ServiceState(StrEnum):
    ok = "ok"
    down = "down"
    degraded = "degraded"
    not_configured = "not_configured"


@dataclass(frozen=True)
class ServiceHealth:
    id: str
    state: ServiceState
    # Короткий код причины для журнала и подсказки: `timeout`, имя исключения, `no_online_runner`.
    reason: str | None = None
    # Для раннеров: сколько всего и сколько в сети.
    total: int | None = None
    online: int | None = None


class ServicesOverviewUC:
    def __init__(self, runners: IRunnerRepository, smtp: SmtpSettingsService, *, clock: Clock = utc_now) -> None:
        self._runners = runners
        self._smtp = smtp
        self._clock = clock

    async def execute(self, actor: Actor, probes: Mapping[str, str | None]) -> list[ServiceHealth]:
        """`probes`: имя -> причина сбоя или None, результат выполненных проверок готовности."""
        require_admin(actor)
        items = [_probed(name, probes) for name in PROBED_SERVICES]
        items.append(await self._runners_health())
        items.append(await self._smtp_health())
        return items

    async def _runners_health(self) -> ServiceHealth:
        now = self._clock()
        active = [r for r in await self._runners.list() if r.revoked_at is None]
        online = sum(1 for r in active if runner_status(r, now) is RunnerStatus.online)
        if not active:
            return ServiceHealth("runners", ServiceState.not_configured, total=0, online=0)
        if online == 0:
            return ServiceHealth("runners", ServiceState.down, "no_online_runner", total=len(active), online=0)
        return ServiceHealth("runners", ServiceState.ok, total=len(active), online=online)

    async def _smtp_health(self) -> ServiceHealth:
        view = await self._smtp.view()
        return ServiceHealth("smtp", ServiceState.ok if view.config.enabled else ServiceState.not_configured)


def _probed(name: str, probes: Mapping[str, str | None]) -> ServiceHealth:
    if name not in probes:
        return ServiceHealth(name, ServiceState.not_configured)
    reason = probes[name]
    return ServiceHealth(name, ServiceState.ok if reason is None else ServiceState.down, reason)
