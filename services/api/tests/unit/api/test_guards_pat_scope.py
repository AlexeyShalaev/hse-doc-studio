"""Админские маршруты /api/v1 не открываются токеном доступа админа, как и /api/admin."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from hse_doc_studio.api import guards
from hse_doc_studio.api.route_scopes import RouteScope
from hse_doc_studio.core.access.entities import Actor, ActorSource
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode


def _request() -> SimpleNamespace:
    return SimpleNamespace(scope={"route": SimpleNamespace(path="/api/v1/trusted-roots")}, method="POST")


@pytest.mark.parametrize("scope", [RouteScope.instance_admin, RouteScope.org_admin])
def test__enforce_scope__admin_session__passes(monkeypatch: pytest.MonkeyPatch, scope: RouteScope) -> None:
    monkeypatch.setattr(guards, "scope_for_request", lambda _r: scope)
    admin = Actor.user("boss", is_instance_admin=True, source=ActorSource.session)

    guards._enforce_scope(admin, _request())  # type: ignore[arg-type]


@pytest.mark.parametrize("scope", [RouteScope.instance_admin, RouteScope.org_admin])
def test__enforce_scope__admin_pat__rejected(monkeypatch: pytest.MonkeyPatch, scope: RouteScope) -> None:
    monkeypatch.setattr(guards, "scope_for_request", lambda _r: scope)
    admin = Actor.user("boss", is_instance_admin=True, source=ActorSource.pat, scopes=frozenset({"api"}))

    with pytest.raises(IdentityError) as caught:
        guards._enforce_scope(admin, _request())  # type: ignore[arg-type]
    assert caught.value.code in {IdentityErrorCode.forbidden, IdentityErrorCode.not_found}
