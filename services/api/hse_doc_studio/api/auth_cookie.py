"""Cookie сессии и заголовок Bearer: откуда запрос берёт данные для входа."""

from __future__ import annotations

from fastapi import Request

from hse_doc_studio.core.identity.entities import ActorCredentials

SESSION_COOKIE = "hse_session"
# Префикс `__Host-` браузер разрешает только по HTTPS (Secure, Path=/, без Domain).
SECURE_SESSION_COOKIE = f"__Host-{SESSION_COOKIE}"
_BEARER = "bearer"


def session_cookie_name(*, secure: bool) -> str:
    return SECURE_SESSION_COOKIE if secure else SESSION_COOKIE


def bearer_token(request: Request) -> str | None:
    scheme, _, value = request.headers.get("authorization", "").partition(" ")
    value = value.strip()
    return value if scheme.lower() == _BEARER and value else None


def credentials_from_request(request: Request) -> ActorCredentials:
    cookies = request.cookies
    secret = cookies.get(SECURE_SESSION_COOKIE) or cookies.get(SESSION_COOKIE)
    return ActorCredentials(session_secret=secret or None, bearer_token=bearer_token(request))
