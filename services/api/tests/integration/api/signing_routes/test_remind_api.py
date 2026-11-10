"""«Напомнить», «Скопировать ссылку» и автонапоминания маршрута подписания на настоящем сервере
(docs/design/signing-route.md, 5.7 и 8).

Проект КП пака hse-cs-sse, точка «Заявка на тему КП»: автор согласует отправкой, очередь научрука. Время
двигается правкой строк в базе (`reminded_at`, `last_sent_at`) или часами прохода автонапоминаний.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from hse_doc_studio.core.signing_route.ports import IRouteFacts, ISigningNotifier
from hse_doc_studio.core.signing_route.repositories import ISigningRouteRepository
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.infra.db.orm.invitations import ProjectInvitationRow
from hse_doc_studio.infra.db.orm.signing_routes import SigningRouteParticipantRow
from hse_doc_studio.infra.notifications.mailer import SmtpNotificationMailer
from hse_doc_studio.use_cases.signing_route.reminders import SigningReminderSweeper
from sqlalchemy import select, update

from tests.integration.api.signing_routes.stand import (
    TOPIC,
    TOPIC_DOCS,
    Person,
    Project,
    Stand,
    make_project,
    person,
)

pytestmark = [pytest.mark.pg, pytest.mark.timeout(240)]

SUPERVISOR = {"name": "Петров Пётр Петрович", "role": "university"}
HALF_DAY = 12 * 3600


async def _sent(stand: Stand, *, invite: bool = False) -> tuple[Project, Person, Person, dict[str, Any]]:
    """Отправленный маршрут: автор согласовал отправкой, научрук участник проекта или приглашён по почте."""
    author = await person(stand, "Иванов Иван Иванович")
    supervisor = await person(stand, "Петров Пётр Петрович")
    project = make_project(stand, author, supervisor=SUPERVISOR)
    if not invite:
        await project.member(supervisor, "reviewer", "supervisor")
    route = _create(project, author)
    if invite:
        invited = project.call(
            author,
            "POST",
            f"{project.base}/invitations",
            json={
                "email": supervisor.email,
                "role": "reviewer",
                "persona": "supervisor",
                "next": f"/sign/{project.id}/{route['id']}",
            },
        )
        assert invited.status_code == 201, invited.text
        steps = [
            [{"id": p["id"], "persona": p["persona"], "user_id": p["user_id"], "invitation_id": None}]
            for step in route["steps"]
            for p in step
        ]
        steps[1][0]["invitation_id"] = invited.json()["invitation"]["id"]
        body = {"steps": steps, "extra_slots": [], "deadline": None, "message": None}
        assert project.call(author, "PUT", f"{project.routes}/{route['id']}", json=body).status_code == 200
    for doc_id in TOPIC_DOCS:
        project.build(doc_id)
    project.png(author, "author")
    project.place(author)
    preview = project.call(author, "POST", f"{project.routes}/{route['id']}/preview", json={})
    assert preview.status_code == 200, preview.text
    expected = {d["doc_id"]: d["token"] for d in preview.json()["docs"]}
    sent = project.call(
        author, "POST", f"{project.routes}/{route['id']}/send", json={"expected": expected, "sign": None}
    )
    assert sent.status_code == 200, sent.text
    return project, author, supervisor, sent.json()


def _create(project: Project, who: Person) -> dict[str, Any]:
    resp = project.call(who, "POST", project.routes, json={"profile_id": TOPIC})
    assert resp.status_code in (200, 201), resp.text
    return dict(resp.json())


def _remind(project: Project, who: Person, route_id: str, participant_id: str) -> Any:
    return project.call(who, "POST", f"{project.routes}/{route_id}/participants/{participant_id}/remind", json={})


def _route(project: Project, who: Person, route_id: str) -> dict[str, Any]:
    resp = project.call(who, "GET", f"{project.routes}/{route_id}")
    assert resp.status_code == 200, resp.text
    return dict(resp.json())


def _notifications(stand: Stand, who: Person) -> list[dict[str, Any]]:
    resp = stand.client.get("/api/v1/account/notifications", headers=who.headers)
    assert resp.status_code == 200, resp.text
    return list(resp.json()["items"])


async def _reminded_ago(stand: Stand, participant_id: str, ago: timedelta) -> None:
    """Как будто участнику напомнили `ago` назад."""
    async with stand.sessions.use() as db:
        await db.execute(
            update(SigningRouteParticipantRow)
            .where(SigningRouteParticipantRow.id == UUID(participant_id))
            .values(reminded_at=datetime.now(UTC) - ago)
        )


async def _invitation_sent_ago(stand: Stand, invitation_id: str, ago: timedelta) -> None:
    async with stand.sessions.use() as db:
        await db.execute(
            update(ProjectInvitationRow)
            .where(ProjectInvitationRow.id == invitation_id)
            .values(last_sent_at=datetime.now(UTC) - ago)
        )


# --- «Напомнить» ---------------------------------------------------------------------------------------------------


async def test__remind__whose_turn_it_is__inbox_notification_event_and_mark(stand: Stand) -> None:
    project, author, supervisor, sent = await _sent(stand)
    waiting = sent["steps"][1][0]
    assert (waiting["state"], waiting["reminded_at"], waiting["reminders"]) == ("to_approve", None, 0)

    resp = _remind(project, author, sent["id"], waiting["id"])

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"participant_id": waiting["id"], "delivery": "inbox", "link": None}
    route = _route(project, author, sent["id"])
    reminded = route["steps"][1][0]
    assert reminded["reminders"] == 1
    assert reminded["reminded_at"] is not None
    assert [(e["kind"], e["who"]) for e in route["events"]][-1] == ("reminded", "Иванов Иван Иванович")
    newest = _notifications(stand, supervisor)[0]
    assert newest["kind"] == "signing_reminder"
    assert (newest["payload"]["ref_id"], newest["payload"]["outcome"]) == (sent["id"], "approve")
    assert newest["payload"]["actor_name"] == "Иванов Иван Иванович"


async def test__remind__again_within_twelve_hours__rate_limited_until_available(stand: Stand) -> None:
    project, author, _, sent = await _sent(stand)
    waiting = sent["steps"][1][0]
    assert _remind(project, author, sent["id"], waiting["id"]).status_code == 200
    first = _route(project, author, sent["id"])["steps"][1][0]["reminded_at"]

    again = _remind(project, author, sent["id"], waiting["id"])

    assert again.status_code == 429, again.text
    body = again.json()
    assert body["code"] == "rate_limited"
    assert HALF_DAY - 60 <= body["retry_after"] <= HALF_DAY
    assert again.headers["Retry-After"] == str(body["retry_after"])
    available = datetime.fromisoformat(body["available_at"])
    assert available - datetime.fromisoformat(first) == timedelta(hours=12)
    assert _route(project, author, sent["id"])["steps"][1][0]["reminders"] == 1

    await _reminded_ago(stand, waiting["id"], timedelta(hours=12, minutes=1))
    later = _remind(project, author, sent["id"], waiting["id"])

    assert later.status_code == 200, later.text
    assert _route(project, author, sent["id"])["steps"][1][0]["reminders"] == 2


async def test__remind__not_waiting__conflict(stand: Stand) -> None:
    project, author, _, sent = await _sent(stand)
    done, waiting = sent["steps"][0][0], sent["steps"][1][0]

    finished = _remind(project, author, sent["id"], done["id"])
    project.replace_sent("topic_application")  # версию на подписи подменили: по расчёту маршрут уже остановлен
    rebuilt = _remind(project, author, sent["id"], waiting["id"])
    assert project.call(author, "POST", f"{project.routes}/{sent['id']}/cancel", json={}).status_code == 200
    cancelled = _remind(project, author, sent["id"], waiting["id"])

    for resp in (finished, rebuilt, cancelled):
        assert (resp.status_code, resp.json()["code"]) == (409, "participant_not_waiting"), resp.text
    assert _route(project, author, sent["id"])["steps"][1][0]["reminders"] == 0


async def test__remind__unknown_participant_or_route__404(stand: Stand) -> None:
    project, author, _, sent = await _sent(stand)
    waiting = sent["steps"][1][0]
    other_route = "00000000-0000-4000-8000-000000000001"

    assert _remind(project, author, sent["id"], other_route).status_code == 404
    assert _remind(project, author, sent["id"], "not-an-id").status_code == 404
    assert _remind(project, author, other_route, waiting["id"]).status_code == 404


async def test__remind__only_who_manages_the_route(stand: Stand) -> None:
    project, _, supervisor, sent = await _sent(stand)
    waiting = sent["steps"][1][0]
    stranger = await person(stand, "Чужой Человек")
    path = f"{project.routes}/{sent['id']}/participants/{waiting['id']}/remind"

    assert _remind(project, supervisor, sent["id"], waiting["id"]).status_code == 403
    assert _remind(project, stranger, sent["id"], waiting["id"]).status_code == 404
    assert stand.client.post(path, json={}).status_code == 401


# --- приглашённый ----------------------------------------------------------------------------------------------------


@pytest.fixture
def smtp(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Почта на сервере настроена: приглашения уходят письмом; список хранит ссылки из писем."""
    letters: list[str] = []

    async def _send_invitation(self: SmtpNotificationMailer, to_email: str, *, link: str, **_kwargs: Any) -> bool:
        letters.append(link)
        return True

    monkeypatch.setattr(SmtpNotificationMailer, "enabled", property(lambda _self: True))
    monkeypatch.setattr(SmtpNotificationMailer, "send_invitation", _send_invitation)
    return letters


def _link(project: Project, who: Person, route_id: str, participant_id: str) -> Any:
    return project.call(who, "POST", f"{project.routes}/{route_id}/participants/{participant_id}/link", json={})


def _invite_state(stand: Stand, token: str) -> str:
    resp = stand.client.get(f"/api/v1/project-invitations/{token}")
    assert resp.status_code == 200, resp.text
    return str(resp.json()["state"])


def _token(link: str) -> str:
    return link.split("/project-invite/", 1)[1].split("?", 1)[0]


async def _invitation_row(stand: Stand, invitation_id: str) -> tuple[int, datetime, datetime]:
    async with stand.sessions.use() as db:
        row = (
            await db.execute(select(ProjectInvitationRow).where(ProjectInvitationRow.id == invitation_id))
        ).scalar_one()
        return row.sent_count, row.last_sent_at, row.expires_at


async def test__remind__invited_with_mail__invitation_resent_by_email_and_recorded(
    stand: Stand, smtp: list[str]
) -> None:
    project, author, _, sent = await _sent(stand, invite=True)
    invited = sent["steps"][1][0]
    assert invited["state"] == "invited"
    await _invitation_sent_ago(stand, invited["invitation_id"], timedelta(hours=1))

    resp = _remind(project, author, sent["id"], invited["id"])

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"participant_id": invited["id"], "delivery": "email", "link": None}
    assert smtp[-1].startswith("http://localhost:8100/project-invite/")
    assert smtp[-1].endswith(f"?next=%2Fsign%2F{project.id}%2F{sent['id']}")
    route = _route(project, author, sent["id"])
    assert route["steps"][1][0]["reminders"] == 1
    assert [(e["kind"], e["who"]) for e in route["events"]][-1] == ("invited", "Иванов Иван Иванович")
    again = _remind(project, author, sent["id"], invited["id"])
    assert (again.status_code, again.json()["code"]) == (429, "rate_limited")


async def test__remind__invited_just_now_with_mail__invitation_limit_and_nothing_recorded(
    stand: Stand, smtp: list[str]
) -> None:
    project, author, _, sent = await _sent(stand, invite=True)
    invited = sent["steps"][1][0]
    letters = len(smtp)

    resp = _remind(project, author, sent["id"], invited["id"])

    assert resp.json()["code"] == "invitation_resend_too_soon", resp.text
    waiting = _route(project, author, sent["id"])["steps"][1][0]
    assert (waiting["reminded_at"], waiting["reminders"]) == (None, 0)
    assert len(smtp) == letters


async def test__remind__invited_just_now_without_mail__manual_link_without_limits_or_marks(stand: Stand) -> None:
    project, author, _, sent = await _sent(stand, invite=True)
    invited = sent["steps"][1][0]
    before = await _invitation_row(stand, invited["invitation_id"])

    first = _remind(project, author, sent["id"], invited["id"])
    second = _remind(project, author, sent["id"], invited["id"])

    for resp in (first, second):
        assert resp.status_code == 200, resp.text
        assert (resp.json()["participant_id"], resp.json()["delivery"]) == (invited["id"], "manual")
        assert resp.json()["link"].endswith(f"?next=%2Fsign%2F{project.id}%2F{sent['id']}")
    assert first.json()["link"] != second.json()["link"]
    route = _route(project, author, sent["id"])
    assert (route["steps"][1][0]["reminded_at"], route["steps"][1][0]["reminders"]) == (None, 0)
    assert [e["kind"] for e in route["events"]] == [e["kind"] for e in sent["events"]]
    assert (await _invitation_row(stand, invited["invitation_id"]))[:2] == before[:2]


async def test__remind__invited__editor_without_access_rights__forbidden(stand: Stand) -> None:
    project, _, _, sent = await _sent(stand, invite=True)
    invited = sent["steps"][1][0]
    editor = await person(stand, "Редактор")
    await project.member(editor, "editor", None)
    await _invitation_sent_ago(stand, invited["invitation_id"], timedelta(hours=1))

    resp = _remind(project, editor, sent["id"], invited["id"])

    assert resp.status_code == 403, resp.text
    assert _route(project, editor, sent["id"])["steps"][1][0]["reminders"] == 0


# --- «Скопировать ссылку» --------------------------------------------------------------------------------------------


async def test__link__member__signing_page_any_time_and_nothing_written(stand: Stand) -> None:
    project, author, _, sent = await _sent(stand)
    waiting = sent["steps"][1][0]
    assert _remind(project, author, sent["id"], waiting["id"]).status_code == 200  # 12 часов ссылку не закрывают
    before = _route(project, author, sent["id"])

    first = _link(project, author, sent["id"], waiting["id"])
    second = _link(project, author, sent["id"], waiting["id"])

    page = f"http://localhost:8100/sign/{project.id}/{sent['id']}"
    for resp in (first, second):
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"participant_id": waiting["id"], "kind": "page", "link": page}
        assert resp.headers["Cache-Control"] == "no-store"
    after = _route(project, author, sent["id"])
    assert (after["steps"], after["events"]) == (before["steps"], before["events"])


async def test__link__invited_just_now_without_mail__new_invitation_link_each_time_not_a_resend(stand: Stand) -> None:
    project, author, _, sent = await _sent(stand, invite=True)
    invited = sent["steps"][1][0]
    sent_count, last_sent_at, expires_at = await _invitation_row(stand, invited["invitation_id"])

    first = _link(project, author, sent["id"], invited["id"])
    second = _link(project, author, sent["id"], invited["id"])

    for resp in (first, second):
        assert resp.status_code == 200, resp.text
        assert (resp.json()["participant_id"], resp.json()["kind"]) == (invited["id"], "invitation")
        assert resp.json()["link"].startswith("http://localhost:8100/project-invite/")
        assert resp.json()["link"].endswith(f"?next=%2Fsign%2F{project.id}%2F{sent['id']}")
    # Секрет хранится хэшем: каждая выдача это новая ссылка, прежняя перестаёт работать.
    assert _invite_state(stand, _token(first.json()["link"])) == "invalid"
    assert _invite_state(stand, _token(second.json()["link"])) == "ok"
    after = await _invitation_row(stand, invited["invitation_id"])
    assert after[:2] == (sent_count, last_sent_at)
    assert after[2] >= expires_at
    route = _route(project, author, sent["id"])
    assert (route["steps"][1][0]["reminded_at"], route["steps"][1][0]["reminders"]) == (None, 0)
    assert [e["kind"] for e in route["events"]] == [e["kind"] for e in sent["events"]]
    # Обычный повтор приглашения по-прежнему ограничен: ссылка его не заменяет и не сбрасывает.
    resend = project.call(author, "POST", f"{project.base}/invitations/{invited['invitation_id']}/resend")
    assert (resend.status_code, resend.json()["code"]) == (429, "invitation_resend_too_soon")


async def test__link__invited_with_mail__link_stays_in_the_letter(stand: Stand, smtp: list[str]) -> None:
    project, author, _, sent = await _sent(stand, invite=True)
    invited = sent["steps"][1][0]
    letter = smtp[-1]

    resp = _link(project, author, sent["id"], invited["id"])

    assert (resp.status_code, resp.json()["code"]) == (409, "link_by_mail"), resp.text
    assert _invite_state(stand, _token(letter)) == "ok"


async def test__link__who_may_take_it(stand: Stand) -> None:
    project, author, supervisor, sent = await _sent(stand, invite=True)
    done, invited = sent["steps"][0][0], sent["steps"][1][0]
    editor = await person(stand, "Редактор")
    await project.member(editor, "editor", None)
    reader = await person(stand, "Читатель")
    await project.member(reader, "reader", None)
    stranger = await person(stand, "Чужой Человек")
    path = f"{project.routes}/{sent['id']}/participants/{invited['id']}/link"

    # Редактор управляет маршрутом, но приглашениями распоряжается только тот, кто решает доступ.
    assert _link(project, editor, sent["id"], invited["id"]).status_code == 403
    assert _link(project, editor, sent["id"], done["id"]).json()["kind"] == "page"
    assert _link(project, reader, sent["id"], done["id"]).status_code == 403
    assert _link(project, stranger, sent["id"], done["id"]).status_code == 404
    assert _link(project, supervisor, sent["id"], done["id"]).status_code == 404  # приглашение ещё не принято
    assert stand.client.post(path, json={}).status_code == 401
    assert _link(project, author, sent["id"], "not-an-id").status_code == 404
    assert _link(project, author, sent["id"], "00000000-0000-4000-8000-000000000001").status_code == 404
    assert _link(project, author, "00000000-0000-4000-8000-000000000001", invited["id"]).status_code == 404


# --- автонапоминания -------------------------------------------------------------------------------------------------


def _sweep(stand: Stand, now: datetime | None = None) -> int:
    """Проход автонапоминаний в цикле приложения; `now` подменяет часы прохода, без него задача сервера как есть."""

    async def _run() -> int:
        container = stand.client.app.state.dishka_container  # type: ignore[attr-defined]
        if now is None:
            return await (await container.get(SigningReminderSweeper)).run()
        sweeper = SigningReminderSweeper(
            await container.get(ISigningRouteRepository),
            await container.get(IRouteFacts),
            await container.get(ISigningNotifier),
            await container.get(IUnitOfWork),
            clock=lambda: now,
        )
        return await sweeper.run()

    return stand.client.portal.call(_run)  # type: ignore[no-any-return]


async def test__auto_reminders__registered_for_leader_and_quiet_right_after_sending(stand: Stand) -> None:
    await _sent(stand)

    tasks = stand.client.app.state.background.tasks()  # type: ignore[attr-defined]

    assert tasks["signing_reminders"].interval_s == 900.0
    assert _sweep(stand) == 0


async def test__auto_reminders__three_days_waiting__reminds_once_per_pass(stand: Stand) -> None:
    project, author, supervisor, sent = await _sent(stand)
    later = datetime.fromisoformat(sent["sent_at"]) + timedelta(days=3, minutes=1)

    first = _sweep(stand, later)
    second = _sweep(stand, later + timedelta(minutes=15))

    assert (first, second) == (1, 0)
    route = _route(project, author, sent["id"])
    reminded = route["steps"][1][0]
    assert reminded["reminders"] == 1
    assert datetime.fromisoformat(reminded["reminded_at"]) == later
    assert [(e["kind"], e["who"]) for e in route["events"]][-1] == ("reminded", None)
    kinds = [n["kind"] for n in _notifications(stand, supervisor)]
    assert kinds.count("signing_reminder") == 1
    # Автонапоминание закрывает и ручное на 12 часов: счёт на человека общий (здесь оно «в будущем»).
    manual = _remind(project, author, sent["id"], reminded["id"])
    assert (manual.status_code, manual.json()["code"]) == (429, "rate_limited")
