"""Уведомления маршрута подписания на живом сервере (docs/design/signing-route.md, 6.5 и 6.6).

Маршрут кладётся в Postgres так, как это сделают сценарии автора: переход `send` на фактах настоящего проекта,
пометка запросов и доставка в одной транзакции. Дальше всё через API: «На подпись», сводка «Входящих», уведомления
и принятие приглашения приглашённым подписантом.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.signing_route.engine import evaluate
from hse_doc_studio.core.signing_route.entities import Participant, SigningRoute
from hse_doc_studio.core.signing_route.notices import mark_requests, notices_in
from hse_doc_studio.core.signing_route.ports import IRouteFacts, ISigningNotifier
from hse_doc_studio.core.signing_route.repositories import ISigningRouteRepository
from hse_doc_studio.core.signing_route.transitions import send
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.infra.db.orm.identity import PasswordCredentialRow, UserRow
from hse_doc_studio.infra.db.repositories.signing_routes import SqlSigningRouteRepository
from hse_doc_studio.infra.identity.argon2_hasher import Argon2PasswordHasher

from tests.integration.api.invites.conftest import Stand, make_org
from tests.integration.api.personal.conftest import ORIGIN, PASSWORD, Person

pytestmark = pytest.mark.pg

NOW = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)


async def _person(stand: Stand, name: str) -> Person:
    """Человек с id, как у настоящих аккаунтов (32 hex-символа): маршрут хранит людей так же."""
    user_id = uuid4().hex
    email = f"user-{user_id[:8]}@example.org"
    async with stand.sessions.use() as db:
        db.add(
            UserRow(
                id=user_id,
                email=email,
                email_normalized=email,
                name=name,
                status="active",
                email_verified=True,
                created_at=datetime.now(UTC),
            )
        )
        await db.flush()
        db.add(PasswordCredentialRow(user_id=user_id, password_hash=Argon2PasswordHasher().hash(PASSWORD)))
    login = stand.client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}, headers={"Origin": ORIGIN}
    )
    assert login.status_code == 200, login.text
    created = stand.client.post(
        "/api/v1/account/tokens",
        json={"name": "tests", "scopes": ["api"], "expires_in_days": 30},
        headers={"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]},
    )
    assert created.status_code == 201, created.text
    stand.client.cookies.clear()
    return Person(id=user_id, email=email, headers={"Authorization": f"Bearer {created.json()['token']}"})


def _project(stand: Stand, owner: Person) -> tuple[str, str]:
    """Настоящий проект курсовой на томе сервера; возвращает id проекта и заявления о выборе темы."""
    body = {
        "name": "Bertie",
        "pack_id": "hse-cs-sse",
        "template_id": "coursework",
        "version": "2026.1",
        "lang": "ru",
        "authors": [{"name": "Иван Иванов"}],
    }
    created = stand.client.post("/api/v1/projects", json=body, headers=owner.headers)
    assert created.status_code in {200, 201}, created.text
    return str(created.json()["id"]), "topic_application"


def _send(stand: Stand, route: SigningRoute, by: UUID) -> SigningRoute:
    """Как сценарий отправки (R5): переход, расчёт, пометка запросов, запись и доставка в одной транзакции.

    Идёт в цикле приложения (`portal`): там живут его пул соединений и порты.
    """

    async def _run() -> SigningRoute:
        container = stand.client.app.state.dishka_container  # type: ignore[attr-defined]
        facts = await (await container.get(IRouteFacts)).facts(route)
        assert facts is not None
        sent = send(route, facts, by=by, at=NOW)
        notices = notices_in(evaluate(sent, facts).effects)
        routes = await container.get(ISigningRouteRepository)
        async with (await container.get(IUnitOfWork)).begin():
            sent = mark_requests(sent, notices, at=NOW)
            sent = await routes.add(sent)
            await (await container.get(ISigningNotifier)).notify(sent, notices, actor_id=by)
        return sent

    return stand.client.portal.call(_run)  # type: ignore[no-any-return]


async def _stored(stand: Stand, route: SigningRoute) -> SigningRoute:
    found = await SqlSigningRouteRepository(stand.sessions).get(route.project_id, route.id)
    assert found is not None
    return found


def _route(project_id: str, doc_id: str, author: Person, supervisor: Participant) -> SigningRoute:
    """Автор согласует отправкой, научрук только согласует (без слотов): задача видна и без сборки PDF."""
    return SigningRoute(
        id=uuid4(),
        project_id=UUID(project_id),
        profile_id="topic-approval",
        created_by=UUID(author.id),
        docs=(doc_id,),
        participants=(Participant(id=uuid4(), step=1, persona="author", user_id=UUID(author.id)), supervisor),
        deadline=NOW + timedelta(days=5),
    )


def _items(stand: Stand, person: Person, path: str) -> list[dict[str, Any]]:
    response = stand.client.get(path, headers=person.headers)
    assert response.status_code == 200, response.text
    return list(response.json()["items"])


async def test__sent_route__signer_sees_task_count_and_request_notification(stand: Stand) -> None:
    author, petr = await _person(stand, "Иван"), await _person(stand, "Пётр")
    project_id, doc_id = _project(stand, author)
    supervisor = Participant(id=uuid4(), step=2, persona="supervisor", user_id=UUID(petr.id))

    route = _send(stand, _route(project_id, doc_id, author, supervisor), UUID(author.id))

    tasks = _items(stand, petr, "/api/v1/account/signing-tasks")
    assert tasks == [
        {
            "project": {"id": project_id, "name": "Bertie"},
            "route_id": str(route.id),
            "profile": {
                "id": "topic-approval",
                "name": {"ru": "Заявка на тему КП (SmartLMS)", "en": "Topic application (SmartLMS)"},
            },
            "round": 1,
            "sender": "Иван",
            "deadline": "2026-11-15T09:00:00Z",
            "next_action": "approve",
            "since": "2026-11-10T09:00:00Z",
        }
    ]
    assert _items(stand, author, "/api/v1/account/signing-tasks") == []
    summary = stand.client.get("/api/v1/account/inbox/summary", headers=petr.headers).json()
    assert (summary["signing_tasks"], summary["unread"]) == (1, 1)
    [notification] = _items(stand, petr, "/api/v1/account/notifications")
    assert notification["kind"] == "signing_request"
    assert notification["payload"] == {
        "project_id": project_id,
        "project_name": "Bertie",
        "actor_name": "Иван",
        "role": None,
        "ref_id": str(route.id),
        "outcome": "approve",
        "path": None,
        "excerpt": "Заявка на тему КП (SmartLMS)",
        "doc_id": None,
        "profile_id": "topic-approval",
        "deadline": "2026-11-15T09:00:00Z",
        "new_version": False,
        "freed_bytes": None,
        "signing": None,
        "signing_waiting": None,
    }
    stored = await _stored(stand, route)
    assert stored.participant(supervisor.id).notified is not None


async def test__signing_tasks__needs_sign_in(stand: Stand) -> None:
    assert stand.client.get("/api/v1/account/signing-tasks").status_code == 401


async def test__invited_signer_accepts__bound_to_the_route_and_gets_the_request(stand: Stand) -> None:
    author, petr = await _person(stand, "Иван"), await _person(stand, "Пётр")
    await make_org(stand, "kafedra", (author, "member"), (petr, "member"))
    project_id, doc_id = _project(stand, author)
    invited = stand.client.post(
        f"/api/v1/projects/{project_id}/invitations",
        json={"user_id": petr.id, "role": "reviewer"},
        headers=author.headers,
    )
    assert invited.status_code == 201, invited.text
    invitation_id = invited.json()["invitation"]["id"]
    supervisor = Participant(id=uuid4(), step=2, persona="supervisor", invitation_id=invitation_id)
    route = _send(stand, _route(project_id, doc_id, author, supervisor), UUID(author.id))
    assert _items(stand, petr, "/api/v1/account/signing-tasks") == []

    accepted = stand.client.post(f"/api/v1/account/invitations/{invitation_id}/accept", headers=petr.headers)

    assert accepted.status_code == 200, accepted.text
    stored = await _stored(stand, route)
    assert stored.participant(supervisor.id) == replace(
        supervisor, user_id=UUID(petr.id), notified=stored.participant(supervisor.id).notified
    )
    assert [t["route_id"] for t in _items(stand, petr, "/api/v1/account/signing-tasks")] == [str(route.id)]
    kinds = [n["kind"] for n in _items(stand, petr, "/api/v1/account/notifications")]
    assert kinds == ["signing_request", "project_invitation"]
