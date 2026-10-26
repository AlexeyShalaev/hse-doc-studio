"""Таблица «маршрут -> действие»: единственное место, где сказано, что требует каждый маршрут проекта.

Ключ — `(МЕТОД, шаблон пути без /api/v1)`. Таблица явная, без вывода из имён: тест
`tests/integration/api/access/test_route_actions.py` сверяет её с настоящими маршрутами
приложения и падает, если у нового маршрута проекта нет записи. Сами решения
принимает `core.access.policy`, здесь только соответствие.

`path_param` называет параметр пути запроса, из которого берётся область проверки:
путь файла (`path`) или идентификатор документа, формы, слота (`doc_id`, `form_id`,
`slot_id`), по которому находится автор. Если путь лежит в теле запроса, он None.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from fastapi import Request

from hse_doc_studio.core.access.actions import Action, RouteExemption
from hse_doc_studio.core.access.paths import scope_path_of_instance_id

API_PREFIX = "/api/v1"

ProjectSource = Literal["path", "query", "body"]


@dataclass(frozen=True, slots=True)
class RouteRule:
    action: Action | RouteExemption
    path_param: str | None = None
    # Где у маршрута лежит project_id: в пути, в query или в теле запроса.
    project_source: ProjectSource = "path"


RouteKey = tuple[str, str]

# Параметры пути, в которых лежит id экземпляра `<база>--<автор>`, а не путь файла.
INSTANCE_ID_PARAMS = frozenset({"doc_id", "form_id", "slot_id"})


def route_key(method: str, path: str) -> RouteKey:
    return method.upper(), path.removeprefix(API_PREFIX)


ROUTE_ACTIONS: Mapping[RouteKey, RouteRule] = {
    # Проект и его описание
    ("GET", "/projects/{project_id}"): RouteRule(Action.PROJECT_VIEW),
    ("GET", "/projects/{project_id}/nda"): RouteRule(Action.PROJECT_VIEW),
    ("GET", "/projects/{project_id}/documents"): RouteRule(Action.PROJECT_VIEW),
    ("GET", "/projects/{project_id}/documents/{doc_id}"): RouteRule(Action.PROJECT_VIEW),
    ("GET", "/projects/{project_id}/requirements"): RouteRule(Action.PROJECT_VIEW),
    ("GET", "/projects/{project_id}/template-update"): RouteRule(Action.PROJECT_VIEW),
    ("GET", "/projects/{project_id}/submissions/profiles"): RouteRule(Action.PROJECT_VIEW),
    # Результат сборки: PDF, ход и проверки (доступно и читателю без исходников)
    ("GET", "/projects/{project_id}/compiles/{compile_id}/stream"): RouteRule(Action.OUTPUT_READ),
    ("GET", "/projects/{project_id}/documents/{doc_id}/checks"): RouteRule(Action.OUTPUT_READ),
    ("GET", "/projects/{project_id}/documents/{doc_id}/compiles"): RouteRule(Action.OUTPUT_READ),
    ("GET", "/projects/{project_id}/documents/{doc_id}/compiles/{compile_id}"): RouteRule(Action.OUTPUT_READ),
    ("GET", "/projects/{project_id}/documents/{doc_id}/compiles/{compile_id}/pdf"): RouteRule(Action.OUTPUT_READ),
    ("GET", "/projects/{project_id}/checks/rules"): RouteRule(Action.OUTPUT_READ),
    ("GET", "/projects/{project_id}/documents/{doc_id}/checks/rules"): RouteRule(Action.OUTPUT_READ),
    ("GET", "/projects/{project_id}/normcontrol-report"): RouteRule(Action.OUTPUT_READ),
    ("GET", "/projects/{project_id}/signatures"): RouteRule(Action.OUTPUT_READ),
    ("GET", "/projects/{project_id}/docs/{doc_id}/frozen/pdf"): RouteRule(Action.OUTPUT_READ),
    ("GET", "/projects/{project_id}/docs/{doc_id}/pdf/signed"): RouteRule(Action.OUTPUT_READ),
    ("GET", "/projects/{project_id}/docs/{doc_id}/detached/{slot_id}/file"): RouteRule(Action.OUTPUT_READ),
    # Исходники: читателю только с show_sources
    ("GET", "/projects/{project_id}/files"): RouteRule(Action.SOURCES_READ),
    ("GET", "/projects/{project_id}/forms"): RouteRule(Action.SOURCES_READ),
    ("GET", "/projects/{project_id}/forms/{form_id}"): RouteRule(Action.SOURCES_READ),
    ("GET", "/projects/{project_id}/forms/{form_id}/preview"): RouteRule(Action.SOURCES_READ),
    ("GET", "/projects/{project_id}/changelog"): RouteRule(Action.SOURCES_READ),
    ("GET", "/projects/{project_id}/documents/{doc_id}/synctex/forward"): RouteRule(Action.SOURCES_READ),
    # Обратный поиск выдаёт позиции в исходнике, поэтому это чтение исходников, а не PDF.
    ("GET", "/projects/{project_id}/documents/{doc_id}/synctex/inverse"): RouteRule(Action.SOURCES_READ),
    ("GET", "/projects/{project_id}/template-update/diff"): RouteRule(Action.SOURCES_READ),
    ("GET", "/projects/{project_id}/template/compare"): RouteRule(Action.SOURCES_READ),
    ("GET", "/projects/{project_id}/vcs/status"): RouteRule(Action.SOURCES_READ),
    ("GET", "/projects/{project_id}/vcs/history"): RouteRule(Action.SOURCES_READ),
    ("GET", "/projects/{project_id}/vcs/commits/{commit_id}"): RouteRule(Action.SOURCES_READ),
    ("GET", "/projects/{project_id}/vcs/diff"): RouteRule(Action.SOURCES_READ),
    ("GET", "/projects/{project_id}/vcs/branches"): RouteRule(Action.SOURCES_READ),
    ("GET", "/projects/{project_id}/vcs/tags"): RouteRule(Action.SOURCES_READ),
    ("GET", "/projects/{project_id}/vcs/settings"): RouteRule(Action.SOURCES_READ),
    # Файл по пути: PDF, лог и PNG подписи читает и читатель, исходник нет (access.paths)
    ("GET", "/projects/{project_id}/files/{path:path}"): RouteRule(Action.FILES_READ, path_param="path"),
    ("GET", "/projects/{project_id}/file-version/{path:path}"): RouteRule(Action.FILES_READ, path_param="path"),
    # Правки файлов и документов (в team-проекте автор пишет в свою папку)
    ("PUT", "/projects/{project_id}/files/{path:path}"): RouteRule(Action.FILES_WRITE, path_param="path"),
    ("DELETE", "/projects/{project_id}/files/{path:path}"): RouteRule(Action.FILES_WRITE, path_param="path"),
    ("POST", "/projects/{project_id}/file-ops/move"): RouteRule(Action.FILES_WRITE),
    ("POST", "/projects/{project_id}/file-ops/mkdir"): RouteRule(Action.FILES_WRITE),
    ("PATCH", "/projects/{project_id}/documents/{doc_id}"): RouteRule(Action.FILES_WRITE, path_param="doc_id"),
    ("POST", "/projects/{project_id}/documents/{doc_id}/custom-file"): RouteRule(
        Action.FILES_WRITE, path_param="doc_id"
    ),
    ("DELETE", "/projects/{project_id}/documents/{doc_id}/custom-file"): RouteRule(
        Action.FILES_WRITE, path_param="doc_id"
    ),
    ("PUT", "/projects/{project_id}/forms/{form_id}"): RouteRule(Action.FILES_WRITE, path_param="form_id"),
    ("POST", "/projects/{project_id}/changelog"): RouteRule(Action.FILES_WRITE),
    ("POST", "/projects/{project_id}/checks/apply-fix"): RouteRule(Action.FILES_WRITE),
    # GET, но открывает сессию редактирования, поэтому это запись.
    ("GET", "/projects/{project_id}/documents/{doc_id}/office-editor"): RouteRule(
        Action.FILES_WRITE, path_param="doc_id"
    ),
    ("POST", "/projects/{project_id}/documents/{doc_id}/office-editor/touch"): RouteRule(
        Action.FILES_WRITE, path_param="doc_id"
    ),
    ("PATCH", "/projects/{project_id}/signatures/placements/{doc_id}/{slot_id}"): RouteRule(
        Action.FILES_WRITE, path_param="slot_id"
    ),
    ("PATCH", "/projects/{project_id}/signatures/slots/{slot_id}/config"): RouteRule(
        Action.FILES_WRITE, path_param="slot_id"
    ),
    ("POST", "/projects/{project_id}/docs/{doc_id}/frozen"): RouteRule(Action.FILES_WRITE, path_param="doc_id"),
    ("DELETE", "/projects/{project_id}/docs/{doc_id}/frozen"): RouteRule(Action.FILES_WRITE, path_param="doc_id"),
    ("POST", "/projects/{project_id}/docs/{doc_id}/detached/{slot_id}/recheck"): RouteRule(
        Action.FILES_WRITE, path_param="slot_id"
    ),
    # Сборка и проверки
    ("POST", "/projects/{project_id}/documents/{doc_id}/compile"): RouteRule(Action.BUILD_RUN),
    ("POST", "/projects/{project_id}/compiles/{compile_id}/cancel"): RouteRule(Action.BUILD_RUN),
    ("POST", "/projects/{project_id}/documents/{doc_id}/checks/run"): RouteRule(Action.BUILD_RUN),
    # Агент. POST /agent/chats несёт project_id в теле; чаты по session_id разбираются позже.
    ("POST", "/agent/chats"): RouteRule(Action.AGENT_USE, project_source="body"),
    # Проверка адреса до подключения: проект в теле запроса нужен, чтобы сравнить его с тем, что лежит на сервере.
    ("POST", "/git/remote/probe"): RouteRule(Action.PROJECT_SETTINGS, project_source="body"),
    ("GET", "/projects/{project_id}/chats"): RouteRule(Action.AGENT_USE),
    ("POST", "/projects/{project_id}/chats"): RouteRule(Action.AGENT_USE),
    ("GET", "/projects/{project_id}/chats/{session_id}"): RouteRule(Action.AGENT_USE),
    ("PATCH", "/projects/{project_id}/chats/{session_id}"): RouteRule(Action.AGENT_USE),
    ("DELETE", "/projects/{project_id}/chats/{session_id}"): RouteRule(Action.AGENT_USE),
    ("POST", "/projects/{project_id}/chats/{session_id}/turns"): RouteRule(Action.AGENT_USE),
    ("GET", "/projects/{project_id}/chats/{session_id}/runs/{run_id}/stream"): RouteRule(Action.AGENT_USE),
    ("POST", "/projects/{project_id}/chats/{session_id}/runs/{run_id}/approve"): RouteRule(Action.AGENT_USE),
    ("POST", "/projects/{project_id}/chats/{session_id}/runs/{run_id}/answer"): RouteRule(Action.AGENT_USE),
    ("POST", "/projects/{project_id}/chats/{session_id}/runs/{run_id}/cancel"): RouteRule(Action.AGENT_USE),
    # История проекта, она же git
    ("GET", "/projects/{project_id}/git"): RouteRule(Action.SOURCES_READ),
    ("POST", "/projects/{project_id}/git/fetch"): RouteRule(Action.HISTORY_WRITE),
    ("POST", "/projects/{project_id}/git/ci/preview"): RouteRule(Action.HISTORY_WRITE),
    ("POST", "/projects/{project_id}/git/ci/write"): RouteRule(Action.HISTORY_WRITE),
    ("POST", "/projects/{project_id}/vcs/init"): RouteRule(Action.HISTORY_WRITE),
    ("POST", "/projects/{project_id}/vcs/snapshots"): RouteRule(Action.HISTORY_WRITE),
    ("POST", "/projects/{project_id}/vcs/restore"): RouteRule(Action.HISTORY_WRITE),
    ("POST", "/projects/{project_id}/vcs/branches"): RouteRule(Action.HISTORY_WRITE),
    ("DELETE", "/projects/{project_id}/vcs/branches"): RouteRule(Action.HISTORY_WRITE),
    ("POST", "/projects/{project_id}/vcs/branches/switch"): RouteRule(Action.HISTORY_WRITE),
    ("POST", "/projects/{project_id}/vcs/tags"): RouteRule(Action.HISTORY_WRITE),
    ("DELETE", "/projects/{project_id}/vcs/tags"): RouteRule(Action.HISTORY_WRITE),
    # Сдача работы (автор пакета для SUBMISSION_CREATE лежит в теле запроса)
    ("GET", "/projects/{project_id}/submissions"): RouteRule(Action.SUBMISSION_READ),
    ("GET", "/projects/{project_id}/submissions/preflight"): RouteRule(Action.SUBMISSION_READ),
    ("GET", "/projects/{project_id}/submissions/{submission_id}/download"): RouteRule(Action.SUBMISSION_READ),
    ("POST", "/projects/{project_id}/submissions"): RouteRule(Action.SUBMISSION_CREATE),
    # Подписи: слот `<слот>--<слаг>` принадлежит автору слага. В пути пакета на подпись слота нет.
    ("GET", "/projects/{project_id}/docs/{doc_id}/signing-package"): RouteRule(Action.SIGN),
    ("POST", "/projects/{project_id}/docs/{doc_id}/detached/{slot_id}"): RouteRule(Action.SIGN, path_param="slot_id"),
    ("DELETE", "/projects/{project_id}/docs/{doc_id}/detached/{slot_id}"): RouteRule(Action.SIGN, path_param="slot_id"),
    ("POST", "/projects/{project_id}/docs/{doc_id}/detached/{slot_id}/complete-chain"): RouteRule(
        Action.SIGN, path_param="slot_id"
    ),
    ("POST", "/projects/{project_id}/docs/{doc_id}/detached/{slot_id}/sign"): RouteRule(
        Action.SIGN, path_param="slot_id"
    ),
    ("PUT", "/projects/{project_id}/signatures/slots/{slot_id}/signer"): RouteRule(Action.SIGN, path_param="slot_id"),
    ("DELETE", "/projects/{project_id}/signatures/slots/{slot_id}/signer"): RouteRule(
        Action.SIGN, path_param="slot_id"
    ),
    ("POST", "/projects/{project_id}/signatures/slots/{slot_id}/signer/file"): RouteRule(
        Action.SIGN, path_param="slot_id"
    ),
    ("PUT", "/projects/{project_id}/signatures/slots/{slot_id}/signer/level"): RouteRule(
        Action.SIGN, path_param="slot_id"
    ),
    ("POST", "/projects/{project_id}/signatures/slots/{slot_id}/png"): RouteRule(Action.SIGN, path_param="slot_id"),
    ("DELETE", "/projects/{project_id}/signatures/slots/{slot_id}/png"): RouteRule(Action.SIGN, path_param="slot_id"),
    # Настройки проекта (владелец)
    ("PATCH", "/projects/{project_id}"): RouteRule(Action.PROJECT_SETTINGS),
    ("POST", "/projects/{project_id}/move"): RouteRule(Action.PROJECT_SETTINGS),
    ("POST", "/projects/{project_id}/team/sets"): RouteRule(Action.PROJECT_SETTINGS),
    ("PATCH", "/projects/{project_id}/vcs/settings"): RouteRule(Action.PROJECT_SETTINGS),
    ("PUT", "/projects/{project_id}/git/remote"): RouteRule(Action.PROJECT_SETTINGS),
    ("DELETE", "/projects/{project_id}/git/remote"): RouteRule(Action.PROJECT_SETTINGS),
    ("PATCH", "/projects/{project_id}/git/settings"): RouteRule(Action.PROJECT_SETTINGS),
    ("PUT", "/projects/{project_id}/requirements/format"): RouteRule(Action.PROJECT_SETTINGS),
    ("POST", "/projects/{project_id}/nda/files"): RouteRule(Action.PROJECT_SETTINGS),
    ("DELETE", "/projects/{project_id}/nda/files"): RouteRule(Action.PROJECT_SETTINGS),
    # Шаблон проекта (владелец)
    ("POST", "/projects/{project_id}/template-update/plan"): RouteRule(Action.TEMPLATE_MANAGE),
    ("POST", "/projects/{project_id}/template-update/apply"): RouteRule(Action.TEMPLATE_MANAGE),
    ("POST", "/projects/{project_id}/template-update/revert"): RouteRule(Action.TEMPLATE_MANAGE),
    ("PUT", "/projects/{project_id}/template/tracking"): RouteRule(Action.TEMPLATE_MANAGE),
    ("DELETE", "/projects/{project_id}"): RouteRule(Action.PROJECT_DELETE),
    # Звонит контейнер Document Server: подлинность проверяют подпись и JWT внутри сценария.
    ("POST", "/office-editor/callback"): RouteRule(RouteExemption.system_callback, project_source="query"),
}


def scope_for_rule(rule: RouteRule, path_params: Mapping[str, object]) -> str | None:
    """Область проверки для решения: путь файла как есть, для id экземпляра слаг его автора."""
    if rule.path_param is None:
        return None
    value = path_params.get(rule.path_param)
    if value is None:
        return None
    if rule.action is Action.FILES_WRITE and rule.path_param in INSTANCE_ID_PARAMS:
        return scope_path_of_instance_id(str(value))
    return str(value)


def rule_for(request: Request) -> RouteRule | None:
    """Правило для текущего запроса; None, если маршрута нет в таблице."""
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if path is None:
        return None
    return ROUTE_ACTIONS.get(route_key(request.method, path))
