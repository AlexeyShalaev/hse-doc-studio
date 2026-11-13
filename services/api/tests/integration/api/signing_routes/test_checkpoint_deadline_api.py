"""Срок контрольной точки на настоящем сервере (docs/design/signing-route.md, 16.3, 16.6 и 16.8).

Права те же, что у сборки пакета (`SUBMISSION_CREATE`), срок уходит копией в каталог проектов, список проектов
показывает ближайший срок, «пакет собран» прячет прошедший срок из списка, правка пишет аудит `project.deadline`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.infra.db.orm.submission import SubmissionRow
from hse_doc_studio.infra.projects.catalog_sync import MirroringProjectRepository
from sqlalchemy import text

from tests.integration.api.signing_routes.stand import TOPIC, Project, Stand, make_project, person
from tests.integration.api.signing_routes.watch_stand import container, in_app

pytestmark = [pytest.mark.pg, pytest.mark.timeout(240)]

MSK = timezone(timedelta(hours=3))
TOPIC_NAME = {"ru": "Заявка на тему КП (SmartLMS)", "en": "Topic application (SmartLMS)"}


def _in_days(days: int) -> datetime:
    day = datetime.now(MSK).date() + timedelta(days=days)
    return datetime(day.year, day.month, day.day, 23, 59, tzinfo=MSK)


def _put(project: Project, who: Any, deadline: str | None, profile_id: str = TOPIC) -> Any:
    path = f"{project.base}/submissions/profiles/{profile_id}/deadline"
    return project.call(who, "PUT", path, json={"deadline": deadline})


def _mirrored(stand: Stand) -> None:
    """Дождаться копии в каталог: репозиторий проектов пишет её задачей после сохранения."""

    async def wait() -> None:
        repo = await container(stand).get(MirroringProjectRepository)
        await repo.drain()

    in_app(stand, wait)


async def _copy(stand: Stand, project: Project) -> Any:
    async with stand.sessions.use() as db:
        row = await db.execute(
            text("SELECT deadlines, deadlines IS NULL FROM projects WHERE id = :id"), {"id": UUID(project.id)}
        )
        return row.one()


def _listed(project: Project, who: Any) -> dict[str, Any]:
    page = project.call(who, "GET", "/api/v1/projects")
    assert page.status_code == 200, page.text
    return next(item for item in page.json()["items"] if item["id"] == project.id)


async def test__deadline__rights_copy_list_and_audit(stand: Stand) -> None:
    owner = await person(stand, "Автор")
    editor = await person(stand, "Соавтор")
    reviewer = await person(stand, "Научрук")
    outsider = await person(stand, "Посторонний")
    project = make_project(stand, owner)
    await project.member(editor, "editor", None)
    await project.member(reviewer, "reviewer", "supervisor")
    deadline = _in_days(2)

    by_owner = _put(project, owner, deadline.isoformat())
    by_editor = _put(project, editor, "2027-06-01T23:59:00+03:00", "final")
    by_reviewer = _put(project, reviewer, deadline.isoformat())
    by_outsider = _put(project, outsider, deadline.isoformat())
    _mirrored(stand)
    copy, _ = await _copy(stand, project)

    assert by_owner.status_code == 200, by_owner.text
    assert by_owner.json() == {
        "profile_id": TOPIC,
        "deadline": deadline.isoformat(),
        "state": "soon",
        "packaged_at": None,
    }
    assert by_editor.status_code == 200, by_editor.text
    assert by_reviewer.status_code == 403
    assert by_outsider.status_code == 404
    final_name = copy["final"]["name"]
    assert copy == {
        TOPIC: {"deadline": deadline.isoformat(), "name": TOPIC_NAME},
        "final": {"deadline": "2027-06-01T23:59:00+03:00", "name": final_name},
    }
    expected = {"profile_id": TOPIC, "name": TOPIC_NAME, "deadline": deadline.isoformat(), "state": "soon"}
    # Руководитель видит ту же пометку у проекта студента, где он участник.
    assert _listed(project, owner)["next_deadline"] == expected
    assert _listed(project, reviewer)["next_deadline"] == expected
    # Рецензент срок видит на точке, хоть и не ставит его.
    profiles = project.call(reviewer, "GET", f"{project.base}/submissions/profiles").json()
    assert next(p for p in profiles if p["id"] == TOPIC)["deadline_state"] == "soon"

    audit = stand.admin().get("/api/admin/audit", params={"target": project.id, "limit": 200}).json()
    events = [e for e in audit["items"] if e["action"] == "project.deadline"]
    assert sorted(
        (e["actor_id"], e["details"]["profile_id"], e["details"]["previous"], e["details"]["deadline"]) for e in events
    ) == sorted(
        [
            (owner.id, TOPIC, None, deadline.isoformat()),
            (editor.id, "final", None, "2027-06-01T23:59:00+03:00"),
        ]
    )


async def test__deadline__past_deadline_overdue_until_packaged_and_cleared_copy_is_null(stand: Stand) -> None:
    owner = await person(stand, "Автор")
    project = make_project(stand, owner)
    copy_before = await _copy(stand, project)
    deadline = datetime.now(UTC) - timedelta(days=2)

    put = _put(project, owner, deadline.isoformat())
    _mirrored(stand)
    overdue = _listed(project, owner)["next_deadline"]
    async with stand.sessions.use() as db:
        db.add(
            SubmissionRow(
                id=uuid4(),
                project_id=UUID(project.id),
                profile_id=TOPIC,
                created_at=deadline - timedelta(days=1),
                output_path="submissions/p.zip",
            )
        )
    packaged = project.call(owner, "GET", f"{project.base}/submissions/profiles").json()
    hidden = _listed(project, owner)["next_deadline"]
    cleared = _put(project, owner, None)
    _mirrored(stand)

    # У нового проекта срока нет: колонка пустая, как после миграции.
    assert copy_before == (None, True)
    assert (put.status_code, put.json()["state"]) == (200, "overdue")
    assert overdue is not None
    assert (overdue["profile_id"], overdue["state"]) == (TOPIC, "overdue")
    topic = next(p for p in packaged if p["id"] == TOPIC)
    assert topic["deadline_state"] == "packaged"
    assert topic["packaged_at"] is not None
    assert hidden is None
    assert cleared.status_code == 200, cleared.text
    # Снятый срок даёт SQL NULL, а не JSON null.
    assert await _copy(stand, project) == (None, True)
