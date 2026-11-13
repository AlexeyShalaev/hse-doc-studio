"""Сроки контрольных точек (docs/design/signing-route.md, 16.8): тело `PUT .../deadline`, ответ и срок в списке."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from hse_doc_studio.api.schemas.common import StrictModel
from hse_doc_studio.core.checkpoint_deadlines import CheckpointDeadline as CheckpointDeadlineView
from hse_doc_studio.core.checkpoint_deadlines import NextDeadline as NextDeadlineView

DeadlineStateName = Literal["none", "upcoming", "soon", "today", "packaged", "overdue"]


class SetCheckpointDeadlineRequest(StrictModel):
    # ISO 8601 с поясом («2026-11-15T23:59:00+03:00»); null снимает срок. Разбирает сценарий: 400 `bad_deadline`.
    deadline: str | None


class CheckpointDeadline(StrictModel):
    profile_id: str
    deadline: datetime | None
    state: DeadlineStateName
    # Последняя сборка пакета точки к сроку: за 14 дней до срока и не позже него.
    packaged_at: datetime | None

    @classmethod
    def of(cls, view: CheckpointDeadlineView) -> CheckpointDeadline:
        return cls(
            profile_id=view.profile_id, deadline=view.deadline, state=view.state.value, packaged_at=view.packaged_at
        )


class NextDeadline(StrictModel):
    """Ближайший срок проекта в списке проектов: точка с названием из пака."""

    profile_id: str
    name: dict[str, str]
    deadline: datetime
    state: DeadlineStateName

    @classmethod
    def of(cls, view: NextDeadlineView | None) -> NextDeadline | None:
        if view is None:
            return None
        return cls(profile_id=view.profile_id, name=dict(view.name), deadline=view.deadline, state=view.state.value)
