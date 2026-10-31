"""Допуск по квотам: сборки и токены, место и участники, поведение при исчерпании, сброс периода."""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from hse_doc_studio.core.jobs.quotas import QuotaOverride, QuotaOwnerKind, QuotaResource
from hse_doc_studio.core.quotas.errors import QuotaExceededError
from hse_doc_studio.core.quotas.kinds import QuotaKind
from hse_doc_studio.core.quotas.policy import LimitSource, QuotaState
from hse_doc_studio.core.quotas.protocols import ProjectOwner
from hse_doc_studio.use_cases.admin.ops_quotas import QuotaService
from hse_doc_studio.use_cases.quotas.gate import QuotaGate

from tests.fakes.identity import InMemoryInstanceSettingsRepository
from tests.fakes.job_quotas import InMemoryQuotaOverrides
from tests.fakes.quotas import InMemoryFootprint, InMemoryUsageCounters

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


async def _gate(
    values: dict[str, object], *overrides: QuotaOverride
) -> tuple[QuotaGate, InMemoryUsageCounters, InMemoryFootprint, Clock]:
    repo = InMemoryInstanceSettingsRepository()
    for key, value in values.items():
        await repo.set(key, value, source="admin")
    counters, footprint, clock = InMemoryUsageCounters(), InMemoryFootprint(), Clock(NOW)
    service = QuotaService(repo, InMemoryQuotaOverrides(*overrides), ttl_s=0)
    return QuotaGate(service, counters, footprint, clock=clock), counters, footprint, clock


async def test__admit__without_limits_everything_passes() -> None:
    gate, *_ = await _gate({})

    admission = await gate.admit(QuotaKind.builds, uuid4(), None)

    assert not admission.deprioritize
    assert admission.warning is None


async def test__admit_builds__exhausted_user_is_deprioritized_by_default() -> None:
    user = uuid4()
    gate, *_ = await _gate({"quota.builds.user": 2})
    await gate.charge(QuotaKind.builds, user, None, 2)

    admission = await gate.admit(QuotaKind.builds, user, None)

    assert admission.deprioritize
    assert admission.warning is not None
    assert admission.warning.state is QuotaState.exceeded


async def test__admit_builds__reject_mode_raises_with_numbers_and_reset_date() -> None:
    user = uuid4()
    gate, *_ = await _gate({"quota.builds.user": 2, "quota.on_exceed": "reject"})
    await gate.charge(QuotaKind.builds, user, None, 2)

    with pytest.raises(QuotaExceededError) as caught:
        await gate.admit(QuotaKind.builds, user, None)

    assert (caught.value.used, caught.value.limit) == (2, 2)
    assert caught.value.resets_at == datetime(2026, 12, 1, tzinfo=UTC)


async def test__admit_builds__warn_mode_lets_the_build_through_with_a_warning() -> None:
    user = uuid4()
    gate, *_ = await _gate({"quota.builds.user": 1, "quota.on_exceed": "warn"})
    await gate.charge(QuotaKind.builds, user, None)

    admission = await gate.admit(QuotaKind.builds, user, None)

    assert not admission.deprioritize
    assert admission.warning is not None


async def test__admit_tokens__deprioritize_mode_is_a_refusal_for_non_build_kinds() -> None:
    user = uuid4()
    gate, *_ = await _gate({"quota.ai_tokens_day.user": 100})
    await gate.charge(QuotaKind.ai_tokens_day, user, None, 100)

    with pytest.raises(QuotaExceededError) as caught:
        await gate.admit(QuotaKind.ai_tokens_day, user, None)

    assert caught.value.kind is QuotaKind.ai_tokens_day


async def test__admit__org_ceiling_blocks_a_member_who_is_under_their_own_limit() -> None:
    user, org = uuid4(), uuid4()
    gate, *_ = await _gate({"quota.builds.user": 100, "quota.builds.org": 3, "quota.on_exceed": "reject"})
    await gate.charge(QuotaKind.builds, uuid4(), org, 3)

    with pytest.raises(QuotaExceededError) as caught:
        await gate.admit(QuotaKind.builds, user, org)

    assert caught.value.scope.value == "org"


async def test__admit__user_override_beats_installation_default() -> None:
    user = uuid4()
    gate, *_ = await _gate(
        {"quota.builds.user": 1, "quota.on_exceed": "reject"},
        QuotaOverride(QuotaOwnerKind.user, user.hex, QuotaResource.builds_user, 10),
    )
    await gate.charge(QuotaKind.builds, user, None, 5)

    assert (await gate.admit(QuotaKind.builds, user, None)).warning is None


async def test__period_reset__new_month_starts_from_zero_and_old_rows_stay() -> None:
    user = uuid4()
    gate, counters, _, clock = await _gate({"quota.builds.user": 2, "quota.on_exceed": "reject"})
    await gate.charge(QuotaKind.builds, user, None, 2)
    clock.now = datetime(2026, 12, 1, 0, 0, 1, tzinfo=UTC)

    await gate.admit(QuotaKind.builds, user, None)

    assert counters.rows[(QuotaOwnerKind.user, str(user), QuotaKind.builds, date(2026, 11, 1))] == 2


async def test__charge__skips_non_counted_kinds_and_non_positive_amounts() -> None:
    user = uuid4()
    gate, counters, *_ = await _gate({})

    await gate.charge(QuotaKind.storage, user, None, 10)
    await gate.charge(QuotaKind.builds, user, None, 0)

    assert counters.rows == {}


async def test__storage_write__owner_limit_rejects_growth_but_allows_shrinking() -> None:
    owner, project = uuid4(), uuid4()
    gate, _, footprint, _ = await _gate({"quota.storage.user": 1000, "quota.on_exceed": "reject"})
    footprint.owners[project] = ProjectOwner(project, str(owner), None)
    footprint.storage[(QuotaOwnerKind.user, str(owner))] = 900

    await gate.check_storage_write(project, 100)
    await gate.check_storage_write(project, -500)
    with pytest.raises(QuotaExceededError) as caught:
        await gate.check_storage_write(project, 101)

    assert caught.value.kind is QuotaKind.storage
    assert caught.value.used == 900


async def test__storage_write__org_project_uses_the_org_total() -> None:
    org, project = uuid4(), uuid4()
    gate, _, footprint, _ = await _gate(
        {"quota.storage.user": 10},
        QuotaOverride(QuotaOwnerKind.org, str(org), QuotaResource.storage_org, 500),
    )
    footprint.owners[project] = ProjectOwner(project, None, str(org))
    footprint.storage[(QuotaOwnerKind.org, str(org))] = 400

    await gate.check_storage_write(project, 100)
    with pytest.raises(QuotaExceededError):
        await gate.check_storage_write(project, 101)


async def test__member_slot__limit_counts_existing_members() -> None:
    owner, project = uuid4(), uuid4()
    gate, _, footprint, _ = await _gate({"quota.members.user": 3, "quota.on_exceed": "reject"})
    footprint.owners[project] = ProjectOwner(project, str(owner), None)
    footprint.members[project] = 2

    await gate.ensure_member_slot(project)
    footprint.members[project] = 3
    with pytest.raises(QuotaExceededError):
        await gate.ensure_member_slot(project)


async def test__member_slot__unknown_project_and_no_limit_pass() -> None:
    gate, _, footprint, _ = await _gate({})
    project = uuid4()
    footprint.owners[project] = ProjectOwner(project, str(uuid4()), None)
    footprint.members[project] = 99

    await gate.ensure_member_slot(project)
    await gate.ensure_member_slot(uuid4())


async def test__assess_counted__reports_source_and_percent() -> None:
    user = uuid4()
    gate, *_ = await _gate({"quota.ai_tokens_month.user": 200})
    await gate.charge(QuotaKind.ai_tokens_month, user, None, 170)

    (line,) = await gate.assess_counted(QuotaKind.ai_tokens_month, user, None)

    assert (line.used, line.limit, line.percent) == (170, 200, 85)
    assert line.source is LimitSource.installation
    assert line.state is QuotaState.warning
