"""Ограничение частоты запросов на уровне API: таблица дорогих маршрутов, гард и `enforce` для маршрутов входа.

Гард стоит на `/api/v1` и ничего не делает, пока в приложении нет ограничителя (локальная установка).
Ограничитель кладёт в `app.state.rate_limiter` серверный режим. Дорогие операции считаются по пользователю,
вход и регистрация (у них актора ещё нет) по IP из `client_ip`, который верит `X-Forwarded-For` только от
доверенных прокси.
"""

from __future__ import annotations

from collections.abc import Mapping

from fastapi import FastAPI, Request

from hse_doc_studio.api.config import Settings
from hse_doc_studio.api.observability.client_ip import client_ip
from hse_doc_studio.api.route_actions import RouteKey, route_key
from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.normalize import normalize_email
from hse_doc_studio.core.rate_limit import (
    AGENT,
    AUTH_EMAIL,
    COMPILE,
    GIT_SYNC,
    UPLOAD,
    IRateLimiter,
    RateRule,
)
from hse_doc_studio.infra.ratelimit.memory import InMemoryRateLimiter

# Маршруты проекта, чья цена высока: сборка, проверки, загрузка файлов, агент, обмен с git.
EXPENSIVE_ROUTES: Mapping[RouteKey, RateRule] = {
    ("POST", "/projects/{project_id}/documents/{doc_id}/compile"): COMPILE,
    ("POST", "/projects/{project_id}/documents/{doc_id}/checks/run"): COMPILE,
    ("PUT", "/projects/{project_id}/files/{path:path}"): UPLOAD,
    ("POST", "/agent/chats/{session_id}/turns"): AGENT,
    ("POST", "/projects/{project_id}/chats/{session_id}/turns"): AGENT,
    ("POST", "/git/clone"): GIT_SYNC,
    ("POST", "/git/clone/bundle"): GIT_SYNC,
    ("POST", "/projects/{project_id}/git/sync"): GIT_SYNC,
    ("POST", "/projects/{project_id}/git/fetch"): GIT_SYNC,
    ("POST", "/projects/{project_id}/git/bundle/import"): GIT_SYNC,
}


def install_rate_limiter(app: FastAPI, cfg: Settings) -> None:
    if cfg.rate_limit.enabled:
        limiter = InMemoryRateLimiter()
        app.state.rate_limiter = limiter
        app.state.rate_limit_scale = cfg.rate_limit.scale


def _scaled(request: Request, rule: RateRule) -> RateRule:
    scale = float(getattr(request.app.state, "rate_limit_scale", 1.0))
    if scale == 1.0:
        return rule
    return RateRule(rule.name, max(1, round(rule.limit * scale)), rule.window_s)


async def enforce(request: Request, rule: RateRule, key: str) -> None:
    """429 `rate_limited` с `Retry-After`, если ключ исчерпал лимит; без ограничителя ничего не делает."""
    limiter: IRateLimiter | None = getattr(request.app.state, "rate_limiter", None)
    if limiter is None:
        return
    decision = await limiter.hit(_scaled(request, rule), key)
    if not decision.allowed:
        raise IdentityError(IdentityErrorCode.rate_limited, retry_after_s=decision.retry_after_s)


async def enforce_ip(request: Request, rule: RateRule) -> None:
    """Для маршрутов входа, регистрации и сброса пароля: ключ по адресу клиента."""
    await enforce(request, rule, f"ip:{client_ip(request)}")


def _email_key(request: Request, email: str, action: str) -> str:
    # Ключ включает действие и адрес клиента: иначе пять запросов чужака закрывали бы владельцу адреса
    # сброс пароля, а запросы одного действия съедали бы лимит другого.
    return f"email:{action}:{client_ip(request)}:{normalize_email(email)}"


async def enforce_email(request: Request, email: str, rule: RateRule = AUTH_EMAIL, *, action: str = "mail") -> None:
    """Для маршрутов с известным пользователем, что отправляют письмо: 429, если с этого адреса слишком часто."""
    await enforce(request, rule, _email_key(request, email, action))


async def email_send_allowed(request: Request, email: str, action: str, rule: RateRule = AUTH_EMAIL) -> bool:
    """Для маршрутов с нейтральным ответом (забыл пароль, повтор подтверждения): False значит письмо не слать.

    Отказа 429 здесь нет намеренно: он различал бы адреса и позволял бы чужому исчерпать лимит владельца.
    """
    limiter: IRateLimiter | None = getattr(request.app.state, "rate_limiter", None)
    if limiter is None:
        return True
    decision = await limiter.hit(_scaled(request, rule), _email_key(request, email, action))
    return decision.allowed


def _subject(request: Request) -> str:
    actor = current_actor()
    if actor is not None and actor.id:
        return f"user:{actor.id}"
    return f"ip:{client_ip(request)}"


async def rate_limit_guard(request: Request) -> None:
    if getattr(request.app.state, "rate_limiter", None) is None:
        return
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    rule = EXPENSIVE_ROUTES.get(route_key(request.method, path)) if path else None
    if rule is not None:
        await enforce(request, rule, _subject(request))
