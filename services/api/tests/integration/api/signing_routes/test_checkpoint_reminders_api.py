"""Срок маршрута из срока точки и напоминание автору на настоящем сервере (docs/design/signing-route.md, 16.5 и 16.7).

Новый черновик получает срок на сутки раньше срока точки и `point_deadline`; задача `checkpoint_reminders` за 3 дня
до срока пишет владельцу и авторам `checkpoint_due` во «Входящие» и строку журнала писем, один раз на срок. Если у
точки есть маршрут, в напоминании состояние подписания: «ждём ...», «завершено» или «не отправлено».
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.identity.protocols import IUserRepository
from hse_doc_studio.core.invitations.protocols import INotifier
from hse_doc_studio.core.signing_route.ports import IRouteFacts
from hse_doc_studio.core.signing_route.repositories import ISigningRouteRepository
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.infra.db.orm.submission import SubmissionRow
from hse_doc_studio.infra.db.repositories.checkpoint_reminders import PostgresCheckpointReminderStore
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.projects.catalog_sync import MirroringProjectRepository
from hse_doc_studio.use_cases.signing_route.checkpoint_signing import CheckpointSigningReader
from hse_doc_studio.use_cases.submission.checkpoint_reminders import CheckpointReminderSweeper
from sqlalchemy import text

from tests.integration.api.signing_routes.signer_stand import NAMES, make_trio
from tests.integration.api.signing_routes.stand import TOPIC, Person, Project, Stand, make_project, person
from tests.integration.api.signing_routes.watch_stand import container, in_app

pytestmark = [pytest.mark.pg, pytest.mark.timeout(240)]

MSK = timezone(timedelta(hours=3))
TOPIC_NAME_RU = "Заявка на тему КП (SmartLMS)"


def _in_days(days: int) -> datetime:
    day = datetime.now(MSK).date() + timedelta(days=days)
    return datetime(day.year, day.month, day.day, 23, 59, tzinfo=MSK)


def _set_deadline(project: Project, who: Person, deadline: datetime | None) -> None:
    body = {"deadline": deadline.isoformat() if deadline is not None else None}
    resp = project.call(who, "PUT", f"{project.base}/submissions/profiles/{TOPIC}/deadline", json=body)
    assert resp.status_code == 200, resp.text

    async def mirrored() -> None:
        # Копия сроков в каталог уходит задачей после сохранения проекта: задача напоминаний читает её.
        await (await container(project.stand).get(MirroringProjectRepository)).drain()

    in_app(project.stand, mirrored)


def _draft(project: Project, who: Person) -> dict[str, Any]:
    resp = project.call(who, "POST", project.routes, json={"profile_id": TOPIC})
    assert resp.status_code == 201, resp.text
    return dict(resp.json())


def _sweep(stand: Stand, now: datetime) -> int:
    """Проход задачи с подменёнными часами; письма дожидаемся, чтобы строки журнала были на месте."""

    async def run() -> int:
        app = container(stand)
        notifier = await app.get(INotifier)
        sweeper = CheckpointReminderSweeper(
            PostgresCheckpointReminderStore(await app.get(SessionProvider)),
            notifier,
            await app.get(IUnitOfWork),
            clock=lambda: now,
            signing=CheckpointSigningReader(
                await app.get(ISigningRouteRepository), await app.get(IRouteFacts), await app.get(IUserRepository)
            ),
        )
        sent = await sweeper.run()
        await notifier.drain()
        return sent

    return in_app(stand, run)


def _due(stand: Stand, who: Person) -> list[dict[str, Any]]:
    resp = stand.client.get("/api/v1/account/notifications", headers=who.headers)
    assert resp.status_code == 200, resp.text
    return [item for item in resp.json()["items"] if item["kind"] == "checkpoint_due"]


async def _mail_rows(stand: Stand, project: Project) -> list[tuple[str, str | None, str | None]]:
    async with stand.sessions.use() as db:
        rows = await db.execute(
            text(
                "SELECT to_user_id, ref_kind, status FROM mail_log WHERE template = 'checkpoint_due' "
                "AND project_id = :id ORDER BY to_user_id"
            ),
            {"id": UUID(project.id)},
        )
        return [(row[0], row[1], row[2]) for row in rows.all()]


async def test__draft__route_deadline_a_day_before_the_point_and_point_deadline(stand: Stand) -> None:
    owner = await person(stand, "Автор")
    project = make_project(stand, owner)
    point = _in_days(5)
    _set_deadline(project, owner, point)

    draft = _draft(project, owner)
    _set_deadline(project, owner, _in_days(7))
    again = project.call(owner, "GET", f"{project.routes}/{draft['id']}").json()

    assert datetime.fromisoformat(draft["deadline"]) == point - timedelta(days=1)
    assert draft["point_deadline"] == point.isoformat()
    # Срок точки сменили: маршрут помнит прежний, по нему редактор пишет «Срок точки изменился».
    assert again["point_deadline"] == point.isoformat()
    assert datetime.fromisoformat(again["deadline"]) == point - timedelta(days=1)


async def test__draft__point_less_than_two_days_away_or_none__equal_or_empty(stand: Stand) -> None:
    owner = await person(stand, "Автор")
    near = make_project(stand, owner)
    soon = (datetime.now(UTC) + timedelta(days=1)).replace(microsecond=0)
    _set_deadline(near, owner, soon)
    bare = make_project(stand, owner)

    close = _draft(near, owner)
    empty = _draft(bare, owner)

    assert datetime.fromisoformat(close["deadline"]) == soon
    assert datetime.fromisoformat(close["point_deadline"]) == soon
    assert (empty["deadline"], empty["point_deadline"]) == (None, None)


async def test__reminder__owner_and_authors_once_per_deadline_with_mail_log(stand: Stand) -> None:
    owner = await person(stand, "Автор")
    coauthor = await person(stand, "Соавтор")
    supervisor = await person(stand, "Научрук")
    project = make_project(stand, owner)
    await project.member(coauthor, "editor", "author")
    await project.member(supervisor, "reviewer", "supervisor")
    point = _in_days(3)
    _set_deadline(project, owner, point)

    early = _sweep(stand, point - timedelta(days=3, minutes=1))
    first = _sweep(stand, point - timedelta(days=2))
    second = _sweep(stand, point - timedelta(days=2) + timedelta(minutes=15))
    moved = point + timedelta(days=1)
    _set_deadline(project, owner, moved)
    after_move = _sweep(stand, point - timedelta(days=1))

    assert (early, first, second, after_move) == (0, 2, 0, 2)
    [*older, latest] = sorted(_due(stand, owner), key=lambda n: n["payload"]["deadline"])
    assert older[0]["payload"]["deadline"] == point.isoformat()
    assert latest["payload"] == {
        "project_id": project.id,
        "project_name": "КП: маршрут",
        "actor_name": None,
        "role": None,
        "ref_id": None,
        "outcome": None,
        "path": None,
        "excerpt": TOPIC_NAME_RU,
        "doc_id": None,
        "profile_id": TOPIC,
        "deadline": moved.isoformat(),
        "new_version": False,
        "freed_bytes": None,
        # Маршрута у точки нет: строки «Подписание» нет.
        "signing": None,
        "signing_waiting": None,
    }
    assert len(_due(stand, coauthor)) == 2
    # Руководителю не напоминает: его срок это срок маршрута.
    assert _due(stand, supervisor) == []
    rows = await _mail_rows(stand, project)
    assert sorted(user for user, _, _ in rows) == sorted([owner.id, owner.id, coauthor.id, coauthor.id])
    assert {(ref_kind, status) for _, ref_kind, status in rows} == {(None, "not_sent")}


async def _mail_values(stand: Stand, project: Project) -> list[dict[str, Any]]:
    async with stand.sessions.use() as db:
        rows = await db.execute(
            text("SELECT params FROM mail_log WHERE template = 'checkpoint_due' AND project_id = :id ORDER BY id"),
            {"id": UUID(project.id)},
        )
        return [dict(row[0].get("values", {})) for row in rows.all()]


async def test__reminder__point_with_a_route__signing_state_in_inbox_and_mail(stand: Stand) -> None:
    trio = await make_trio(stand, images=("author", "supervisor"), academic="none")
    point = _in_days(3)
    _set_deadline(trio.project, trio.author, point)

    trio.sent()
    waiting = _sweep(stand, point - timedelta(days=2))
    trio.approved(trio.supervisor)
    _set_deadline(trio.project, trio.author, point + timedelta(days=1))
    completed = _sweep(stand, point - timedelta(days=1))

    assert (waiting, completed) == (1, 1)
    first, second = sorted(_due(stand, trio.author), key=lambda n: n["payload"]["deadline"])
    assert (first["payload"]["signing"], first["payload"]["signing_waiting"]) == (
        "waiting",
        f"научного руководителя ({NAMES['supervisor']})",
    )
    assert (second["payload"]["signing"], second["payload"]["signing_waiting"]) == ("completed", None)
    values = await _mail_values(stand, trio.project)
    assert [v.get("signing") for v in values] == [f"ждём научного руководителя ({NAMES['supervisor']})", "завершено"]


async def test__reminder__draft_route__not_sent(stand: Stand) -> None:
    owner = await person(stand, "Автор")
    project = make_project(stand, owner)
    point = _in_days(3)
    _set_deadline(project, owner, point)
    _draft(project, owner)

    assert _sweep(stand, point - timedelta(days=2)) == 1
    [due] = _due(stand, owner)
    assert (due["payload"]["signing"], due["payload"]["signing_waiting"]) == ("not_sent", None)


async def test__reminder__package_built_or_deadline_passed__nothing(stand: Stand) -> None:
    owner = await person(stand, "Автор")
    packaged = make_project(stand, owner)
    passed = make_project(stand, owner)
    point = _in_days(2)
    _set_deadline(packaged, owner, point)
    _set_deadline(passed, owner, datetime.now(UTC) - timedelta(hours=1))
    async with stand.sessions.use() as db:
        db.add(
            SubmissionRow(
                id=uuid4(),
                project_id=UUID(packaged.id),
                profile_id=TOPIC,
                created_at=datetime.now(UTC) - timedelta(hours=1),
                output_path="submissions/p.zip",
            )
        )

    sent = _sweep(stand, datetime.now(UTC))

    assert sent == 0
    assert _due(stand, owner) == []


async def test__reminder__task_registered_for_the_leader(stand: Stand) -> None:
    tasks = stand.client.app.state.background.tasks()  # type: ignore[attr-defined]

    assert tasks["checkpoint_reminders"].interval_s == 900.0
