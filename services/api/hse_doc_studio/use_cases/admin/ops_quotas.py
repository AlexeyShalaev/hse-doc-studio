"""Квоты задач установки: чтение для очереди (с короткой памятью) и правка админом."""

from __future__ import annotations

import time
from collections.abc import Callable

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.protocols import IAuditLog, IInstanceSettingsRepository
from hse_doc_studio.core.jobs.quotas import (
    KEY_MAX_DURATION_S,
    KEY_ORG_CONCURRENT,
    KEY_USER_CONCURRENT,
    QuotaSettings,
    quota_settings_from,
)
from hse_doc_studio.core.jobs.scheduler import QueueQuota
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.admin.users import require_admin
from hse_doc_studio.use_cases.identity.auth_settings import SOURCE_ADMIN

# Раннер опрашивает очередь каждые секунды: читать базу на каждый опрос незачем, правка вступает за это время.
QUOTA_CACHE_TTL_S = 5.0


class QuotaService:
    def __init__(
        self,
        repo: IInstanceSettingsRepository,
        *,
        ttl_s: float = QUOTA_CACHE_TTL_S,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._repo = repo
        self._ttl = ttl_s
        self._monotonic = monotonic
        self._cached: tuple[float, QuotaSettings] | None = None

    async def settings(self) -> QuotaSettings:
        now = self._monotonic()
        if self._cached is None or now - self._cached[0] >= self._ttl:
            self._cached = (now, quota_settings_from(await self._repo.get_all()))
        return self._cached[1]

    async def current(self) -> QueueQuota | None:
        """Лимиты для выдачи задач; без единого лимита `None`, и выдача идёт по старому пути."""
        quota = (await self.settings()).to_queue_quota()
        if quota.max_running_per_user is None and quota.max_running_per_org is None and quota.max_timeout_s is None:
            return None
        return quota

    def forget(self) -> None:
        self._cached = None


class GetQuotasUC:
    def __init__(self, repo: IInstanceSettingsRepository) -> None:
        self._repo = repo

    async def execute(self, actor: Actor) -> QuotaSettings:
        require_admin(actor)
        return quota_settings_from(await self._repo.get_all())


class UpdateQuotasUC:
    def __init__(
        self, repo: IInstanceSettingsRepository, audit: IAuditLog, uow: IUnitOfWork, service: QuotaService
    ) -> None:
        self._repo = repo
        self._audit = audit
        self._uow = uow
        self._service = service

    async def execute(self, actor: Actor, new: QuotaSettings) -> QuotaSettings:
        """Полная замена: `None` у поля снимает лимит. Значения уже проверены самим `QuotaSettings`."""
        admin_id = require_admin(actor)
        checked = new
        before = quota_settings_from(await self._repo.get_all())
        pairs = (
            (KEY_USER_CONCURRENT, checked.user_concurrent),
            (KEY_ORG_CONCURRENT, checked.org_concurrent),
            (KEY_MAX_DURATION_S, checked.max_duration_s),
        )
        async with self._uow.begin():
            for key, value in pairs:
                if value is None:
                    await self._repo.delete(key)
                else:
                    await self._repo.set(key, value, source=SOURCE_ADMIN)
            if checked != before:
                await self._audit.record(
                    "settings.quotas_update",
                    actor_id=admin_id,
                    details={
                        "before": _fields(before),
                        "after": _fields(checked),
                    },
                )
        self._service.forget()
        return checked


def _fields(quotas: QuotaSettings) -> dict[str, int | None]:
    return {
        "user_concurrent": quotas.user_concurrent,
        "org_concurrent": quotas.org_concurrent,
        "max_duration_s": quotas.max_duration_s,
    }
