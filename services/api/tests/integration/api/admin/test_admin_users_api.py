"""`/api/admin` для людей: список, роль, отключение, одобрение, приглашения, break-glass ссылка сброса."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from fastapi import FastAPI
from hse_doc_studio.api.auth_cookie import SESSION_COOKIE
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.guards import install_exception_handlers
from hse_doc_studio.api.routers.admin import make_admin_router
from hse_doc_studio.core.identity.entities import Session, User, UserStatus
from hse_doc_studio.core.identity.normalize import hash_token, normalize_email
from hse_doc_studio.core.identity.protocols import IActorResolver
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.infra.identity.resolvers import BearerActorResolver, ChainActorResolver, SessionCookieResolver
from hse_doc_studio.use_cases.admin.audit import ListAuditUC
from hse_doc_studio.use_cases.admin.invitations import ResendInviteUC
from hse_doc_studio.use_cases.admin.users import (
    ApproveUserUC,
    DisableUserUC,
    EnableUserUC,
    GetUserUC,
    ListApprovalsUC,
    ListUsersUC,
    RejectUserUC,
    RevokeUserSessionsUC,
    SetUserAdminUC,
)
from hse_doc_studio.use_cases.identity.invites import CreateInviteUC, ListInvitesUC, RevokeInviteUC
from hse_doc_studio.use_cases.identity.mail import LinkDelivery
from hse_doc_studio.use_cases.identity.recovery import IssueResetLinkUC
from hse_doc_studio.use_cases.identity.sessions import SessionService
from httpx import ASGITransport, AsyncClient

from tests.fakes.auth import (
    InMemoryAuditLog,
    InMemoryAuthTokenRepository,
    InMemoryMailOutboxRepository,
    InMemoryRegistrationInviteRepository,
    InMemorySessionRepository,
)
from tests.fakes.identity import InMemoryIdentityStore, InMemoryUserDirectory, InMemoryUserRepository
from tests.unit.use_cases.identity.conftest import FakeSender, FakeUow

NOW = datetime.now(UTC)


class _Env:
    def __init__(self) -> None:
        self.store = InMemoryIdentityStore()
        self.users = InMemoryUserRepository(self.store)
        self.directory = InMemoryUserDirectory(self.store)
        self.sessions = InMemorySessionRepository()
        self.audit = InMemoryAuditLog()
        self.invites = InMemoryRegistrationInviteRepository()
        self.auth_tokens = InMemoryAuthTokenRepository()
        self.outbox = InMemoryMailOutboxRepository()
        self.sender = FakeSender()
        self.uow = FakeUow()
        self.make: Callable[[], AsyncClient]

    async def add(self, uid: str, *, admin: bool = False, status: UserStatus = UserStatus.active) -> dict[str, str]:
        email = f"{uid}@example.org"
        await self.users.add(
            User(
                id=uid,
                email=email,
                email_normalized=normalize_email(email),
                name=uid.title(),
                status=status,
                created_at=NOW,
                email_verified=True,
                is_instance_admin=admin,
            )
        )
        await self.sessions.add(
            Session(hash_token(f"s-{uid}"), uid, "csrf", NOW, NOW, NOW + timedelta(days=7), None, "UA")
        )
        return {"Cookie": f"{SESSION_COOKIE}=s-{uid}"}


class _Provider(Provider):
    scope = Scope.APP

    def __init__(self, env: _Env) -> None:
        super().__init__()
        self.e = env
        self._delivery = LinkDelivery(env.sender, env.outbox)
        self._create = CreateInviteUC(env.invites, self._delivery, env.audit, public_url="https://studio.test")

    @provide
    def resolver(self) -> IActorResolver:
        return ChainActorResolver(
            [SessionCookieResolver(SessionService(self.e.sessions, self.e.users)), BearerActorResolver()]
        )

    @provide
    def list_audit(self) -> ListAuditUC:
        return ListAuditUC(self.e.audit)

    @provide
    def list_users(self) -> ListUsersUC:
        return ListUsersUC(self.e.directory)

    @provide
    def get_user(self) -> GetUserUC:
        return GetUserUC(self.e.directory)

    @provide
    def disable(self) -> DisableUserUC:
        return DisableUserUC(self.e.users, self.e.sessions, self.e.audit, self.e.uow)

    @provide
    def enable(self) -> EnableUserUC:
        return EnableUserUC(self.e.users, self.e.audit, self.e.uow)

    @provide
    def set_admin(self) -> SetUserAdminUC:
        return SetUserAdminUC(self.e.users, self.e.audit, self.e.uow)

    @provide
    def revoke(self) -> RevokeUserSessionsUC:
        return RevokeUserSessionsUC(self.e.users, self.e.sessions, self.e.audit, self.e.uow)

    @provide
    def approvals(self) -> ListApprovalsUC:
        return ListApprovalsUC(self.e.directory)

    @provide
    def approve(self) -> ApproveUserUC:
        return ApproveUserUC(self.e.users, self.e.audit, self.e.uow)

    @provide
    def reject(self) -> RejectUserUC:
        return RejectUserUC(self.e.users, self.e.audit, self.e.uow)

    @provide
    def reset_link(self) -> IssueResetLinkUC:
        return IssueResetLinkUC(
            self.e.users, self.e.auth_tokens, self._delivery, self.e.audit, self.e.uow, public_url="https://studio.test"
        )

    @provide
    def create_invite(self) -> CreateInviteUC:
        return self._create

    @provide
    def list_invites(self) -> ListInvitesUC:
        return ListInvitesUC(self.e.invites)

    @provide
    def revoke_invite(self) -> RevokeInviteUC:
        return RevokeInviteUC(self.e.invites, self.e.audit)

    @provide
    def resend_invite(self) -> ResendInviteUC:
        return ResendInviteUC(self.e.invites, self._create, self.e.audit, self.e.uow)


@pytest_asyncio.fixture
async def env(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[_Env]:
    monkeypatch.setattr(settings, "mode", StudioMode.server)
    e = _Env()
    clients: list[AsyncClient] = []
    containers = []

    def make() -> AsyncClient:
        app = FastAPI()
        app.include_router(make_admin_router())
        install_exception_handlers(app)
        container = make_async_container(_Provider(e), FastapiProvider())
        setup_dishka(container, app)
        containers.append(container)
        client = AsyncClient(transport=ASGITransport(app=app, client=("203.0.113.9", 5000)), base_url="http://test")
        clients.append(client)
        return client

    e.make = make
    yield e
    for client in clients:
        await client.aclose()
    for container in containers:
        await container.close()


async def test__users__list_search_status_and_page_shape(env: _Env) -> None:
    boss = await env.add("boss", admin=True)
    await env.add("anna")
    await env.add("maria", status=UserStatus.pending_approval)
    env.directory.project_counts["anna"] = 2
    client = env.make()

    everyone = (await client.get("/api/admin/users?limit=2", headers=boss)).json()
    found = (await client.get("/api/admin/users?q=ANN", headers=boss)).json()
    waiting = (await client.get("/api/admin/users?status=pending_approval", headers=boss)).json()

    assert (everyone["total"], everyone["limit"], everyone["offset"], len(everyone["items"])) == (3, 2, 0, 2)
    assert [(u["id"], u["project_count"]) for u in found["items"]] == [("anna", 2)]
    assert [u["id"] for u in waiting["items"]] == ["maria"]
    assert (await client.get("/api/admin/users?status=nonsense", headers=boss)).status_code == 422


async def test__users__student_gets_404_everywhere(env: _Env) -> None:
    student = await env.add("student")
    client = env.make()

    for method, path in (
        ("GET", "/api/admin/users"),
        ("PATCH", "/api/admin/users/student"),
        ("POST", "/api/admin/users/student/disable"),
        ("GET", "/api/admin/approvals"),
        ("GET", "/api/admin/invitations"),
    ):
        response = await client.request(method, path, headers=student, json={} if method == "PATCH" else None)
        assert response.status_code == 404, path


async def test__users__last_admin_is_protected_with_409(env: _Env) -> None:
    boss = await env.add("boss", admin=True)
    client = env.make()

    demote = await client.patch("/api/admin/users/boss", json={"is_instance_admin": False}, headers=boss)
    disable = await client.post("/api/admin/users/boss/disable", headers=boss)

    assert (demote.status_code, demote.json()["code"]) == (409, "last_admin")
    assert disable.status_code == 409
    assert env.store.users["boss"].is_instance_admin


async def test__users__promote_then_demote_and_disable_enable(env: _Env) -> None:
    boss = await env.add("boss", admin=True)
    await env.add("anna")
    client = env.make()

    promoted = await client.patch("/api/admin/users/anna", json={"is_instance_admin": True}, headers=boss)
    disabled = await client.post("/api/admin/users/anna/disable", headers=boss)
    enabled = await client.post("/api/admin/users/anna/enable", headers=boss)

    assert promoted.json()["is_instance_admin"] is True
    assert disabled.json()["status"] == "disabled"
    assert enabled.json()["status"] == "active"
    assert (await client.post("/api/admin/users/ghost/disable", headers=boss)).status_code == 404


async def test__users__disable_closes_the_sessions_of_that_user(env: _Env) -> None:
    boss = await env.add("boss", admin=True)
    anna = await env.add("anna")
    client = env.make()

    await client.post("/api/admin/users/anna/disable", headers=boss)

    assert (await client.get("/api/admin/users", headers=anna)).status_code == 401


async def test__users__revoke_sessions_reports_count(env: _Env) -> None:
    boss = await env.add("boss", admin=True)
    await env.add("anna")
    client = env.make()

    response = await client.post("/api/admin/users/anna/sessions/revoke", headers=boss)

    assert response.json() == {"revoked": 1}


async def test__approvals__approve_changes_status_and_leaves_the_queue(env: _Env) -> None:
    boss = await env.add("boss", admin=True)
    await env.add("maria", status=UserStatus.pending_approval)
    await env.add("pavel", status=UserStatus.pending_approval)
    client = env.make()

    queue = (await client.get("/api/admin/approvals", headers=boss)).json()
    approved = await client.post("/api/admin/approvals/maria/approve", headers=boss)
    rejected = await client.post("/api/admin/approvals/pavel/reject", headers=boss)
    again = await client.post("/api/admin/approvals/maria/approve", headers=boss)

    assert queue["total"] == 2
    assert approved.json()["status"] == "active"
    assert rejected.json()["status"] == "disabled"
    assert again.status_code == 404
    assert (await client.get("/api/admin/approvals", headers=boss)).json()["total"] == 0


async def test__reset_link__needs_confirmation_audits_and_is_not_cached(env: _Env) -> None:
    boss = await env.add("boss", admin=True)
    await env.add("anna")
    client = env.make()

    refused = await client.post("/api/admin/users/anna/reset-link", json={"confirm": False}, headers=boss)
    issued = await client.post("/api/admin/users/anna/reset-link", json={"confirm": True}, headers=boss)
    missing = await client.post("/api/admin/users/ghost/reset-link", json={"confirm": True}, headers=boss)

    assert refused.status_code == 403
    assert issued.status_code == 200
    assert issued.json()["link"].startswith("https://studio.test/reset/")
    assert issued.headers["cache-control"] == "no-store"
    assert missing.status_code == 404
    entry = (await env.audit.list(action="admin.reset_link_issued"))[0]
    assert (entry.actor_id, entry.target, entry.details) == ("boss", "anna", {"break_glass": True})


async def test__invitations__create_list_resend_revoke_without_smtp_returns_link(env: _Env) -> None:
    boss = await env.add("boss", admin=True)
    client = env.make()

    created = await client.post(
        "/api/admin/invitations", json={"email": "new@example.org", "ttl_days": 3}, headers=boss
    )
    body = created.json()
    listed = (await client.get("/api/admin/invitations", headers=boss)).json()
    resent = await client.post(f"/api/admin/invitations/{body['invitation']['id']}/resend", headers=boss)
    deleted = await client.delete(f"/api/admin/invitations/{resent.json()['invitation']['id']}", headers=boss)
    gone = await client.delete(f"/api/admin/invitations/{resent.json()['invitation']['id']}", headers=boss)

    assert created.status_code == 201
    assert body["link"].startswith("https://studio.test/invite/")
    assert body["invitation"]["status"] == "pending"
    assert listed["total"] == 1
    assert resent.json()["invitation"]["id"] != body["invitation"]["id"]
    assert resent.json()["link"] != body["link"]
    assert deleted.status_code == 204
    assert gone.status_code == 404
    assert (await client.get("/api/admin/invitations", headers=boss)).json()["total"] == 0


async def test__invitations__bad_input_is_422(env: _Env) -> None:
    boss = await env.add("boss", admin=True)
    client = env.make()

    for body in ({"email": "not-an-email", "ttl_days": None}, {"email": None, "ttl_days": 31}):
        assert (await client.post("/api/admin/invitations", json=body, headers=boss)).status_code == 422


async def test__invitations__expired_and_used_statuses(env: _Env) -> None:
    boss = await env.add("boss", admin=True)
    client = env.make()
    created = (await client.post("/api/admin/invitations", json={"email": None, "ttl_days": None}, headers=boss)).json()
    key = next(iter(env.invites._items))
    env.invites._items[key] = replace(env.invites._items[key], expires_at=NOW - timedelta(days=1))

    listed = (await client.get("/api/admin/invitations", headers=boss)).json()
    env.invites._items[key] = replace(env.invites._items[key], used_at=NOW)
    used = (await client.get("/api/admin/invitations", headers=boss)).json()

    assert created["link"] is not None
    assert listed["items"][0]["status"] == "expired"
    assert used["items"][0]["status"] == "used"
