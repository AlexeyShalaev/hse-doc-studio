"""Репозиторий участников с квотой: новый участник занимает слот, смена роли существующего нет."""

from __future__ import annotations

from uuid import uuid4

import pytest
from hse_doc_studio.core.access.entities import Role
from hse_doc_studio.core.access.repositories import ProjectMemberGrant
from hse_doc_studio.core.quotas.errors import QuotaExceededError
from hse_doc_studio.core.quotas.protocols import ProjectOwner
from hse_doc_studio.use_cases.admin.ops_quotas import QuotaService
from hse_doc_studio.use_cases.quotas.gate import QuotaGate
from hse_doc_studio.use_cases.quotas.members_guard import QuotaGuardedMemberRepository

from tests.fakes.identity import InMemoryInstanceSettingsRepository
from tests.fakes.job_quotas import InMemoryQuotaOverrides
from tests.fakes.quotas import InMemoryFootprint, InMemoryUsageCounters


class _Inner:
    def __init__(self) -> None:
        self.set_calls: list[tuple[object, ProjectMemberGrant]] = []

    async def get_ownership(self, project_id: object) -> None:
        return None

    async def set_member(self, project_id: object, grant: ProjectMemberGrant) -> None:
        self.set_calls.append((project_id, grant))

    async def remove_member(self, project_id: object, principal_kind: str, principal_id: str) -> bool:
        return True


def _grant(user: str) -> ProjectMemberGrant:
    return ProjectMemberGrant(principal_kind="user", principal_id=user, role=Role.editor)


async def _rig(limit: int) -> tuple[QuotaGuardedMemberRepository, _Inner, InMemoryFootprint, object]:
    repo = InMemoryInstanceSettingsRepository()
    await repo.set("quota.members.user", limit, source="admin")
    await repo.set("quota.on_exceed", "reject", source="admin")
    footprint = InMemoryFootprint()
    gate = QuotaGate(QuotaService(repo, InMemoryQuotaOverrides(), ttl_s=0), InMemoryUsageCounters(), footprint)
    project = uuid4()
    footprint.owners[project] = ProjectOwner(project, str(uuid4()), None)
    inner = _Inner()
    return QuotaGuardedMemberRepository(inner, gate), inner, footprint, project  # type: ignore[arg-type]


async def test__set_member__new_member_over_limit_is_refused_and_nothing_is_written() -> None:
    guarded, inner, footprint, project = await _rig(2)
    footprint.members[project] = 2  # type: ignore[index]

    with pytest.raises(QuotaExceededError):
        await guarded.set_member(project, _grant("newbie"))  # type: ignore[arg-type]

    assert inner.set_calls == []


async def test__set_member__existing_member_role_change_does_not_take_a_slot() -> None:
    guarded, inner, footprint, project = await _rig(2)
    footprint.members[project] = 2  # type: ignore[index]
    footprint.existing.add((project, "user", "anna"))  # type: ignore[arg-type]

    await guarded.set_member(project, _grant("anna"))  # type: ignore[arg-type]

    assert len(inner.set_calls) == 1


async def test__set_member__under_limit_passes() -> None:
    guarded, inner, footprint, project = await _rig(3)
    footprint.members[project] = 2  # type: ignore[index]

    await guarded.set_member(project, _grant("newbie"))  # type: ignore[arg-type]

    assert len(inner.set_calls) == 1
