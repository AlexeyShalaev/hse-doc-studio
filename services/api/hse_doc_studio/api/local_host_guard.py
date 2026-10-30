"""Защита ручек локального режима, которые подключают Студию к чужому серверу, от DNS-rebinding.

В локальном режиме нет CSRF и списка допустимых Host: JSON-запросы с чужой страницы останавливает только
предварительный CORS-запрос. Страница, чьё имя перепривязано на 127.0.0.1, ходит к Студии как «своя» и могла
бы направить облачные сборки на сервер злоумышленника. Её выдаёт Host (имя злоумышленника) и Origin.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import Request

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode

_LOOPBACK = frozenset({"localhost", "127.0.0.1", "::1"})
_WILDCARDS = frozenset({"", "0.0.0.0", "::"})  # noqa: S104 — сравнение, не привязка


def _hostname(value: str) -> str | None:
    """Имя без порта и скобок IPv6 в нижнем регистре; `None`, если разобрать нельзя."""
    try:
        name = urlsplit(value if "//" in value else f"//{value}").hostname
    except ValueError:
        return None
    return name.lower() if name else None


def trusted_local_hosts() -> frozenset[str]:
    """Loopback, адрес привязки (если он конкретный) и хосты из `cors.allow_origins`."""
    hosts = set(_LOOPBACK)
    bind = settings.server.host.strip().lower()
    if bind not in _WILDCARDS:
        hosts.add(bind.strip("[]"))
    for origin in settings.cors.allow_origins:
        name = _hostname(origin)
        if name and origin != "*":
            hosts.add(name)
    return frozenset(hosts)


def require_trusted_local_host(request: Request) -> None:
    """Host и (если есть) Origin должны называть саму Студию, иначе 403 `forbidden`."""
    trusted = trusted_local_hosts()
    host = _hostname(request.headers.get("host", ""))
    origin = request.headers.get("origin")
    if host not in trusted or (origin is not None and _hostname(origin) not in trusted):
        raise IdentityError(IdentityErrorCode.forbidden)
