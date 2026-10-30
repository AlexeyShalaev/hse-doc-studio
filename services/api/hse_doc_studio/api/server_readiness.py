"""Проверки готовности серверного режима: настройки и подключённые маршруты по зонам.

Проверки синхронные и без сети: они ловят то, что делает старт заведомо негодным (нет базы, адреса,
согласованных сроков), а доступность Postgres и S3 в работе показывает ``/health/ready``.
"""

from __future__ import annotations

from collections.abc import Callable

from hse_doc_studio.api.config import Settings
from hse_doc_studio.api.route_scopes import ROUTE_SCOPES, RouteScope
from hse_doc_studio.core.readiness import ReadinessZone, ServerReadinessCheck

_REQUIRED_IDENTITY_ROUTES = (
    ("POST", "/auth/login"),
    ("GET", "/session/bootstrap"),
    ("GET", "/server-setup/status"),
)


def _database(get_cfg: Callable[[], Settings]) -> str | None:
    if not (get_cfg().db.dsn or "").strip():
        return "не задан HSE_STUDIO__DB__DSN"
    return None


def _public_url(get_cfg: Callable[[], Settings]) -> str | None:
    url = (get_cfg().auth.public_url or "").strip()
    if not url.startswith(("http://", "https://")):
        return "не задан HSE_STUDIO__AUTH__PUBLIC_URL (внешний адрес вида https://studio.example.org)"
    return None


def _identity_routes() -> str | None:
    missing = [f"{m} {p}" for m, p in _REQUIRED_IDENTITY_ROUTES if (m, p) not in ROUTE_SCOPES]
    return f"не подключены маршруты входа: {', '.join(missing)}" if missing else None


def _runner_api() -> str | None:
    if not any(scope is RouteScope.runner_token for scope in ROUTE_SCOPES.values()):
        return "не подключён API раннеров"
    return None


def _lease(get_cfg: Callable[[], Settings]) -> str | None:
    jobs = get_cfg().jobs
    if jobs.lease_s <= jobs.reaper_interval_s:
        return "срок аренды задачи (JOBS__LEASE_S) должен быть больше интервала проверки (JOBS__REAPER_INTERVAL_S)"
    return None


def _office_editor(get_cfg: Callable[[], Settings]) -> str | None:
    editor = get_cfg().office_editor
    if editor.pool_replicas and not editor.backend_internal_url.strip():
        return "для пула ONLYOFFICE нужен OFFICE_EDITOR__BACKEND_INTERNAL_URL (адрес api изнутри сети реплик)"
    return None


def server_checks(get_cfg: Callable[[], Settings]) -> list[ServerReadinessCheck]:
    """Проверки identity, базы, jobs и services; ключ секретов и пользовательские маршруты добавляет вход."""
    return [
        ServerReadinessCheck(ReadinessZone.persistence, "database", lambda: _database(get_cfg)),
        ServerReadinessCheck(ReadinessZone.identity, "public_url", lambda: _public_url(get_cfg)),
        ServerReadinessCheck(ReadinessZone.identity, "login_routes", _identity_routes),
        ServerReadinessCheck(ReadinessZone.jobs, "runner_api", _runner_api),
        ServerReadinessCheck(ReadinessZone.jobs, "lease", lambda: _lease(get_cfg)),
        ServerReadinessCheck(ReadinessZone.services, "office_editor", lambda: _office_editor(get_cfg)),
    ]
