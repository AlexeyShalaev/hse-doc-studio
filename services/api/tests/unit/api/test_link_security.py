"""Ссылки доступа на уровне API: Referrer-Policy, маска токена в журнале, cookie гостя, гостевой резолвер."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import Response
from hse_doc_studio.api.auth_cookie import (
    clear_guest_cookie,
    credentials_from_request,
    guest_cookie_name,
    set_guest_cookie,
)
from hse_doc_studio.api.logging_setup import LinkTokenMaskFilter, mask_link_tokens
from hse_doc_studio.api.security_headers import SecurityHeadersMiddleware
from hse_doc_studio.core.access.entities import ActorKind
from hse_doc_studio.core.access.links import GuestLink, GuestSession, hash_secret
from hse_doc_studio.core.identity.entities import ActorCredentials
from hse_doc_studio.infra.identity.guest_resolver import GuestSessionResolver
from hse_doc_studio.use_cases.sharing.open_link import GuestSessionService
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.unit

TOKEN = "hsl_bG9uZ1JhbmRvbVRva2VuRXhhbXBsZVZhbHVlMDE"


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/s/{token}")
    async def page(token: str) -> Response:  # noqa: ARG001
        return Response("<html></html>", media_type="text/html")

    @app.get("/api/v1/links/{token}")
    async def preview(token: str) -> dict[str, str]:  # noqa: ARG001
        return {"state": "ok"}

    @app.get("/api/v1/other")
    async def other() -> dict[str, int]:
        return {"a": 1}

    @app.get("/creds")
    async def creds(request: Request) -> dict[str, str | None]:
        return {"guest": credentials_from_request(request, secure=False).guest_secret}

    app.add_middleware(SecurityHeadersMiddleware)
    return app


async def test__referrer_policy__no_referrer_on_link_pages() -> None:
    async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://t") as client:
        page = await client.get(f"/s/{TOKEN}")
        api = await client.get(f"/api/v1/links/{TOKEN}")
        other = await client.get("/api/v1/other")

    assert page.headers["Referrer-Policy"] == "no-referrer"
    assert api.headers["Referrer-Policy"] == "no-referrer"
    assert other.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


async def test__credentials__read_guest_cookie() -> None:
    async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://t") as client:
        client.cookies.set("hse_guest", "secret-1")
        got = (await client.get("/creds")).json()

    assert got == {"guest": "secret-1"}


def test__mask_link_tokens__in_text_and_access_log() -> None:
    assert mask_link_tokens(f"GET /s/{TOKEN} 200") == "GET /s/hsl_**** 200"
    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s "%s %s"', ("ip", "GET", f"/s/{TOKEN}"), None)

    LinkTokenMaskFilter().filter(record)

    assert TOKEN not in record.getMessage()
    assert "hsl_****" in record.getMessage()


def test__guest_cookie__name_and_attributes() -> None:
    assert guest_cookie_name(secure=True) == "__Host-hse_guest"
    assert guest_cookie_name(secure=False) == "hse_guest"
    response = Response()
    set_guest_cookie(response, "s", secure=True, max_age_s=60)
    header = response.headers["set-cookie"].lower()
    assert "__host-hse_guest=s" in header
    assert "httponly" in header
    assert "secure" in header
    assert "samesite=lax" in header
    cleared = Response()
    clear_guest_cookie(cleared, secure=True)
    assert len(cleared.headers.getlist("set-cookie")) == 2


class _Guests:
    def __init__(self) -> None:
        self.sessions: dict[str, GuestSession] = {}
        self.touched: list[str] = []

    async def get_by_secret_hash(self, secret_hash: str, now: datetime) -> GuestSession | None:
        session = self.sessions.get(secret_hash)
        return session if session is not None and session.expires_at > now else None

    async def touch(self, session_id: str, now: datetime, expires_at: datetime) -> None:  # noqa: ARG002
        self.touched.append(session_id)

    async def create(self, session: GuestSession, secret_hash: str, ip: str | None, user_agent: str) -> None:  # noqa: ARG002
        self.sessions[secret_hash] = session

    async def links_of(self, session_id: str) -> list[GuestLink]:  # noqa: ARG002
        return []


NOW = datetime(2026, 11, 1, tzinfo=UTC)


def _session(*, last_seen: datetime = NOW, expires: datetime = NOW + timedelta(days=30)) -> GuestSession:
    return GuestSession(
        id="gs_1", name="Борис", created_at=NOW, last_seen_at=last_seen, expires_at=expires, csrf_token="c"
    )


async def test__guest_resolver__no_cookie_expired_and_bearer() -> None:
    guests = _Guests()
    guests.sessions[hash_secret("live")] = _session(last_seen=NOW - timedelta(hours=1))
    guests.sessions[hash_secret("old")] = _session(expires=NOW - timedelta(seconds=1))
    resolver = GuestSessionResolver(GuestSessionService(guests, clock=lambda: NOW))  # type: ignore[arg-type]

    assert await resolver.resolve(ActorCredentials()) is None
    assert await resolver.resolve(ActorCredentials(guest_secret="old")) is None
    assert await resolver.resolve(ActorCredentials(guest_secret="live", bearer_token="hsp_x")) is None
    actor = await resolver.resolve(ActorCredentials(guest_secret="live"))
    assert actor is not None
    assert actor.kind is ActorKind.guest
    assert (actor.id, actor.name, actor.key) == ("gs_1", "Борис", "guest:gs_1")
    assert guests.touched == ["gs_1"]


async def test__guest_session_service__create_sets_sliding_expiry() -> None:
    guests = _Guests()
    service = GuestSessionService(guests, lifetime=timedelta(days=30), clock=lambda: NOW)  # type: ignore[arg-type]

    session, secret = await service.create("Борис", "127.0.0.1", "ua")

    assert session.id.startswith("gs_")
    assert session.expires_at == NOW + timedelta(days=30)
    assert await service.resolve(secret) == session
