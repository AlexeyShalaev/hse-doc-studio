"""Встраиваемые ресурсы в server-режиме: поток логов, PDF и файл для ONLYOFFICE под cookie или токеном документа."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from fastapi import APIRouter, Depends, FastAPI
from fastapi.responses import Response, StreamingResponse
from hse_doc_studio.api import guards, route_scopes
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.guards import install_exception_handlers, project_access_guard
from hse_doc_studio.api.security_headers import SecurityHeadersMiddleware
from hse_doc_studio.core.access.entities import Actor, Grant, ProjectAcl, Role
from hse_doc_studio.core.identity.entities import Session, User, UserStatus
from hse_doc_studio.core.identity.normalize import hash_token, normalize_email
from hse_doc_studio.core.identity.protocols import IActorResolver
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.core.office_tokens import OfficeTokenPurpose, OfficeTokenSigner
from hse_doc_studio.infra.identity.resolvers import ChainActorResolver, SessionCookieResolver
from hse_doc_studio.use_cases.identity.sessions import SessionService
from hse_doc_studio.use_cases.office_editor.access import IOfficeAccess, ServerOfficeAccess
from httpx import ASGITransport, AsyncClient

from tests.fakes.auth import InMemorySessionRepository, empty_bearer_resolver
from tests.fakes.identity import InMemoryIdentityStore, InMemoryUserRepository

SECRET = "valid-cookie-secret"  # noqa: S105
NOW = datetime.now(UTC)
PROJECT = uuid4()
_BASE = f"/api/v1/projects/{PROJECT}"
_FILE = "pres/pptx/presentation.pptx"


class _Acl:
    """Права участников проекта; отозванный участник пропадает из словаря."""

    def __init__(self) -> None:
        self.roles: dict[str, Role] = {"u1": Role.editor}

    async def load_for(self, actor: Actor, project_id: UUID) -> ProjectAcl | None:
        role = self.roles.get(actor.id or "")
        if role is None or project_id != PROJECT:
            return None
        return ProjectAcl(str(project_id), owner_id="owner", grants={actor.id or "": Grant(role)})

    async def set_shared_enabled(self, project_id: UUID, enabled: bool) -> None:
        raise NotImplementedError


class _Providers(Provider):
    scope = Scope.APP

    def __init__(self, sessions: InMemorySessionRepository, users: InMemoryUserRepository, acl: _Acl) -> None:
        super().__init__()
        self._sessions, self._users, self._acl = sessions, users, acl

    @provide
    def resolver(self) -> IActorResolver:
        service = SessionService(self._sessions, self._users)
        return ChainActorResolver([SessionCookieResolver(service), empty_bearer_resolver()])

    @provide
    def office_access(self) -> IOfficeAccess:
        return ServerOfficeAccess(OfficeTokenSigner([b"k" * 32]), self._acl, self._users)


class _Env:
    def __init__(self, client: AsyncClient, acl: _Acl, users: InMemoryUserRepository) -> None:
        self.client = client
        self.acl = acl
        self.users = users

    async def token(self, *, purpose: OfficeTokenPurpose = OfficeTokenPurpose.document, path: str = _FILE) -> str:
        from hse_doc_studio.core.access.context import set_current_actor

        set_current_actor(Actor.user("u1"))
        try:
            tokens = await ServerOfficeAccess(OfficeTokenSigner([b"k" * 32]), self.acl, self.users).issue(
                PROJECT, "pres", path
            )
        finally:
            set_current_actor(None)
        assert tokens is not None
        return tokens.document if purpose is OfficeTokenPurpose.document else tokens.callback


@pytest_asyncio.fixture
async def env(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[_Env]:
    monkeypatch.setattr(settings, "mode", StudioMode.server)
    monkeypatch.setattr(route_scopes, "ROUTE_SCOPES", {})
    acl = _Acl()

    async def load_acl(_request: object, project_id: str) -> ProjectAcl | None:
        return await acl.load_for(Actor.user("u1"), UUID(project_id))

    monkeypatch.setattr(guards, "load_project_acl", load_acl)
    sessions = InMemorySessionRepository()
    users = InMemoryUserRepository(InMemoryIdentityStore())
    email = "ann@example.org"
    await users.add(
        User(
            id="u1",
            email=email,
            email_normalized=normalize_email(email),
            name="Ann",
            status=UserStatus.active,
            created_at=NOW,
            email_verified=True,
        )  # fmt: skip
    )
    await sessions.add(
        Session(
            id_hash=hash_token(SECRET),
            user_id="u1",
            csrf_token="c",
            created_at=NOW,
            last_seen_at=NOW,
            expires_at=NOW + timedelta(days=7),
        )  # fmt: skip
    )
    router = APIRouter(dependencies=[Depends(project_access_guard)])

    @router.get("/api/v1/projects/{project_id}/files/{path:path}")
    async def get_file(project_id: UUID, path: str) -> Response:  # noqa: ARG001
        media = "application/pdf" if path.endswith(".pdf") else "application/octet-stream"
        return Response(b"%PDF-1.7", media_type=media)

    @router.get("/api/v1/projects/{project_id}/compiles/{compile_id}/stream")
    async def stream(project_id: UUID, compile_id: str) -> StreamingResponse:  # noqa: ARG001
        async def events() -> AsyncIterator[str]:
            yield "data: line\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    app = FastAPI()
    app.include_router(router)
    app.add_middleware(SecurityHeadersMiddleware, frame_ancestors=["https://office.example.org"])
    install_exception_handlers(app)
    container = make_async_container(_Providers(sessions, users, acl), FastapiProvider())
    setup_dishka(container, app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield _Env(client, acl, users)
    await container.close()


_COOKIE = {"Cookie": f"hse_session={SECRET}"}


async def test__build_log_stream__cookie__opens_as_event_stream(env: _Env) -> None:
    response = await env.client.get(f"{_BASE}/compiles/c1/stream", headers=_COOKIE)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "data: line" in response.text


async def test__build_log_stream__anonymous__401(env: _Env) -> None:
    response = await env.client.get(f"{_BASE}/compiles/c1/stream")

    assert response.status_code == 401


async def test__pdf__cookie__inline_without_sandbox_and_framable_by_office(env: _Env) -> None:
    response = await env.client.get(f"{_BASE}/files/out/report.pdf", headers=_COOKIE)

    assert response.status_code == 200
    csp = response.headers["content-security-policy"]
    assert "sandbox" not in csp
    assert "frame-ancestors 'self' https://office.example.org" in csp
    assert response.headers["content-disposition"].startswith("inline")
    assert response.headers["x-content-type-options"] == "nosniff"


async def test__office_file__document_token_without_cookie__served(env: _Env) -> None:
    token = await env.token()

    response = await env.client.get(f"{_BASE}/files/{_FILE}", params={"office_token": token})

    assert response.status_code == 200
    assert response.headers["content-disposition"].startswith("attachment")


async def test__office_file__token_for_another_file__rejected(env: _Env) -> None:
    token = await env.token()

    response = await env.client.get(f"{_BASE}/files/secret.txt", params={"office_token": token})

    assert response.status_code == 401


async def test__office_file__callback_token_does_not_open_file(env: _Env) -> None:
    token = await env.token(purpose=OfficeTokenPurpose.callback)

    response = await env.client.get(f"{_BASE}/files/{_FILE}", params={"office_token": token})

    assert response.status_code == 401


async def test__office_file__revoked_member__rejected_before_token_expires(env: _Env) -> None:
    token = await env.token()
    env.acl.roles.clear()

    response = await env.client.get(f"{_BASE}/files/{_FILE}", params={"office_token": token})

    assert response.status_code == 401


async def test__office_token__does_not_open_other_routes(env: _Env) -> None:
    token = await env.token()

    response = await env.client.get(f"{_BASE}/compiles/c1/stream", params={"office_token": token})

    assert response.status_code == 401
