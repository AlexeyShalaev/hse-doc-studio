"""Срок контрольной точки: запись в проект, аудит, состояние по журналу сдачи (signing-route.md, 16.6 и 16.8)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.catalog import PackSubmissionConfig, SubmissionProfile
from hse_doc_studio.core.checkpoint_deadlines import BadDeadlineError, DeadlineState
from hse_doc_studio.core.entities import PackSubmissionRecord, Project
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.infra.persistence.project import JsonProjectRepository
from hse_doc_studio.use_cases.submission.get_submission_profiles import (
    GetSubmissionProfilesInput,
    GetSubmissionProfilesUC,
)
from hse_doc_studio.use_cases.submission.next_deadlines import ProjectNextDeadlinesUC
from hse_doc_studio.use_cases.submission.set_checkpoint_deadline import (
    SetCheckpointDeadlineInput,
    SetCheckpointDeadlineUC,
)

from tests.factories import make_project, make_template_version
from tests.fakes.submission import InMemoryPackSubmissionRepository

pytestmark = pytest.mark.unit

MSK = timezone(timedelta(hours=3))
TOPIC = "topic-approval"
FINAL = "final"


def _profile(profile_id: str, name: str, hint: dict[str, str] | None = None) -> SubmissionProfile:
    return SubmissionProfile(
        id=profile_id,
        name={"ru": name, "en": name},
        description={},
        items=(),
        extra_items=(),
        deadline_hint=hint,
    )


@dataclass
class FakeAudit:
    events: list[tuple[str, UUID | None, dict[str, object]]] = field(default_factory=list)

    async def record(self, action: str, *, project_id: UUID | None, details: Mapping[str, object]) -> None:
        self.events.append((action, project_id, dict(details)))


@dataclass
class World:
    project: Project
    projects: JsonProjectRepository
    submissions: InMemoryPackSubmissionRepository
    audit: FakeAudit
    set_uc: SetCheckpointDeadlineUC
    profiles_uc: GetSubmissionProfilesUC
    next_uc: ProjectNextDeadlinesUC

    def stored(self) -> Project:
        project = self.projects.get(self.project.folder)
        assert project is not None
        return project

    async def built(self, profile_id: str, at: datetime) -> None:
        await self.submissions.save(
            PackSubmissionRecord(
                id=uuid4(),
                project_folder=self.project.folder,
                profile_id=profile_id,
                created_at=at,
                doc_items=[],
                extra_items=[],
                output_path=self.project.folder / "submissions" / "p.zip",
            )
        )

    async def set(self, profile_id: str, deadline: str | None):  # noqa: ANN201 — вид ответа сценария
        return await self.set_uc.execute(SetCheckpointDeadlineInput(self.project.id, profile_id, deadline))


@pytest.fixture
def world(tmp_path: Path) -> World:
    version = replace(
        make_template_version(),
        pack_submission=PackSubmissionConfig(
            profiles=(
                _profile(TOPIC, "Заявка", {"ru": "В середине ноября", "en": "Mid-November"}),
                _profile(FINAL, "Итог"),
            )
        ),
    )
    templates = MagicMock()
    templates.get_version.return_value = version
    projects = JsonProjectRepository()
    project = make_project(folder=tmp_path)
    projects.save(project)
    index = MagicMock(spec=["list_known"])
    index.list_known.return_value = [tmp_path]
    submissions = InMemoryPackSubmissionRepository()
    audit = FakeAudit()
    return World(
        project=project,
        projects=projects,
        submissions=submissions,
        audit=audit,
        set_uc=SetCheckpointDeadlineUC(projects, index, templates, submissions, audit),
        profiles_uc=GetSubmissionProfilesUC(projects, index, templates, submissions),
        next_uc=ProjectNextDeadlinesUC(templates, submissions),
    )


def _soon() -> datetime:
    """Срок через два дня по Москве в 23:59: состояние «скоро» в любое время суток."""
    day = datetime.now(MSK).date() + timedelta(days=2)
    return datetime(day.year, day.month, day.day, 23, 59, tzinfo=MSK)


async def test__set_deadline__written_to_project_json_and_audited(world: World) -> None:
    deadline = _soon()

    view = await world.set(TOPIC, deadline.isoformat())

    assert (view.profile_id, view.deadline, view.state, view.packaged_at) == (TOPIC, deadline, DeadlineState.soon, None)
    assert world.stored().deadlines == {TOPIC: deadline}
    assert world.stored().deadlines[TOPIC].utcoffset() == timedelta(hours=3)
    assert world.audit.events == [
        (
            "project.deadline",
            world.project.id,
            {"profile_id": TOPIC, "previous": None, "deadline": deadline.isoformat()},
        )
    ]


async def test__set_deadline__same_moment_in_another_zone__nothing_written(world: World) -> None:
    deadline = _soon()
    await world.set(TOPIC, deadline.isoformat())
    before = world.stored().updated_at

    await world.set(TOPIC, deadline.astimezone(UTC).isoformat())

    assert len(world.audit.events) == 1
    assert world.stored().updated_at == before


async def test__set_deadline__null__clears_and_audits_the_previous(world: World) -> None:
    deadline = _soon()
    await world.set(TOPIC, deadline.isoformat())
    await world.set(FINAL, "2027-06-01T23:59:00+03:00")

    view = await world.set(TOPIC, None)

    assert (view.deadline, view.state) == (None, DeadlineState.none)
    assert list(world.stored().deadlines) == [FINAL]
    assert world.audit.events[-1][2] == {"profile_id": TOPIC, "previous": deadline.isoformat(), "deadline": None}


async def test__set_deadline__unknown_checkpoint__not_found(world: World) -> None:
    with pytest.raises(NotFoundError):
        await world.set("defence", _soon().isoformat())

    assert world.stored().deadlines == {}


async def test__set_deadline__no_zone__bad_deadline_and_nothing_written(world: World) -> None:
    with pytest.raises(BadDeadlineError):
        await world.set(TOPIC, "2026-11-15T23:59:00")

    assert world.stored().deadlines == {}
    assert world.audit.events == []


async def test__set_deadline__in_the_past_with_a_package_to_it__packaged(world: World) -> None:
    await world.built(TOPIC, datetime(2025, 11, 14, 18, 0, tzinfo=MSK))
    await world.built(FINAL, datetime(2025, 11, 14, 19, 0, tzinfo=MSK))

    packaged = await world.set(TOPIC, "2025-11-15T23:59:00+03:00")
    overdue = await world.set(FINAL, "2025-11-01T23:59:00+03:00")

    assert (packaged.state, packaged.packaged_at) == (DeadlineState.packaged, datetime(2025, 11, 14, 18, tzinfo=MSK))
    assert (overdue.state, overdue.packaged_at) == (DeadlineState.overdue, None)


async def test__profiles__deadline_state_hint_and_packaged_at_for_each_checkpoint(world: World) -> None:
    deadline = _soon()
    await world.set(TOPIC, deadline.isoformat())
    await world.built(TOPIC, datetime.now(UTC) - timedelta(hours=1))

    out = await world.profiles_uc.execute(GetSubmissionProfilesInput(world.project.id))

    topic, final = out.deadlines[TOPIC], out.deadlines[FINAL]
    assert (topic.deadline, topic.state) == (deadline, DeadlineState.soon)
    assert topic.packaged_at is not None
    assert (final.deadline, final.state, final.packaged_at) == (None, DeadlineState.none, None)
    assert out.profiles[0].deadline_hint == {"ru": "В середине ноября", "en": "Mid-November"}


async def test__next_deadlines__only_projects_with_deadlines_of_known_checkpoints(world: World) -> None:
    deadline = _soon()
    await world.set(TOPIC, deadline.isoformat())
    gone = replace(world.stored(), id=uuid4(), deadlines={"removed-in-new-version": deadline})
    empty = replace(world.stored(), id=uuid4(), deadlines={})

    found = await world.next_uc.execute([world.stored(), gone, empty])

    assert list(found) == [world.project.id]
    assert (found[world.project.id].profile_id, found[world.project.id].state) == (TOPIC, DeadlineState.soon)
    assert dict(found[world.project.id].name) == {"ru": "Заявка", "en": "Заявка"}
