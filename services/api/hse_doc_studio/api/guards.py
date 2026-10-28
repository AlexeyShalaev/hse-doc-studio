"""Запрет записи в проект, который эта Студия может только смотреть (core.project_access).

Гард висит на всём `/api/v1` и срабатывает на любой изменяющий запрос с
`project_id` в пути: так ограничение не обходят ни интерфейс, ни агент, ни
сборка (она тоже запускается запросом). Чтение не трогается. Последний рубеж —
репозитории состояния (infra.persistence.project.assert_project_writable).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from hse_doc_studio.api.actor import resolve_actor
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.git_errors import install_git_error_handlers
from hse_doc_studio.api.identity_errors import install_identity_error_handlers
from hse_doc_studio.api.route_actions import rule_for, scope_for_rule
from hse_doc_studio.api.route_scopes import (
    ADMIN_PREFIX,
    SELF_AUTHENTICATED,
    RouteScope,
    route_path_of,
    scope_for_request,
)
from hse_doc_studio.core.access.actions import RouteExemption
from hse_doc_studio.core.access.context import set_current_actor
from hse_doc_studio.core.access.entities import Actor, ProjectAcl
from hse_doc_studio.core.access.policy import Decision, decide
from hse_doc_studio.core.enums import ProjectAccessMode, ProjectAccessReason
from hse_doc_studio.core.errors import NotFoundError, ProjectReadOnlyError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.core.project_access import ProjectAccess
from hse_doc_studio.use_cases.projects.get_project_access import GetProjectAccessInput, GetProjectAccessUC

_READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
# Записи, разрешённые и в режиме «только чтение»: вернуть проект к снимку из
# истории (единственный выход для данных более новой Студии) и убрать проект
# из списка. Предпросмотр CI тоже ничего не пишет: это POST только ради тела запроса.
# Выборка из удалённого репозитория не трогает файлы проекта, поэтому «только чтение» ей не помеха.
_ALLOWED_SUFFIXES = ("/vcs/restore", "/git/ci/preview", "/git/fetch")
_LOCKED = 423
_FORBIDDEN = 403
_NOT_FOUND = 404


def _allowed(request: Request) -> bool:
    # Сверяется шаблон найденного маршрута, а не адрес запроса: в адресе `files/{path:path}` лежит произвольный
    # путь файла, и `a/git/fetch` или `projects/<id>` в его конце не должны снимать запрет записи.
    route_path = str(getattr(request.scope.get("route"), "path", ""))
    if request.method == "DELETE" and route_path.endswith("/projects/{project_id}"):
        return True
    return route_path.endswith(_ALLOWED_SUFFIXES)


def access_detail(access: ProjectAccess) -> dict[str, Any]:
    if ProjectAccessReason.update_in_progress in access.reasons:
        message = localized_error(
            "Идёт обновление шаблона проекта — изменения временно недоступны.",
            "The project template is being updated — changes are temporarily unavailable.",
        )
    elif access.mode == ProjectAccessMode.files_only or access.required_studio:
        required = access.required_studio or "?"
        message = localized_error(
            f"Проект сохранён более новой версией Студии (нужна {required}): здесь он открыт только для чтения.",
            f"The project was saved by a newer Studio (needs {required}): it is read-only here.",
        )
    else:
        message = localized_error(
            "Проект открыт только для чтения.",
            "The project is read-only.",
        )
    # Форма как у прочих структурированных ошибок: клиент берёт `detail` и `code`.
    return {
        "detail": message,
        "code": "project_read_only",
        "mode": access.mode.value,
        "reasons": [r.value for r in access.reasons],
        "required_studio": access.required_studio,
    }


async def load_project_acl(_request: Request, _project_id: str) -> ProjectAcl | None:
    """Членство проекта. Хранилище членств появится на втором этапе, до него сюда не дойти."""
    msg = "project membership storage is not implemented (stage 2 of collaboration)"
    raise NotImplementedError(msg)


async def project_access_guard(request: Request) -> None:
    """Проверка прав актора на маршрут по таблицам `api.route_actions` и `api.route_scopes`.

    Кладёт актора в контекст запроса для всего `/api/v1`. Локальный актор уходит
    сразу, без обращения к контейнеру зависимостей и без чтения проекта: часть
    тестов собирает свои приложения вокруг `api_router`, а локальный режим не
    должен менять поведение. На сервере до цепочки cookie обрабатываются маршруты,
    которым актор не нужен: публичные, с собственным токеном (раннер, задача,
    подписанная ссылка) и только локальные (им отвечаем 404). Остальным отказ по
    умолчанию: маршрут без записи ни в одной таблице не открывается никому.
    Гард стоит перед `project_write_guard`, чтобы чужой получил 404, а не 423.
    """
    if settings.mode is not StudioMode.local and _handled_before_actor(request):
        return
    actor = await resolve_actor(request)
    set_current_actor(actor)
    if actor.is_local:
        return
    rule = rule_for(request)
    project_id = request.path_params.get("project_id")
    if rule is None:
        _enforce_scope(actor, request)
        if project_id is not None:
            raise HTTPException(status_code=_FORBIDDEN, detail="Forbidden")
        return
    if isinstance(rule.action, RouteExemption):
        return
    if project_id is None:
        # project_id в теле или query: право проверит сценарий, когда прочитает запрос.
        raise HTTPException(status_code=_FORBIDDEN, detail="Forbidden")
    acl = await load_project_acl(request, str(project_id))
    _enforce(decide(actor, rule.action, acl, scope_for_rule(rule, request.path_params)))


def _handled_before_actor(request: Request) -> bool:
    """True, если запросу не нужен актор по cookie; локальные маршруты на сервере не существуют."""
    scope = scope_for_request(request)
    if scope is RouteScope.local_only:
        raise HTTPException(status_code=_NOT_FOUND, detail="Not Found")
    return scope is RouteScope.public or scope in SELF_AUTHENTICATED


def _enforce_scope(actor: Actor, request: Request) -> None:
    scope = scope_for_request(request)
    if scope is None:
        raise HTTPException(status_code=_FORBIDDEN, detail="Forbidden")
    if scope is RouteScope.local_only:
        raise HTTPException(status_code=_NOT_FOUND, detail="Not Found")
    if scope in {RouteScope.instance_admin, RouteScope.org_admin} and not actor.is_instance_admin:
        # Админка не должна выдавать себя чужому: нет прав, значит нет и маршрута.
        if scope is RouteScope.org_admin or route_path_of(request).startswith(ADMIN_PREFIX):
            raise HTTPException(status_code=_NOT_FOUND, detail="Not Found")
        raise HTTPException(status_code=_FORBIDDEN, detail="Forbidden")


def _enforce(decision: Decision) -> None:
    if decision is Decision.not_found:
        raise HTTPException(status_code=_NOT_FOUND, detail="Project not found")
    if decision is Decision.forbidden:
        raise HTTPException(status_code=_FORBIDDEN, detail="Forbidden")


async def project_write_guard(request: Request) -> None:
    if request.method in _READ_METHODS:
        return
    raw_id = request.path_params.get("project_id")
    if raw_id is None or _allowed(request):
        return
    try:
        project_id = UUID(str(raw_id))
    except ValueError:
        return
    uc = await request.state.dishka_container.get(GetProjectAccessUC)
    try:
        result = await uc.execute(GetProjectAccessInput(project_id=project_id))
    except NotFoundError:
        return  # 404 отдаст сам эндпоинт
    if not result.access.writable:
        raise HTTPException(status_code=_LOCKED, detail=access_detail(result.access))


async def _read_only_handler(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=_LOCKED, content={"detail": str(exc)})


def install_exception_handlers(app: FastAPI) -> None:
    """Ошибки домена, общие для всех роутеров (в create_app и в тестовом приложении)."""
    app.add_exception_handler(ProjectReadOnlyError, _read_only_handler)
    install_git_error_handlers(app)
    install_identity_error_handlers(app)
