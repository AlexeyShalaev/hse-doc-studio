from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import APIRouter, Depends, FastAPI
from fastapi.routing import APIRoute, iter_route_contexts
from hse_doc_studio.api import guards, route_scopes
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.guards import install_exception_handlers, project_access_guard
from hse_doc_studio.api.route_actions import ROUTE_ACTIONS, RouteKey, route_key
from hse_doc_studio.api.route_scopes import (
    PER_USER_PENDING,
    ROUTE_SCOPES,
    RouteScope,
    per_user_routes_problem,
    scope_of_route_path,
)
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.mode import StudioMode
from httpx import ASGITransport, AsyncClient

from tests.fixtures.app import create_test_app, create_test_container

_SKIPPED_METHODS = frozenset({"HEAD", "OPTIONS"})
_PREFIXES = ("/api/v1", "/api/admin", "/api/runner/", "/api/services/", "/git/")
# Потолок общих пользовательских маршрутов: только уменьшается, когда срез переводит данные под владельца.
# Общих пользовательских маршрутов не осталось.
_PENDING_CEILING = 0
_USER = Actor.user("user")
_ADMIN = Actor(kind="user", id="admin", is_instance_admin=True)


def _app_route_keys(tmp_path: Path) -> set[RouteKey]:
    # Админка монтируется только на сервере: реестр сверяется с приложением, где она есть.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(settings, "mode", StudioMode.server)
        app = create_test_app(create_test_container(tmp_path / "data"))
    keys: set[RouteKey] = set()
    for ctx in iter_route_contexts(app.routes):
        if ctx.path.startswith(_PREFIXES) and isinstance(ctx.original_route, APIRoute):
            keys.update(route_key(m, ctx.path) for m in ctx.original_route.methods - _SKIPPED_METHODS)
    return keys


@pytest.fixture(scope="module")
def app_keys(tmp_path_factory: pytest.TempPathFactory) -> set[RouteKey]:
    return _app_route_keys(tmp_path_factory.mktemp("route-scopes"))


def test__route_scopes__every_route_is_classified_exactly_once(app_keys: set[RouteKey]) -> None:
    unclassified = sorted(app_keys - set(ROUTE_ACTIONS) - set(ROUTE_SCOPES))
    both = sorted(set(ROUTE_ACTIONS) & set(ROUTE_SCOPES))

    assert not unclassified, "Маршруты без записи ни в ROUTE_ACTIONS, ни в ROUTE_SCOPES:\n" + "\n".join(
        f"  {m} {p}" for m, p in unclassified
    )
    assert not both, f"Маршрут в двух таблицах сразу: {both}"


def test__route_scopes__no_stale_entries(app_keys: set[RouteKey]) -> None:
    stale = sorted(set(ROUTE_SCOPES) - app_keys)

    assert not stale, "В ROUTE_SCOPES остались записи без маршрута:\n" + "\n".join(f"  {m} {p}" for m, p in stale)


def test__route_scopes__scopes_are_known_and_only_authenticated_data_can_be_pending() -> None:
    assert set(ROUTE_SCOPES.values()) <= set(RouteScope)
    assert all(ROUTE_SCOPES[key] is RouteScope.authenticated for key in PER_USER_PENDING)


def test__route_scopes__pending_list_only_shrinks() -> None:
    assert len(PER_USER_PENDING) <= _PENDING_CEILING


def test__route_scopes__host_routes_are_local_only_and_settings_stay_authenticated() -> None:
    assert scope_of_route_path("GET", "/api/v1/fs/browse") is RouteScope.local_only
    assert scope_of_route_path("POST", "/api/v1/setup/apply") is RouteScope.local_only
    assert scope_of_route_path("POST", "/api/v1/projects/connect") is RouteScope.local_only
    # Клон пишет в папку, которую назвал клиент: на сервере такого маршрута нет
    assert scope_of_route_path("POST", "/api/v1/git/clone") is RouteScope.local_only
    assert scope_of_route_path("POST", "/api/v1/git/clone/bundle") is RouteScope.local_only
    assert scope_of_route_path("GET", "/api/v1/settings") is RouteScope.authenticated
    assert scope_of_route_path("POST", "/api/v1/data/export") is RouteScope.instance_admin
    assert scope_of_route_path("GET", "/api/v1/nope") is None


def test__per_user_routes_problem__red_while_pending_and_green_when_empty() -> None:
    assert per_user_routes_problem() is None
    assert per_user_routes_problem(frozenset({("GET", "/agent-personas")})) is not None


def test__per_user_routes_check__registered_for_server_start() -> None:
    from hse_doc_studio.api.config import Settings  # noqa: PLC0415
    from hse_doc_studio.api.entrypoint import ensure_supported_mode  # noqa: PLC0415
    from hse_doc_studio.core.readiness import ServerReadinessRegistry  # noqa: PLC0415

    registry = ServerReadinessRegistry()
    cfg = Settings(mode=StudioMode.server)

    with pytest.raises(RuntimeError) as err:
        ensure_supported_mode(cfg, registry)

    assert "per_user_routes" not in str(err.value)
    assert "persistence/database" in str(err.value)


def _stub(monkeypatch: pytest.MonkeyPatch, actor: Actor | None, *, server: bool = True) -> None:
    async def resolve(_request: object) -> Actor:
        if actor is None:
            raise IdentityError(IdentityErrorCode.auth_required)
        return actor

    monkeypatch.setattr(guards, "resolve_actor", resolve)
    monkeypatch.setattr(guards, "settings", SimpleNamespace(mode=StudioMode.server if server else StudioMode.local))


@pytest_asyncio.fixture
async def real_client(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    container = create_test_container(tmp_path / "data")
    async with AsyncClient(transport=ASGITransport(app=create_test_app(container)), base_url="http://test") as client:
        yield client
    await container.close()


@pytest.mark.parametrize(
    ("actor", "method", "path", "status"),
    [
        (None, "GET", "/api/v1/catalog/packs", 401),
        (None, "GET", "/api/v1/fs/browse", 404),
        (None, "POST", "/api/v1/data/export", 401),
        (_USER, "GET", "/api/v1/fs/browse", 404),
        (_USER, "POST", "/api/v1/setup/apply", 404),
        (_USER, "GET", "/api/v1/ai-runtime/status", 404),
        (_USER, "POST", "/api/v1/data/export", 403),
        (_USER, "PUT", "/api/v1/fonts/a.ttf", 403),
        (_ADMIN, "GET", "/api/v1/fs/browse", 404),
        (_ADMIN, "GET", "/api/v1/ai-runtime/status", 404),
    ],
    ids=lambda v: v if isinstance(v, str | int) else getattr(v, "id", "anon"),
)
async def test__matrix__server_mode_real_routes(
    real_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    actor: Actor | None,
    method: str,
    path: str,
    status: int,
) -> None:
    _stub(monkeypatch, actor)

    assert (await real_client.request(method, path)).status_code == status


async def test__matrix__authenticated_and_admin_pass_the_guard(
    real_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub(monkeypatch, _USER)
    assert (await real_client.get("/api/v1/system/archive-formats")).status_code == 200

    _stub(monkeypatch, _ADMIN)
    assert (await real_client.get("/api/v1/system/archive-formats")).status_code == 200
    assert (await real_client.put("/api/v1/fonts/a.ttf")).status_code not in {401, 403, 404}


def _scoped_app() -> FastAPI:
    router = APIRouter(prefix="/api/v1", dependencies=[Depends(project_access_guard)])
    for name in ("pub", "runner", "job", "signed", "me", "admin", "org", "host", "unknown"):

        @router.get(f"/{name}", name=name)
        async def _ok() -> dict[str, bool]:
            return {"ok": True}

    app = FastAPI()
    app.include_router(router)
    install_exception_handlers(app)
    return app


@pytest.mark.parametrize(
    ("actor", "path", "status"),
    [
        (None, "/api/v1/pub", 200),
        (None, "/api/v1/runner", 200),
        (None, "/api/v1/job", 200),
        (None, "/api/v1/signed", 200),
        (None, "/api/v1/me", 401),
        (_USER, "/api/v1/me", 200),
        (_USER, "/api/v1/admin", 403),
        (_ADMIN, "/api/v1/admin", 200),
        (_USER, "/api/v1/org", 404),
        (_ADMIN, "/api/v1/org", 200),
        (_USER, "/api/v1/host", 404),
        (None, "/api/v1/host", 404),
        (_USER, "/api/v1/unknown", 403),
        (_ADMIN, "/api/v1/unknown", 403),
    ],
    ids=lambda v: v if isinstance(v, str | int) else getattr(v, "id", "anon"),
)
async def test__matrix__every_scope_on_server(
    monkeypatch: pytest.MonkeyPatch, actor: Actor | None, path: str, status: int
) -> None:
    _stub(monkeypatch, actor)
    scopes = {
        ("GET", "/pub"): RouteScope.public,
        ("GET", "/runner"): RouteScope.runner_token,
        ("GET", "/job"): RouteScope.job_token,
        ("GET", "/signed"): RouteScope.signed_token,
        ("GET", "/me"): RouteScope.authenticated,
        ("GET", "/admin"): RouteScope.instance_admin,
        ("GET", "/org"): RouteScope.org_admin,
        ("GET", "/host"): RouteScope.local_only,
    }
    monkeypatch.setattr(route_scopes, "ROUTE_SCOPES", scopes)

    async with AsyncClient(transport=ASGITransport(app=_scoped_app()), base_url="http://test") as client:
        assert (await client.get(path)).status_code == status


async def test__matrix__local_mode_ignores_scopes(monkeypatch: pytest.MonkeyPatch, real_client: AsyncClient) -> None:
    monkeypatch.setattr(guards, "settings", SimpleNamespace(mode=StudioMode.local))

    assert (await real_client.get("/api/v1/system/archive-formats")).status_code == 200
    assert (await real_client.get("/api/v1/fs/browse", params={"path": str(Path.home())})).status_code != 404
