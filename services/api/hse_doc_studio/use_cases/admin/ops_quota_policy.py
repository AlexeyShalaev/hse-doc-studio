"""Квоты по видам ресурсов в админке: умолчания установки, переопределения, использование и сброс периода."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.entities import User
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.protocols import IAuditLog, IInstanceSettingsRepository, IUserRepository
from hse_doc_studio.core.jobs.quotas import (
    IQuotaOverrideRepository,
    QuotaOverride,
    QuotaOwnerKind,
    QuotaResource,
    user_key,
)
from hse_doc_studio.core.orgs.protocols import IOrgRepository
from hse_doc_studio.core.quotas.kinds import KIND_SPECS, QuotaKind, QuotaScope
from hse_doc_studio.core.quotas.policy import (
    KEY_ON_EXCEED,
    KEY_WARN_PERCENT,
    MAX_LIMIT,
    QuotaPolicy,
    QuotaPolicyError,
    limit_key,
    policy_from,
)
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.admin.ops_quotas import QuotaService
from hse_doc_studio.use_cases.admin.users import require_admin
from hse_doc_studio.use_cases.identity.auth_settings import SOURCE_ADMIN
from hse_doc_studio.use_cases.quotas.gate import QuotaGate
from hse_doc_studio.use_cases.quotas.usage import OwnerUsage

SUMMARY_TOP = 5


class GetQuotaPolicyUC:
    def __init__(self, repo: IInstanceSettingsRepository) -> None:
        self._repo = repo

    async def execute(self, actor: Actor) -> QuotaPolicy:
        require_admin(actor)
        return policy_from(await self._repo.get_all())


def _policy_fields(policy: QuotaPolicy) -> dict[str, object]:
    fields: dict[str, object] = {"warn_percent": policy.warn_percent, "on_exceed": policy.on_exceed.value}
    for kind in KIND_SPECS:
        for scope in QuotaScope:
            fields[limit_key(kind, scope)] = policy.default(kind, scope)
    return fields


class UpdateQuotaPolicyUC:
    def __init__(
        self, repo: IInstanceSettingsRepository, audit: IAuditLog, uow: IUnitOfWork, service: QuotaService
    ) -> None:
        self._repo = repo
        self._audit = audit
        self._uow = uow
        self._service = service

    async def execute(self, actor: Actor, new: QuotaPolicy) -> QuotaPolicy:
        """Полная замена: отсутствующее значение снимает умолчание. Диапазоны проверил сам `QuotaPolicy`."""
        admin_id = require_admin(actor)
        before = policy_from(await self._repo.get_all())
        async with self._uow.begin():
            for kind in KIND_SPECS:
                for scope in QuotaScope:
                    value = new.default(kind, scope)
                    if value is None:
                        await self._repo.delete(limit_key(kind, scope))
                    else:
                        await self._repo.set(limit_key(kind, scope), value, source=SOURCE_ADMIN)
            await self._repo.set(KEY_WARN_PERCENT, new.warn_percent, source=SOURCE_ADMIN)
            await self._repo.set(KEY_ON_EXCEED, new.on_exceed.value, source=SOURCE_ADMIN)
            if _policy_fields(before) != _policy_fields(new):
                await self._audit.record(
                    "settings.quota_policy_update",
                    actor_id=admin_id,
                    details={"before": _policy_fields(before), "after": _policy_fields(new)},
                )
        self._service.forget()
        return new


@dataclass(frozen=True)
class OverrideView:
    owner_kind: QuotaOwnerKind
    owner_id: str
    owner_name: str
    resource: QuotaResource
    hard_limit: int


# Ограничения по виду владельца: пользователю доступны только значения «на человека».
_USER_RESOURCES = frozenset(
    {QuotaResource.concurrent_user, QuotaResource.max_duration_s} | {spec.user_resource for spec in KIND_SPECS.values()}
)


class OverrideRules:
    @staticmethod
    def check(owner_kind: QuotaOwnerKind, resource: QuotaResource, value: int) -> None:
        if not 1 <= value <= MAX_LIMIT:
            raise QuotaPolicyError("hard_limit")
        if owner_kind is QuotaOwnerKind.user and resource not in _USER_RESOURCES:
            raise QuotaPolicyError("resource")


class _Names:
    def __init__(self, users: IUserRepository, orgs: IOrgRepository) -> None:
        self._users = users
        self._orgs = orgs

    async def name_of(self, owner_kind: QuotaOwnerKind, owner_id: str) -> str | None:
        """Подпись владельца для админки; `None`, если владельца в установке нет."""
        if owner_kind is QuotaOwnerKind.org:
            org = await self._orgs.get(owner_id) or await self._orgs.get_by_slug(owner_id)
            return org.name if org is not None else None
        user = await self._find_user(owner_id)
        return (user.name or user.email) if user is not None else None

    async def _find_user(self, owner_id: str) -> User | None:
        """Id человека в счётчиках с дефисами, в базе может быть без них: пробуем оба написания."""
        key = user_key(owner_id)
        for form in (owner_id, key.hex, str(key)) if key is not None else (owner_id,):
            if (user := await self._users.get(form)) is not None:
                return user
        return None

    async def canonical_id(self, owner_kind: QuotaOwnerKind, owner_id: str) -> str | None:
        if owner_kind is QuotaOwnerKind.org:
            org = await self._orgs.get(owner_id) or await self._orgs.get_by_slug(owner_id)
            return org.id if org is not None else None
        user = await self._find_user(owner_id)
        return user.id if user is not None else None


class ListQuotaOverridesUC:
    def __init__(self, overrides: IQuotaOverrideRepository, users: IUserRepository, orgs: IOrgRepository) -> None:
        self._overrides = overrides
        self._names = _Names(users, orgs)

    async def execute(self, actor: Actor) -> list[OverrideView]:
        require_admin(actor)
        items = sorted(
            await self._overrides.list_all(), key=lambda i: (i.owner_kind.value, i.owner_id, i.resource.value)
        )
        return [
            OverrideView(
                i.owner_kind,
                i.owner_id,
                await self._names.name_of(i.owner_kind, i.owner_id) or i.owner_id,
                i.resource,
                i.hard_limit,
            )
            for i in items
        ]


class SetQuotaOverrideUC:
    def __init__(
        self,
        overrides: IQuotaOverrideRepository,
        users: IUserRepository,
        orgs: IOrgRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
        service: QuotaService,
    ) -> None:
        self._overrides = overrides
        self._names = _Names(users, orgs)
        self._audit = audit
        self._uow = uow
        self._service = service

    async def execute(
        self, actor: Actor, owner_kind: QuotaOwnerKind, owner_id: str, resource: QuotaResource, value: int
    ) -> OverrideView:
        admin_id = require_admin(actor)
        OverrideRules.check(owner_kind, resource, value)
        canonical = await self._names.canonical_id(owner_kind, owner_id)
        if canonical is None:
            raise IdentityError(IdentityErrorCode.not_found)
        async with self._uow.begin():
            await self._overrides.set(QuotaOverride(owner_kind, canonical, resource, value))
            await self._audit.record(
                "quota.override_set",
                actor_id=admin_id,
                target=f"{owner_kind.value}:{canonical}",
                details={"resource": resource.value, "hard_limit": value},
            )
        self._service.forget()
        name = await self._names.name_of(owner_kind, canonical) or canonical
        return OverrideView(owner_kind, canonical, name, resource, value)


class DeleteQuotaOverrideUC:
    def __init__(
        self, overrides: IQuotaOverrideRepository, audit: IAuditLog, uow: IUnitOfWork, service: QuotaService
    ) -> None:
        self._overrides = overrides
        self._audit = audit
        self._uow = uow
        self._service = service

    async def execute(self, actor: Actor, owner_kind: QuotaOwnerKind, owner_id: str, resource: QuotaResource) -> None:
        admin_id = require_admin(actor)
        async with self._uow.begin():
            await self._overrides.delete(owner_kind, owner_id, resource)
            await self._audit.record(
                "quota.override_delete",
                actor_id=admin_id,
                target=f"{owner_kind.value}:{owner_id}",
                details={"resource": resource.value},
            )
        self._service.forget()


class AdminOwnerUsageUC:
    def __init__(self, gate: QuotaGate, users: IUserRepository, orgs: IOrgRepository) -> None:
        self._gate = gate
        self._names = _Names(users, orgs)

    async def execute(self, actor: Actor, owner_kind: QuotaOwnerKind, owner_id: str) -> OwnerUsage:
        require_admin(actor)
        canonical = await self._names.canonical_id(owner_kind, owner_id)
        if canonical is None:
            raise IdentityError(IdentityErrorCode.not_found)
        name = await self._names.name_of(owner_kind, canonical) or canonical
        if owner_kind is QuotaOwnerKind.org:
            return OwnerUsage(canonical, name, await self._gate.lines_for_org(canonical))
        try:
            uid = UUID(canonical)
        except ValueError as exc:
            raise IdentityError(IdentityErrorCode.not_found) from exc
        return OwnerUsage(canonical, name, await self._gate.lines_for_user(uid))


@dataclass(frozen=True)
class TopConsumer:
    user_id: str
    name: str
    used: int


@dataclass(frozen=True)
class UsageSummary:
    totals: dict[QuotaKind, int]
    top: dict[QuotaKind, list[TopConsumer]]


class AdminUsageSummaryUC:
    def __init__(self, gate: QuotaGate, users: IUserRepository, orgs: IOrgRepository) -> None:
        self._gate = gate
        self._names = _Names(users, orgs)

    async def execute(self, actor: Actor) -> UsageSummary:
        require_admin(actor)
        top: dict[QuotaKind, list[TopConsumer]] = {}
        for kind in (QuotaKind.builds, QuotaKind.ai_tokens_month):
            top[kind] = [
                TopConsumer(uid, await self._names.name_of(QuotaOwnerKind.user, uid) or uid, used)
                for uid, used in await self._gate.top_users(kind, SUMMARY_TOP)
            ]
        return UsageSummary(await self._gate.installation_totals(), top)


class ResetUsageUC:
    def __init__(
        self, gate: QuotaGate, users: IUserRepository, orgs: IOrgRepository, audit: IAuditLog, uow: IUnitOfWork
    ) -> None:
        self._gate = gate
        self._names = _Names(users, orgs)
        self._audit = audit
        self._uow = uow

    async def execute(self, actor: Actor, owner_kind: QuotaOwnerKind, owner_id: str, kind: QuotaKind) -> bool:
        """Обнуляет расход за текущий период. `False`, если счётчика не было или вид без счётчика."""
        admin_id = require_admin(actor)
        canonical = await self._names.canonical_id(owner_kind, owner_id)
        if canonical is None:
            raise IdentityError(IdentityErrorCode.not_found)
        async with self._uow.begin():
            done = await self._gate.reset(owner_kind, canonical, kind)
            if done:
                await self._audit.record(
                    "usage.reset",
                    actor_id=admin_id,
                    target=f"{owner_kind.value}:{canonical}",
                    details={"resource": kind.value},
                )
        return done
