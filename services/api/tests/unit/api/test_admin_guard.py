"""Гард `/api/admin`: админ-сессия проходит, токен доступа админа и обычный пользователь получают 404."""

from __future__ import annotations

import pytest
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.routers import admin
from hse_doc_studio.core.access.context import set_current_actor
from hse_doc_studio.core.access.entities import Actor, ActorSource
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.mode import StudioMode


@pytest.fixture(autouse=True)
def _server(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "mode", StudioMode.server)
    monkeypatch.setattr(admin, "admin_request_allowed", lambda _request: True)
    yield
    set_current_actor(None)


def _resolving(monkeypatch: pytest.MonkeyPatch, actor: Actor) -> None:
    async def resolve(_request: object) -> Actor:
        return actor

    monkeypatch.setattr(admin, "resolve_actor", resolve)


async def test__session_admin__passes(monkeypatch: pytest.MonkeyPatch) -> None:
    _resolving(monkeypatch, Actor.user("boss", is_instance_admin=True, source=ActorSource.session))

    await admin.admin_guard(object())  # type: ignore[arg-type]


@pytest.mark.parametrize("source", [ActorSource.pat, ActorSource.link])
async def test__admin_with_a_token_instead_of_a_session__gets_404(
    monkeypatch: pytest.MonkeyPatch, source: ActorSource
) -> None:
    _resolving(
        monkeypatch,
        Actor.user("boss", is_instance_admin=True, source=source, scopes=frozenset({"api"})),
    )

    with pytest.raises(IdentityError) as caught:
        await admin.admin_guard(object())  # type: ignore[arg-type]
    assert caught.value.code is IdentityErrorCode.not_found
