"""Таблица «маршрут -> область» для всего, что не лежит в ROUTE_ACTIONS (маршруты проекта).

Вместе с `ROUTE_ACTIONS` это единый реестр: тест `tests/integration/api/access/test_route_scopes.py`
сверяет обе таблицы с настоящими маршрутами приложения. Маршрут без записи в обеих таблицах в
серверном режиме закрыт (403), так что забытая запись не открывает дыру. Ключ как в
`ROUTE_ACTIONS`: `(МЕТОД, шаблон пути без /api/v1)`.

Области:
- public: без входа (проверка готовности, публичные ссылки);
- authenticated: любой вошедший пользователь;
- instance_admin: только администратор установки; в `/api/admin` чужому отвечаем 404, не 403;
- org_admin: администратор организации; пока организаций нет, проходит только админ установки;
- runner_token, job_token, signed_token: подлинность проверяет сам маршрут по своему токену,
  цепочка cookie для них не запускается;
- local_only: возможности одной локальной установки (файловая система хоста, docker, обновление
  самой Студии); в серверном режиме отвечают 404.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

from fastapi import Request

from hse_doc_studio.api.route_actions import RouteKey, route_key, rule_for
from hse_doc_studio.core.access.actions import RouteExemption

ADMIN_PREFIX = "/api/admin"


class RouteScope(StrEnum):
    public = "public"
    authenticated = "authenticated"
    instance_admin = "instance_admin"
    org_admin = "org_admin"
    runner_token = "runner_token"  # noqa: S105 — имя области, не секрет
    job_token = "job_token"  # noqa: S105 — имя области, не секрет
    signed_token = "signed_token"  # noqa: S105 — имя области, не секрет
    local_only = "local_only"


# Области, где подлинность проверяет сам маршрут: актор по cookie или PAT ему не нужен.
SELF_AUTHENTICATED = frozenset({RouteScope.runner_token, RouteScope.job_token, RouteScope.signed_token})

_P = RouteScope.public
_A = RouteScope.authenticated
_ADM = RouteScope.instance_admin
_LOCAL = RouteScope.local_only

ROUTE_SCOPES: Mapping[RouteKey, RouteScope] = {
    # Вход и сессии: в локальной установке входа нет, маршруты входа и аккаунта отвечают 404 сами
    ("GET", "/session/bootstrap"): _P,
    ("POST", "/auth/login"): _P,
    ("POST", "/auth/logout"): _P,
    # Единый вход: страницы провайдера открывает браузер, личность подтверждает состояние в подписанной cookie
    ("GET", "/auth/oidc/{provider_id}/start"): _P,
    ("GET", "/auth/oidc/{provider_id}/callback"): _P,
    # Письма: подтверждение почты и сброс пароля; личность подтверждает одноразовый токен
    ("POST", "/auth/verify"): _P,
    ("POST", "/auth/verify/resend"): _P,
    ("POST", "/auth/forgot"): _P,
    ("POST", "/auth/reset"): _P,
    # Регистрация (открытая и по приглашению) и карточка приглашения для формы
    ("POST", "/auth/register"): _P,
    ("GET", "/auth/invitations/{token}"): _P,
    # Мастер первого запуска: до завершения права проверяет сам маршрут (токен установки или сессия админа),
    # после завершения маршрутов нет (404)
    ("GET", "/server-setup/status"): _P,
    ("POST", "/server-setup/admin"): _P,
    ("GET", "/server-setup/environment"): _P,
    ("GET", "/server-setup/settings"): _P,
    ("POST", "/server-setup/settings"): _P,
    ("POST", "/server-setup/complete"): _P,
    ("GET", "/account"): _A,
    ("PATCH", "/account"): _A,
    ("POST", "/account/password"): _A,
    ("POST", "/account/email"): _A,
    ("POST", "/account/email/confirm"): _P,
    ("GET", "/account/sessions"): _A,
    ("DELETE", "/account/sessions"): _A,
    ("DELETE", "/account/sessions/{session_id}"): _A,
    ("GET", "/account/export"): _A,
    ("GET", "/account/identities"): _A,
    ("GET", "/account/identities/{provider_id}/link"): _A,
    ("DELETE", "/account/identities/{provider_id}"): _A,
    ("GET", "/account/tokens"): _A,
    ("POST", "/account/tokens"): _A,
    ("DELETE", "/account/tokens/{token_id}"): _A,
    # Организации и группы: роль проверяет сценарий (не участнику 404, мало роли 403)
    ("GET", "/orgs"): _A,
    ("POST", "/orgs"): _A,
    ("GET", "/orgs/{slug}"): _A,
    ("PATCH", "/orgs/{slug}"): _A,
    ("DELETE", "/orgs/{slug}"): _A,
    ("GET", "/orgs/{slug}/members"): _A,
    ("POST", "/orgs/{slug}/members"): _A,
    ("PATCH", "/orgs/{slug}/members/{user_id}"): _A,
    ("DELETE", "/orgs/{slug}/members/{user_id}"): _A,
    ("POST", "/orgs/{slug}/leave"): _A,
    ("GET", "/orgs/{slug}/groups"): _A,
    ("POST", "/orgs/{slug}/groups"): _A,
    ("PATCH", "/groups/{group_id}"): _A,
    ("DELETE", "/groups/{group_id}"): _A,
    ("GET", "/groups/{group_id}/members"): _A,
    ("POST", "/groups/{group_id}/members"): _A,
    ("DELETE", "/groups/{group_id}/members/{user_id}"): _A,
    # Каталог шаблонов
    ("GET", "/catalog/packs"): _A,
    ("GET", "/catalog/packs/{pack_id}/templates/{template_id}/versions"): _A,
    ("GET", "/catalog/packs/{pack_id}/templates/{template_id}/versions/{version}"): _A,
    # Список и создание проектов; проект с папкой на диске хоста подключает только локальная установка
    ("GET", "/projects"): _A,
    ("GET", "/projects/suggestions"): _A,
    ("POST", "/projects"): _A,
    ("POST", "/projects/connect"): _LOCAL,
    # Образы сборки, LanguageTool и ONLYOFFICE: docker хоста управляется только локально
    ("GET", "/compile/docker-status"): _LOCAL,
    ("GET", "/compile/images"): _LOCAL,
    ("GET", "/compile/images/remote"): _LOCAL,
    ("POST", "/compile/images/active"): _LOCAL,
    ("DELETE", "/compile/images"): _LOCAL,
    ("GET", "/compile/images/install"): _LOCAL,
    ("GET", "/languagetool/status"): _A,
    ("GET", "/languagetool/images"): _LOCAL,
    ("GET", "/languagetool/images/remote"): _LOCAL,
    ("POST", "/languagetool/images/active"): _LOCAL,
    ("DELETE", "/languagetool/images"): _LOCAL,
    ("GET", "/languagetool/images/install"): _LOCAL,
    ("GET", "/office-services/status"): _A,
    ("GET", "/office-services/{service}/images"): _LOCAL,
    ("GET", "/office-services/{service}/images/remote"): _LOCAL,
    ("POST", "/office-services/{service}/images/active"): _LOCAL,
    ("GET", "/office-services/{service}/images/install"): _LOCAL,
    # Шрифты: общие на установку, менять их может только админ; системные шрифты хоста только локально
    ("GET", "/fonts"): _A,
    ("GET", "/fonts/{filename}/file"): _A,
    ("GET", "/fonts/catalog"): _A,
    ("GET", "/fonts/system"): _LOCAL,
    ("POST", "/fonts/system/import"): _LOCAL,
    ("GET", "/fonts/marketplace"): _A,
    ("POST", "/fonts/marketplace/{font_id}"): _ADM,
    ("POST", "/fonts/catalog/{font_id}"): _ADM,
    ("PUT", "/fonts/{filename}"): _ADM,
    ("DELETE", "/fonts/{filename}"): _ADM,
    # Файловая система хоста
    ("GET", "/fs/browse"): _LOCAL,
    ("GET", "/fs/inspect"): _LOCAL,
    # Справочник сотрудников ВШЭ
    ("GET", "/hse/persons/facets"): _A,
    ("GET", "/hse/persons/search"): _A,
    ("GET", "/hse/persons/{person_id}"): _A,
    # Настройки
    ("GET", "/settings"): _A,
    ("PUT", "/settings"): _A,
    # Система, обновление и первый запуск локальной установки
    ("GET", "/system/runner-health"): _A,
    ("GET", "/system/editors"): _A,
    ("GET", "/system/archive-formats"): _A,
    ("GET", "/system/info"): _A,
    ("GET", "/system/release-notes"): _A,
    ("POST", "/system/check-updates"): _LOCAL,
    ("GET", "/system/versions"): _LOCAL,
    ("POST", "/system/self-update"): _LOCAL,
    ("GET", "/setup/status"): _LOCAL,
    ("POST", "/setup/probe-folder"): _LOCAL,
    ("POST", "/setup/apply"): _LOCAL,
    ("GET", "/setup/environment"): _LOCAL,
    ("GET", "/system/docker-usage"): _LOCAL,
    ("POST", "/system/docker-cleanup"): _LOCAL,
    ("GET", "/system/docker-cleanup"): _LOCAL,
    ("POST", "/system/docker-cleanup/cancel"): _LOCAL,
    # Провайдеры ИИ и персоны
    ("GET", "/ai-providers"): _A,
    ("POST", "/ai-providers"): _A,
    ("GET", "/ai-providers/{provider_id}"): _A,
    ("PATCH", "/ai-providers/{provider_id}"): _A,
    ("DELETE", "/ai-providers/{provider_id}"): _A,
    ("GET", "/ai-providers/{provider_id}/models"): _A,
    ("GET", "/agent-personas"): _A,
    ("GET", "/agent-personas/builtins"): _A,
    ("POST", "/agent-personas"): _A,
    ("GET", "/agent-personas/{persona_id}"): _A,
    ("PATCH", "/agent-personas/{persona_id}"): _A,
    ("DELETE", "/agent-personas/{persona_id}"): _A,
    # Локальная среда Ollama на хосте
    ("GET", "/ai-runtime/hardware"): _LOCAL,
    ("GET", "/ai-runtime/catalog"): _LOCAL,
    ("GET", "/ai-runtime/registry/search"): _LOCAL,
    ("GET", "/ai-runtime/status"): _LOCAL,
    ("POST", "/ai-runtime/start"): _LOCAL,
    ("POST", "/ai-runtime/stop"): _LOCAL,
    ("GET", "/ai-runtime/engine/install"): _LOCAL,
    ("POST", "/ai-runtime/models/pull"): _LOCAL,
    ("GET", "/ai-runtime/models/pulls"): _LOCAL,
    ("DELETE", "/ai-runtime/models/pulls"): _LOCAL,
    ("GET", "/ai-runtime/models/loaded"): _LOCAL,
    ("POST", "/ai-runtime/models/unload"): _LOCAL,
    ("POST", "/ai-runtime/provider/sync"): _LOCAL,
    ("DELETE", "/ai-runtime/models"): _LOCAL,
    # Агент и его чаты
    ("GET", "/agent/tools"): _A,
    ("GET", "/agent/personas"): _A,
    ("GET", "/agent/chats"): _A,
    ("GET", "/agent/chats/{session_id}"): _A,
    ("PATCH", "/agent/chats/{session_id}"): _A,
    ("DELETE", "/agent/chats/{session_id}"): _A,
    ("POST", "/agent/chats/{session_id}/turns"): _A,
    ("POST", "/agent/chats/{session_id}/runs/{run_id}/approve"): _A,
    ("POST", "/agent/chats/{session_id}/runs/{run_id}/answer"): _A,
    ("POST", "/agent/chats/{session_id}/runs/{run_id}/cancel"): _A,
    ("GET", "/agent/chats/{session_id}/runs/{run_id}/stream"): _A,
    # Выгрузка и загрузка данных всей установки
    ("POST", "/data/export"): _ADM,
    ("POST", "/data/import"): _ADM,
    # Электронная подпись
    ("GET", "/signing-identities"): _A,
    ("POST", "/signing-identities/self-signed"): _A,
    ("POST", "/signing-identities/import-pkcs12"): _A,
    ("DELETE", "/signing-identities/{identity_id}"): _A,
    ("POST", "/signing-identities/openpgp/generate"): _A,
    ("POST", "/signing-identities/openpgp/import"): _A,
    ("GET", "/signing-identities/openpgp/keys"): _A,
    ("GET", "/signing-identities/{identity_id}/public-key"): _A,
    ("GET", "/crypto/cadesplugin_api.js"): _A,
    ("GET", "/trusted-roots"): _A,
    ("POST", "/trusted-roots"): _A,
    ("POST", "/trusted-roots/from-chain/{fingerprint}"): _A,
    ("DELETE", "/trusted-roots/{fingerprint}"): _A,
    # Профиль
    ("GET", "/profile"): _A,
    ("PUT", "/profile"): _A,
    ("DELETE", "/profile"): _A,
    # Git: доступы, хосты, клонирование
    ("GET", "/git/credentials"): _A,
    ("POST", "/git/credentials"): _A,
    ("PATCH", "/git/credentials/{credential_id}"): _A,
    ("POST", "/git/credentials/{credential_id}/check"): _A,
    ("DELETE", "/git/credentials/{credential_id}"): _A,
    ("GET", "/git/secrets/status"): _A,
    ("GET", "/git/hosts"): _A,
    ("POST", "/git/hosts/trust"): _ADM,
    ("DELETE", "/git/hosts"): _ADM,
    ("GET", "/git/host-settings"): _A,
    ("PUT", "/git/host-settings"): _ADM,
    # Клон принимает от клиента абсолютную папку и регистрирует проект в локальном индексе: на сервере это
    # запись в произвольное место диска. Пока клон не выбирает папку на томе проектов и не создаёт строку
    # с владельцем, маршруты существуют только в локальной установке.
    ("POST", "/git/clone"): _LOCAL,
    ("POST", "/git/clone/bundle"): _LOCAL,
    ("GET", "/git/clone/defaults"): _A,
    ("GET", "/git/operations/{operation_id}"): _A,
    ("POST", "/git/operations/{operation_id}/cancel"): _A,
    ("GET", "/git/shared-folder"): _LOCAL,
    # Протокол раннера и админка лежат вне /api/v1, ключ это полный путь маршрута
    ("POST", "/api/runner/v1/register"): RouteScope.runner_token,
    ("POST", "/api/runner/v1/poll"): RouteScope.runner_token,
    ("POST", "/api/runner/v1/jobs/{job_id}/heartbeat"): RouteScope.job_token,
    ("POST", "/api/runner/v1/jobs/{job_id}/log"): RouteScope.job_token,
    ("POST", "/api/runner/v1/jobs/{job_id}/blobs/need"): RouteScope.job_token,
    ("GET", "/api/runner/v1/jobs/{job_id}/blobs/{sha256}"): RouteScope.job_token,
    ("POST", "/api/runner/v1/jobs/{job_id}/artifacts"): RouteScope.job_token,
    ("PUT", "/api/runner/v1/jobs/{job_id}/artifacts/{sha256}"): RouteScope.job_token,
    ("POST", "/api/runner/v1/jobs/{job_id}/complete"): RouteScope.job_token,
    # Админка установки: гард admin_guard сам отвечает 401 анониму и 404 не админу
    ("DELETE", "/api/admin/invitations/{invite_id}"): _ADM,
    ("DELETE", "/api/admin/users/{user_id}"): _ADM,
    ("DELETE", "/api/admin/oidc-providers/{provider_id}"): _ADM,
    ("GET", "/api/admin/approvals"): _ADM,
    ("GET", "/api/admin/audit"): _ADM,
    ("GET", "/api/admin/invitations"): _ADM,
    ("GET", "/api/admin/oidc-providers"): _ADM,
    ("GET", "/api/admin/oidc-providers/{provider_id}"): _ADM,
    ("GET", "/api/admin/settings/auth"): _ADM,
    ("GET", "/api/admin/settings/registration"): _ADM,
    ("GET", "/api/admin/settings/retention"): _ADM,
    ("GET", "/api/admin/settings/smtp"): _ADM,
    ("GET", "/api/admin/users"): _ADM,
    ("GET", "/api/admin/users/{user_id}"): _ADM,
    ("PATCH", "/api/admin/oidc-providers/{provider_id}"): _ADM,
    ("PATCH", "/api/admin/users/{user_id}"): _ADM,
    ("POST", "/api/admin/approvals/{user_id}/approve"): _ADM,
    ("POST", "/api/admin/approvals/{user_id}/reject"): _ADM,
    ("POST", "/api/admin/invitations"): _ADM,
    ("POST", "/api/admin/invitations/{invite_id}/resend"): _ADM,
    ("POST", "/api/admin/oidc-providers"): _ADM,
    ("POST", "/api/admin/settings/smtp/test"): _ADM,
    ("POST", "/api/admin/users/{user_id}/disable"): _ADM,
    ("POST", "/api/admin/users/{user_id}/enable"): _ADM,
    ("POST", "/api/admin/users/{user_id}/reset-link"): _ADM,
    ("POST", "/api/admin/users/{user_id}/sessions/revoke"): _ADM,
    ("PUT", "/api/admin/settings/auth"): _ADM,
    ("PUT", "/api/admin/settings/registration"): _ADM,
    ("PUT", "/api/admin/settings/smtp"): _ADM,
    ("POST", "/api/admin/runner-tokens"): _ADM,
    ("GET", "/api/admin/runner-tokens"): _ADM,
    ("DELETE", "/api/admin/runner-tokens/{token_id}"): _ADM,
    ("GET", "/api/admin/runners"): _ADM,
    ("PATCH", "/api/admin/runners/{runner_id}"): _ADM,
    ("POST", "/api/admin/runners/{runner_id}/rotate-token"): _ADM,
    ("DELETE", "/api/admin/runners/{runner_id}"): _ADM,
    ("GET", "/api/admin/queue"): _ADM,
    ("GET", "/api/admin/queue/summary"): _ADM,
    ("POST", "/api/admin/queue/{job_id}/cancel"): _ADM,
    ("GET", "/api/admin/quotas"): _ADM,
    ("PUT", "/api/admin/quotas"): _ADM,
    ("GET", "/api/admin/services"): _ADM,
    ("GET", "/api/admin/storage"): _ADM,
    ("GET", "/api/admin/settings/signing"): _ADM,
    ("PUT", "/api/admin/settings/signing"): _ADM,
    ("GET", "/api/admin/ai-providers"): _ADM,
    ("POST", "/api/admin/ai-providers"): _ADM,
    ("GET", "/api/admin/ai-providers/{provider_id}"): _ADM,
    ("PATCH", "/api/admin/ai-providers/{provider_id}"): _ADM,
    ("DELETE", "/api/admin/ai-providers/{provider_id}"): _ADM,
    ("POST", "/api/admin/ai-providers/{provider_id}/check"): _ADM,
}

# Маршруты `authenticated`, чьи данные пока общие на всю установку: у пользователей они ещё не
# разделены. Пока список не пуст, готовность зоны `per_user_routes` красная и сервер не стартует.
# Список только сжимается: срез, который переводит данные в БД под владельца, вычёркивает свои
# маршруты (тест `test_route_scopes.py` сравнивает его с потолком и с таблицей).
PER_USER_PENDING: frozenset[RouteKey] = frozenset(
    key
    for key in ROUTE_SCOPES
    if key[1].split("/")[1]
    in {
        "projects",
        "agent-personas",
        "agent",
        "signing-identities",
        "trusted-roots",
        "profile",
        "git",
    }
    and ROUTE_SCOPES[key] is RouteScope.authenticated
    and key[1]
    not in {
        "/git/secrets/status",
        "/git/clone/defaults",
        "/agent/tools",
        "/agent/personas",
        # Идентичности подписи лежат в Postgres у владельца; ключи OpenPGP остаются в общей связке установки.
        "/signing-identities",
        "/signing-identities/self-signed",
        "/signing-identities/import-pkcs12",
        "/signing-identities/{identity_id}",
        # Git-доступы лежат в Postgres у владельца; проект пользуется ими по привязке.
        "/git/credentials",
        "/git/credentials/{credential_id}",
        "/git/credentials/{credential_id}/check",
    }
)


def per_user_routes_problem(pending: frozenset[RouteKey] | None = None) -> str | None:
    """Причина красной готовности зоны `per_user_routes`; None, когда общих пользовательских маршрутов не осталось."""
    left = PER_USER_PENDING if pending is None else pending
    if not left:
        return None
    return f"{len(left)} пользовательских маршрутов ещё отдают общие данные установки"


def scope_of_route_path(method: str, path: str) -> RouteScope | None:
    return ROUTE_SCOPES.get(route_key(method, path))


def scope_for_request(request: Request) -> RouteScope | None:
    """Область маршрута текущего запроса; None, если маршрут не классифицирован."""
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if path is None:
        return None
    rule = rule_for(request)
    if rule is not None and isinstance(rule.action, RouteExemption):
        return RouteScope.signed_token
    return scope_of_route_path(request.method, path)


def route_path_of(request: Request) -> str:
    return str(getattr(request.scope.get("route"), "path", ""))
