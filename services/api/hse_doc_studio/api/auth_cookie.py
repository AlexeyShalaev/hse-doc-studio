"""Cookie сессии и заголовок Bearer: откуда запрос берёт данные для входа."""

from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import Request, Response

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


def credentials_from_request(request: Request, *, secure: bool | None = None) -> ActorCredentials:
    """Данные для входа из запроса.

    По HTTPS читается только `__Host-hse_session`: простое имя может подложить соседний поддомен или посредник по
    HTTP, а префикс как раз это запрещает. `secure` по умолчанию берётся из `auth.public_url`.
    """
    if secure is None:
        from hse_doc_studio.api.config import settings  # noqa: PLC0415

        secure = is_secure_public_url(settings.auth.public_url)
    cookies = request.cookies
    secret = cookies.get(SECURE_SESSION_COOKIE)
    if not secret and not secure:
        secret = cookies.get(SESSION_COOKIE)
    return ActorCredentials(session_secret=secret or None, bearer_token=bearer_token(request))


def public_origin(public_url: str | None) -> str | None:
    """Origin (схема и хост) внешнего адреса либо None, если адрес не задан или не похож на URL."""
    if not public_url:
        return None
    parts = urlsplit(public_url.strip())
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}".lower()


def is_secure_public_url(public_url: str | None) -> bool:
    origin = public_origin(public_url)
    return origin is not None and origin.startswith("https://")


def set_session_cookie(response: Response, secret: str, *, secure: bool, max_age_s: int) -> None:
    """HttpOnly и SameSite=Lax всегда; Secure и префикс `__Host-` по HTTPS. Без Domain."""
    response.set_cookie(
        session_cookie_name(secure=secure),
        secret,
        max_age=max_age_s,
        path="/",
        httponly=True,
        secure=secure,
        samesite="lax",
    )


def clear_session_cookie(response: Response, *, secure: bool) -> None:
    """Гасит cookie обоих имён: после смены схемы или подкладки простого имени старое не должно остаться."""
    response.delete_cookie(session_cookie_name(secure=secure), path="/", httponly=True, secure=secure, samesite="lax")
    if secure:
        response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, secure=False, samesite="lax")


OIDC_STATE_COOKIE = "hse_oidc_state"
OIDC_STATE_MAX_AGE_S = 600


def oidc_state_cookie_name(*, secure: bool) -> str:
    return f"__Host-{OIDC_STATE_COOKIE}" if secure else OIDC_STATE_COOKIE


def set_oidc_state_cookie(response: Response, sealed: str, *, secure: bool) -> None:
    """HttpOnly, SameSite=Lax (возврат от провайдера это переход верхнего уровня), живёт десять минут."""
    response.set_cookie(
        oidc_state_cookie_name(secure=secure),
        sealed,
        max_age=OIDC_STATE_MAX_AGE_S,
        path="/",
        httponly=True,
        secure=secure,
        samesite="lax",
    )


def clear_oidc_state_cookie(response: Response, *, secure: bool) -> None:
    response.delete_cookie(
        oidc_state_cookie_name(secure=secure), path="/", httponly=True, secure=secure, samesite="lax"
    )
