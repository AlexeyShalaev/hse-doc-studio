"""Допуск по квотам: сборки и токены (счётчики), место и участники (по таблицам проектов)."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.jobs.quotas import QuotaOwnerKind, org_key, user_key
from hse_doc_studio.core.quotas.errors import QuotaExceededError
from hse_doc_studio.core.quotas.kinds import KIND_SPECS, QuotaKind, QuotaScope, period_end, period_start
from hse_doc_studio.core.quotas.policy import (
    Assessment,
    OnExceed,
    QuotaState,
    ResolvedLimit,
    resolve_org_limit,
    resolve_user_limit,
    state_of,
)
from hse_doc_studio.core.quotas.protocols import IOwnerFootprint, IUsageCounters, ProjectOwner
from hse_doc_studio.use_cases.admin.ops_quotas import QuotaService, QuotaSnapshot


@dataclass(frozen=True)
class Admission:
    """Итог допуска: `deprioritize` ставит сборку в конец очереди, `warning` несёт превышение."""

    deprioritize: bool = False
    warning: Assessment | None = None


class QuotaGate:
    def __init__(
        self, quotas: QuotaService, counters: IUsageCounters, footprint: IOwnerFootprint, *, clock: Clock = utc_now
    ) -> None:
        self._quotas = quotas
        self._counters = counters
        self._footprint = footprint
        self._clock = clock

    # --- оценка ---

    async def assess_counted(self, kind: QuotaKind, user_id: UUID | None, org_id: UUID | None) -> list[Assessment]:
        """Оценки по человеку и по организации проекта для вида со счётчиком."""
        snap = await self._quotas.snapshot()
        out: list[Assessment] = []
        if user_id is not None:
            out.append(await self._assess_user(kind, snap, user_id, org_id))
        if org_id is not None:
            out.append(await self._assess_org(kind, snap, org_id, str(org_id)))
        return out

    async def _assess_user(
        self, kind: QuotaKind, snap: QuotaSnapshot, user_id: UUID, org_id: UUID | None, *, owner_id: str | None = None
    ) -> Assessment:
        limit = resolve_user_limit(kind, user_id, org_id, snap.policy, snap.index)
        key = owner_id or str(user_id)
        used = await self._used(kind, QuotaOwnerKind.user, key)
        return self._assessment(kind, QuotaScope.user, key, used, limit, snap)

    async def _assess_org(self, kind: QuotaKind, snap: QuotaSnapshot, org_id: UUID, raw_id: str) -> Assessment:
        limit = resolve_org_limit(kind, org_id, snap.policy, snap.index)
        used = await self._used(kind, QuotaOwnerKind.org, raw_id)
        return self._assessment(kind, QuotaScope.org, raw_id, used, limit, snap)

    def _assessment(
        self,
        kind: QuotaKind,
        scope: QuotaScope,
        owner_id: str,
        used: int,
        limit: ResolvedLimit | None,
        snap: QuotaSnapshot,
    ) -> Assessment:
        hard = limit.hard if limit is not None else None
        return Assessment(
            kind=kind,
            scope=scope,
            owner_id=owner_id,
            used=used,
            limit=hard,
            source=limit.source if limit is not None else None,
            state=state_of(used, hard, snap.policy.warn_percent),
            resets_at=period_end(KIND_SPECS[kind].period, self._clock()),
        )

    async def _used(self, kind: QuotaKind, owner_kind: QuotaOwnerKind, owner_id: str) -> int:
        spec = KIND_SPECS[kind]
        if spec.counted:
            start = period_start(spec.period, self._clock())
            assert start is not None  # noqa: S101 — у вида со счётчиком период есть
            return await self._counters.get(owner_kind, _counter_owner(owner_kind, owner_id), kind, start)
        if kind is QuotaKind.storage:
            return await self._footprint.storage_bytes(owner_kind, owner_id)
        return await self._footprint.max_members(owner_kind, owner_id)

    # --- допуск ---

    async def admit(self, kind: QuotaKind, user_id: UUID | None, org_id: UUID | None, amount: int = 1) -> Admission:
        """Пропускает расход или отказывает по политике установки (раздел 0, Q7)."""
        over = next(
            (item for item in await self.assess_counted(kind, user_id, org_id) if item.would_exceed(amount)), None
        )
        if over is None:
            return Admission()
        return await self._on_exceed(kind, over)

    async def _on_exceed(self, kind: QuotaKind, over: Assessment) -> Admission:
        mode = (await self._quotas.snapshot()).policy.on_exceed
        if mode is OnExceed.warn:
            return Admission(warning=over)
        if mode is OnExceed.deprioritize and kind is QuotaKind.builds:
            return Admission(deprioritize=True, warning=over)
        assert over.limit is not None  # noqa: S101 — превысить можно только заданный предел
        raise QuotaExceededError(kind, over.scope, over.used, over.limit, over.resets_at, over.owner_id)

    async def charge(self, kind: QuotaKind, user_id: UUID | None, org_id: UUID | None, amount: int = 1) -> None:
        """Прибавляет расход человеку и организации проекта; ноль и меньше игнорируются."""
        spec = KIND_SPECS[kind]
        start = period_start(spec.period, self._clock())
        if amount <= 0 or not spec.counted or start is None:
            return
        if user_id is not None:
            await self._counters.add(QuotaOwnerKind.user, str(user_id), kind, start, amount)
        if org_id is not None:
            await self._counters.add(QuotaOwnerKind.org, str(org_id), kind, start, amount)

    # --- место и участники ---

    async def _owner_assessment(self, kind: QuotaKind, owner: ProjectOwner) -> Assessment | None:
        snap = await self._quotas.snapshot()
        if owner.org_id is not None:
            return await self._assess_org(kind, snap, org_key(owner.org_id), owner.org_id)
        if owner.user_id is not None and (uid := user_key(owner.user_id)) is not None:
            return await self._assess_user(kind, snap, uid, None, owner_id=owner.user_id)
        return None

    async def check_storage_write(self, project_id: UUID, delta_bytes: int) -> None:
        """Запись, не увеличивающая размер, проходит всегда: удалять можно и сверх предела."""
        if delta_bytes <= 0:
            return
        await self._check_owner(QuotaKind.storage, project_id, delta_bytes)

    async def ensure_member_slot(self, project_id: UUID) -> None:
        owner = await self._footprint.project_owner(project_id)
        if owner is None:
            return
        assessment = await self._owner_assessment(QuotaKind.members, owner)
        if assessment is None or assessment.limit is None:
            return
        used = await self._footprint.member_count(project_id)
        await self._raise_if_over(QuotaKind.members, assessment, used, 1)

    async def _check_owner(self, kind: QuotaKind, project_id: UUID, amount: int) -> None:
        owner = await self._footprint.project_owner(project_id)
        if owner is None:
            return
        assessment = await self._owner_assessment(kind, owner)
        if assessment is None or assessment.limit is None:
            return
        await self._raise_if_over(kind, assessment, assessment.used, amount)

    async def _raise_if_over(self, kind: QuotaKind, assessment: Assessment, used: int, amount: int) -> None:
        if assessment.limit is None or used + amount <= assessment.limit:
            return
        over = Assessment(
            kind, assessment.scope, assessment.owner_id, used, assessment.limit, assessment.source,
            QuotaState.exceeded, assessment.resets_at,
        )  # fmt: skip
        mode = (await self._quotas.snapshot()).policy.on_exceed
        if mode is OnExceed.warn:
            return
        raise QuotaExceededError(kind, over.scope, used, assessment.limit, None, over.owner_id)


def _counter_owner(owner_kind: QuotaOwnerKind, owner_id: str) -> str:
    """Организация в счётчиках всегда UUID-ключ: `jobs.org_id` и slug-id сходятся на одной строке."""
    return str(org_key(owner_id)) if owner_kind is QuotaOwnerKind.org else owner_id
