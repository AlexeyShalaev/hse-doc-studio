from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.routing import APIRoute, iter_route_contexts
from hse_doc_studio.api.route_actions import ROUTE_ACTIONS, RouteKey, route_key
from hse_doc_studio.core.access.actions import Action, RouteExemption
from pydantic import BaseModel

from tests.fixtures.app import create_test_app, create_test_container

_PROJECT_FIELD = "project_id"
_SKIPPED_METHODS = frozenset({"HEAD", "OPTIONS"})
# Действия, у которых пока нет ни одного маршрута.
_RESERVED_ACTIONS = frozenset({Action.COMMENT, Action.SHARE, Action.PROJECT_TRANSFER})
_WRITE_ACTIONS = frozenset(
    {
        Action.FILES_WRITE,
        Action.HISTORY_WRITE,
        Action.HISTORY_REWRITE,
        Action.PROJECT_SETTINGS,
        Action.TEMPLATE_MANAGE,
        Action.PROJECT_DELETE,
        Action.SUBMISSION_CREATE,
    }
)
# GET, который требует записи: открывает сессию редактирования или показывает владельцу то, что остальным закрыто
# (подбор людей и групп для панели «Доступ» не должен подсказывать список людей читателю).
_GET_WITH_WRITE = frozenset(
    {
        ("GET", "/projects/{project_id}/documents/{doc_id}/office-editor"),
        ("GET", "/projects/{project_id}/members/candidates"),
    }
)


@dataclass(frozen=True)
class _AppRoute:
    key: RouteKey
    path_params: frozenset[str]
    project_source: str | None


def _body_has_project(route: APIRoute) -> bool:
    for param in route.dependant.body_params:
        model = param.field_info.annotation
        if param.name == _PROJECT_FIELD:
            return True
        if isinstance(model, type) and issubclass(model, BaseModel) and _PROJECT_FIELD in model.model_fields:
            return True
    return False


def _project_source(route: APIRoute) -> str | None:
    dependant = route.dependant
    if _PROJECT_FIELD in {p.name for p in dependant.path_params}:
        return "path"
    if _PROJECT_FIELD in {p.name for p in dependant.query_params}:
        return "query"
    return "body" if _body_has_project(route) else None


def _api_routes(tmp_path: Path) -> list[_AppRoute]:
    app = create_test_app(create_test_container(tmp_path / "data"))
    routes: list[_AppRoute] = []
    for ctx in iter_route_contexts(app.routes):
        route = ctx.original_route
        if not ctx.path.startswith("/api/v1") or not isinstance(route, APIRoute):
            continue
        for method in sorted(route.methods - _SKIPPED_METHODS):
            routes.append(
                _AppRoute(
                    key=route_key(method, ctx.path),
                    path_params=frozenset(p.name for p in route.dependant.path_params),
                    project_source=_project_source(route),
                )
            )
    return routes


@pytest.fixture(scope="module")
def app_routes(tmp_path_factory: pytest.TempPathFactory) -> list[_AppRoute]:
    return _api_routes(tmp_path_factory.mktemp("route-table"))


@pytest.fixture(scope="module")
def project_routes(app_routes: list[_AppRoute]) -> dict[RouteKey, _AppRoute]:
    return {r.key: r for r in app_routes if r.project_source is not None}


def test__route_table__every_project_route_has_entry(project_routes: dict[RouteKey, _AppRoute]) -> None:
    missing = sorted(set(project_routes) - set(ROUTE_ACTIONS))

    assert not missing, (
        "У маршрутов проекта нет записи в ROUTE_ACTIONS. Добавьте в hse_doc_studio/api/route_actions.py:\n"
        + "\n".join(f"  {method} {path}" for method, path in missing)
    )


def test__route_table__no_stale_entries(app_routes: list[_AppRoute]) -> None:
    existing = {r.key for r in app_routes}

    stale = sorted(set(ROUTE_ACTIONS) - existing)

    assert not stale, (
        "В ROUTE_ACTIONS остались записи без маршрута (переименован или удалён). Уберите их:\n"
        + "\n".join(f"  {method} {path}" for method, path in stale)
    )


def test__route_table__project_source_matches_route(project_routes: dict[RouteKey, _AppRoute]) -> None:
    wrong = sorted(
        (key, rule.project_source, project_routes[key].project_source)
        for key, rule in ROUTE_ACTIONS.items()
        if key in project_routes and rule.project_source != project_routes[key].project_source
    )

    assert not wrong, f"project_source не совпадает с маршрутом: {wrong}"


def test__route_table__only_callback_is_system_callback() -> None:
    exempt = {key for key, rule in ROUTE_ACTIONS.items() if isinstance(rule.action, RouteExemption)}

    assert exempt == {("POST", "/office-editor/callback")}


@pytest.mark.parametrize(
    "key",
    sorted(k for k in ROUTE_ACTIONS if k[0] == "GET" and k not in _GET_WITH_WRITE),
    ids=lambda key: key[1],
)
def test__route_table__get_routes_do_not_need_write_actions(key: RouteKey) -> None:
    assert ROUTE_ACTIONS[key].action not in _WRITE_ACTIONS


def test__route_table__path_param_exists_in_route(app_routes: list[_AppRoute]) -> None:
    params_by_key = {r.key: r.path_params for r in app_routes}

    wrong = sorted(
        (key, rule.path_param)
        for key, rule in ROUTE_ACTIONS.items()
        if rule.path_param is not None and rule.path_param not in params_by_key.get(key, frozenset())
    )

    assert not wrong, f"path_param не входит в параметры пути маршрута: {wrong}"


def test__route_table__every_non_reserved_action_is_used() -> None:
    used = {rule.action for rule in ROUTE_ACTIONS.values()}

    assert set(Action) - _RESERVED_ACTIONS - used == set()


def test__route_key__strips_api_prefix_and_leaves_relative_path_unchanged() -> None:
    assert route_key("put", "/api/v1/projects/{project_id}/files/{path:path}") == (
        "PUT",
        "/projects/{project_id}/files/{path:path}",
    )
    assert route_key("GET", "/projects/{project_id}") == ("GET", "/projects/{project_id}")


def test__scope_for_rule__file_path_as_is_instance_id_by_author() -> None:
    from hse_doc_studio.api.route_actions import RouteRule, scope_for_rule  # noqa: PLC0415
    from hse_doc_studio.core.access.actions import Action  # noqa: PLC0415

    assert (
        scope_for_rule(RouteRule(Action.FILES_WRITE, path_param="path"), {"path": "alex/main.tex"}) == "alex/main.tex"
    )
    assert scope_for_rule(RouteRule(Action.FILES_WRITE, path_param="doc_id"), {"doc_id": "vkr--alex"}) == "alex"
    assert scope_for_rule(RouteRule(Action.FILES_WRITE, path_param="slot_id"), {"slot_id": "sig"}) is None
    assert scope_for_rule(RouteRule(Action.SIGN, path_param="slot_id"), {"slot_id": "sig--alex"}) == "sig--alex"
    assert scope_for_rule(RouteRule(Action.FILES_WRITE), {"path": "x"}) is None
