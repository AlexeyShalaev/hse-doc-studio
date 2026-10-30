"""Квоты задач установки: чтение для очереди (с короткой памятью) и правка админом."""

from __future__ import annotations

import time
from collections.abc import Callable
from uuid import UUID

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.protocols import IAuditLog, IInstanceSettingsRepository
from hse_doc_studio.core.jobs.quotas import (
    KEY_MAX_DURATION_S,
    KEY_ORG_CONCURRENT,
    KEY_USER_CONCURRENT,
    IQuotaOverrideRepository,
    QuotaOverride,
    QuotaSettings,
    duration_cap,
    overrides_to_queue_quota,
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
        overrides: IQuotaOverrideRepository | None = None,
        *,
        ttl_s: float = QUOTA_CACHE_TTL_S,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._repo = repo
        self._overrides = overrides
        self._ttl = ttl_s
        self._monotonic = monotonic
        self._cached: tuple[float, QuotaSettings, tuple[QuotaOverride, ...]] | None = None

    async def _load(self) -> tuple[QuotaSettings, tuple[QuotaOverride, ...]]:
        now = self._monotonic()
        if self._cached is None or now - self._cached[0] >= self._ttl:
            overrides = tuple(await self._overrides.list_all()) if self._overrides is not None else ()
            self._cached = (now, quota_settings_from(await self._repo.get_all()), overrides)
        return self._cached[1], self._cached[2]

    async def settings(self) -> QuotaSettings:
        return (await self._load())[0]

    async def current(self) -> QueueQuota | None:
        """Лимиты для выдачи задач; без единого лимита `None`, и выдача идёт по старому пути."""
        settings, overrides = await self._load()
        quota = overrides_to_queue_quota(settings.to_queue_quota(), overrides)
        return None if quota.is_unlimited else quota

    async def max_duration_s(self, user_id: UUID, org_id: UUID | None) -> float | None:
        settings, overrides = await self._load()
        cap = duration_cap(settings.max_duration_s, overrides, user_id, org_id)
        return float(cap) if cap is not None else None

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
