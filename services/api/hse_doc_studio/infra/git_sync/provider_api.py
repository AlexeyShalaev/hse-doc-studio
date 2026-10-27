"""Разговор с API git-серверов: определение провайдера по публичным адресам версии и проверка токена.

Определение шлёт запросы без доступа и без перенаправлений: догадка о сервере не должна унести токен или
ходить дальше самого хоста. Проверка токена, наоборот, ходит с токеном, но только на корень API, который
уже определён для этого хоста. Сертификат проверяется полностью; если у сервера свой CA, httpx получает тот же
файл PEM, что и git (`http.<адрес>.sslCAInfo`), и тогда системные центры не используются ни там, ни там.
"""

from __future__ import annotations

import asyncio
import json
import ssl
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import structlog

from hse_doc_studio.core.git_sync.entities import TokenIntrospection, TokenState
from hse_doc_studio.core.git_sync.error_messages import git_error
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.protocols import DetectionRequest, ICertificateService, IntrospectionRequest
from hse_doc_studio.core.git_sync.providers import (
    ApiDetection,
    GitProvider,
    api_base,
    instance_prefix_candidates,
    provider_spec,
    web_base,
)

logger = structlog.get_logger()

_USER_AGENT = "HSE-Doc-Studio"
_MAX_BODY_BYTES = 1_000_000
# Таймаут httpx действует на каждую фазу и сбрасывается с каждым байтом: сервер, который капает по байту или не
# заканчивает ответ, держал бы запрос вечно. Поэтому на весь запрос (до конца тела) есть общий срок.
_TOTAL_TIMEOUT_FACTOR = 2.0
_CACHE_TTL_S = 300.0
# Сбой (таймаут, обрыв, сертификат) не ответ сервера: тот же запрос через несколько секунд может дать другое.
_FAILURE_TTL_S = 5.0
# Ключ зависит от адреса, который печатает человек: без потолка кэш рос бы с каждым новым адресом до конца процесса.
_CACHE_MAX_ENTRIES = 256
_HTTP_OK = 200
_HTTP_UNAUTHORIZED = 401
_HTTP_FORBIDDEN = 403
# Коды openssl X509_V_ERR_*, при которых сертификат не принят из-за незнакомого центра выдачи.
_UNTRUSTED_VERIFY_CODES = frozenset({18, 19, 20, 21})
_GITHUB_ENTERPRISE_HEADER = "x-github-enterprise-version"
_GITHUB_EXPIRY_HEADER = "github-authentication-token-expiration"
_GITHUB_SCOPES_HEADER = "x-oauth-scopes"


def _ssl_context(ca_file: Path | None) -> ssl.SSLContext:
    """Проверка как у git (curl): внутренние центры часто выдают сертификаты без идентификаторов ключа, а строгий
    режим Python их отвергает; git при этом работает, и проверка токена не должна быть строже него."""
    context = ssl.create_default_context(cafile=str(ca_file)) if ca_file is not None else ssl.create_default_context()
    context.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return context


@dataclass(frozen=True)
class _Reply:
    """Ответ сервера: статус, заголовки и тело, прочитанное не дальше `_MAX_BODY_BYTES` (None, если тело длиннее)."""

    status_code: int
    headers: httpx.Headers
    body: bytes | None

    def json_object(self) -> dict[str, Any] | None:
        if self.body is None:
            return None
        try:
            parsed = json.loads(self.body)
        except ValueError:
            return None
        return parsed if isinstance(parsed, dict) else None


class _Fetcher:
    """GET с потолком по размеру тела и общим сроком: длинный или медленный ответ не копится в памяти и не висит."""

    def __init__(self, client: httpx.AsyncClient, timeout_s: float) -> None:
        self._client = client
        self._deadline_s = timeout_s * _TOTAL_TIMEOUT_FACTOR

    async def get(self, url: str, headers: Mapping[str, str] | None = None) -> _Reply:
        """Бросает TimeoutError, когда срок вышел, и httpx.HTTPError при сбое соединения."""
        async with asyncio.timeout(self._deadline_s), self._client.stream("GET", url, headers=headers) as response:
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body += chunk
                if len(body) > _MAX_BODY_BYTES:
                    return _Reply(response.status_code, response.headers, None)
            return _Reply(response.status_code, response.headers, bytes(body))


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


class HttpProviderDetector:
    """Спрашивает адреса версии GitLab, Gitea и GitHub Enterprise; ответы кэшируются на несколько минут."""

    def __init__(self, timeout_s: float) -> None:
        self._timeout_s = timeout_s
        self._cache: dict[tuple[object, ...], tuple[float, ApiDetection | None]] = {}

    async def detect(self, request: DetectionRequest) -> ApiDetection | None:
        # Ответ зависит от адресов, которые спрашивают (префиксы), а не от самого репозитория: у одного сервера
        # все репозитории из двух частей пути делят одну запись.
        prefixes = tuple(instance_prefix_candidates(request.segments))
        key = (request.secure, request.host, request.port, prefixes, request.providers, request.ca_file)
        now = time.monotonic()
        cached = self._cache.get(key)
        if cached is not None and now < cached[0]:
            return cached[1]
        found, answered = await self._search(request, prefixes)
        # Надолго запоминается только то, что сказал сам сервер; «не отвечает» не должно скрывать провайдера
        # после того, как сервер оправился или человек добавил его сертификат.
        self._remember(key, found, _CACHE_TTL_S if answered else _FAILURE_TTL_S)
        return found

    def _remember(self, key: tuple[object, ...], found: ApiDetection | None, ttl_s: float) -> None:
        now = time.monotonic()
        if len(self._cache) >= _CACHE_MAX_ENTRIES:
            for stale in [name for name, (until, _) in self._cache.items() if until <= now]:
                del self._cache[stale]
        while len(self._cache) >= _CACHE_MAX_ENTRIES:
            del self._cache[next(iter(self._cache))]
        self._cache.pop(key, None)
        self._cache[key] = (now + ttl_s, found)

    async def _search(
        self, request: DetectionRequest, prefixes: tuple[str, ...]
    ) -> tuple[ApiDetection | None, bool]:
        """Найденный провайдер и признак, что ответ окончательный: нашли или каждый сервер ответил по-своему."""
        candidates = [(provider, prefix) for provider in request.providers for prefix in prefixes]
        if not candidates:
            return None, True
        async with httpx.AsyncClient(
            verify=_ssl_context(request.ca_file),
            timeout=self._timeout_s,
            follow_redirects=False,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
        ) as client:
            fetcher = _Fetcher(client, self._timeout_s)
            results = await asyncio.gather(
                *(self._probe(fetcher, request, provider, prefix) for provider, prefix in candidates)
            )
        found = next((detection for detection, _ in results if detection is not None), None)
        return found, found is not None or all(answered for _, answered in results)

    async def _probe(
        self, fetcher: _Fetcher, request: DetectionRequest, provider: GitProvider, prefix: str
    ) -> tuple[ApiDetection | None, bool]:
        """(провайдер, ответил ли сервер): таймаут и сбой соединения дают (None, False), а не «здесь такого нет»."""
        spec = provider_spec(provider)
        base = web_base(host=request.host, port=request.port, secure=request.secure, subpath=prefix)
        if spec.api.detect is None or base is None:
            return None, True
        try:
            response = await fetcher.get(base + spec.api.detect.path)
        except (httpx.HTTPError, ssl.SSLError, OSError):
            return None, False
        version = self._recognize(provider, response)
        if version is None:
            return None, True
        return ApiDetection(provider, version[0], api_base(provider, host=request.host, base=base)), True

    @staticmethod
    def _recognize(provider: GitProvider, response: _Reply) -> tuple[str | None] | None:
        """(версия,) если ответ принадлежит провайдеру, иначе None. Версия может быть неизвестна."""
        headers = response.headers
        if provider is GitProvider.github:
            version = _text(headers.get(_GITHUB_ENTERPRISE_HEADER))
            return (version,) if version is not None else None
        body = response.json_object()
        if provider is GitProvider.gitea:
            version = _text(body.get("version")) if body else None
            return (version,) if response.status_code == _HTTP_OK and version is not None else None
        if provider is GitProvider.gitlab:
            if response.status_code == _HTTP_OK and body and "revision" in body:
                return (_text(body.get("version")),)
            # Без доступа GitLab отвечает 401, но узнаётся по своим заголовкам.
            gitlab_header = any(name.lower().startswith("x-gitlab-") for name in headers)
            return (None,) if response.status_code == _HTTP_UNAUTHORIZED and gitlab_header else None
        return None


class HttpTokenIntrospector:
    """Спрашивает у сервера, чей токен, какие у него права и до какого срока он действует."""

    def __init__(
        self, timeout_s: float, certificates: ICertificateService | None = None, *, allow_insecure_http: bool = False
    ) -> None:
        self._timeout_s = timeout_s
        self._certificates = certificates
        self._allow_insecure_http = allow_insecure_http

    async def introspect(self, request: IntrospectionRequest) -> TokenIntrospection:
        if request.api_base.lower().startswith("http://") and not self._allow_insecure_http:
            # Та же политика, что у git: токен открытым текстом идёт только туда, куда администратор это разрешил.
            raise git_error(GitErrorCode.url_scheme_forbidden)
        token = request.token.reveal()
        try:
            async with httpx.AsyncClient(
                verify=_ssl_context(request.ca_file),
                timeout=self._timeout_s,
                follow_redirects=False,
                headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
            ) as client:
                fetcher = _Fetcher(client, self._timeout_s)
                return await self._dispatch(fetcher, request.provider, request.api_base, token)
        except (httpx.TimeoutException, TimeoutError):
            raise git_error(GitErrorCode.timeout) from None
        except httpx.ConnectError as exc:
            raise await self._connect_error(exc, request) from None
        except (httpx.HTTPError, OSError):
            raise git_error(GitErrorCode.offline) from None

    async def _dispatch(self, fetcher: _Fetcher, provider: GitProvider, api: str, token: str) -> TokenIntrospection:
        if provider is GitProvider.gitlab:
            return await _gitlab_self(fetcher, api, token)
        if provider is GitProvider.github:
            return await _github_user(fetcher, api, token)
        if provider is GitProvider.gitea:
            return await _gitea_user(fetcher, api, token)
        return TokenIntrospection(TokenState.unknown)

    async def _connect_error(self, exc: httpx.ConnectError, request: IntrospectionRequest) -> GitSyncError:
        cause: BaseException | None = exc
        while cause is not None and not isinstance(cause, ssl.SSLCertVerificationError):
            cause = cause.__cause__ or cause.__context__
        if not isinstance(cause, ssl.SSLCertVerificationError):
            return git_error(GitErrorCode.offline)
        if cause.verify_code not in _UNTRUSTED_VERIFY_CODES or self._certificates is None:
            return git_error(GitErrorCode.tls_error)
        host_port = _authority(request.api_base)
        try:
            certificate = await self._certificates.fetch(*host_port)
        except GitSyncError:
            return git_error(GitErrorCode.tls_untrusted_ca)
        return git_error(GitErrorCode.tls_untrusted_ca, certificate=certificate.public())


def _authority(url: str) -> tuple[str, int | None]:
    parsed = httpx.URL(url)
    return parsed.host, parsed.port


def _gitlab_date(value: object) -> datetime | None:
    """GitLab отдаёт срок датой (ГГГГ-ММ-ДД): токен перестаёт действовать в полночь UTC этого дня."""
    if not isinstance(value, str):
        return None
    try:
        parsed = date.fromisoformat(value[:10])
    except ValueError:
        return None
    return datetime(parsed.year, parsed.month, parsed.day, tzinfo=timezone.utc)


def _string_list(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return None
    return tuple(value)


def _expired(expires_at: datetime | None) -> bool:
    return expires_at is not None and expires_at <= datetime.now(timezone.utc)


async def _gitlab_self(fetcher: _Fetcher, api: str, token: str) -> TokenIntrospection:
    headers = {"PRIVATE-TOKEN": token}
    response = await fetcher.get(f"{api}/personal_access_tokens/self", headers=headers)
    if response.status_code == _HTTP_UNAUTHORIZED:
        body = response.json_object() or {}
        description = str(body.get("error_description", "")).lower()
        return TokenIntrospection(TokenState.expired if "expired" in description else TokenState.rejected)
    body = response.json_object()
    if response.status_code != _HTTP_OK or body is None:
        return TokenIntrospection(TokenState.unknown)
    expires_at = _gitlab_date(body.get("expires_at"))
    if _expired(expires_at):
        return TokenIntrospection(TokenState.expired, expires_at=expires_at)
    if body.get("revoked") is True or body.get("active") is False:
        return TokenIntrospection(TokenState.rejected, expires_at=expires_at)
    login = await _gitlab_login(fetcher, api, headers, body.get("user_id"))
    return TokenIntrospection(
        TokenState.valid, login=login, scopes=_string_list(body.get("scopes")), expires_at=expires_at
    )


async def _gitlab_login(fetcher: _Fetcher, api: str, headers: Mapping[str, str], user_id: object) -> str | None:
    """Имя владельца нужно для показа; токену только с правами на репозиторий GitLab его не отдаёт."""
    for path in ("/user", f"/users/{user_id}" if isinstance(user_id, int) else None):
        if path is None:
            continue
        try:
            response = await fetcher.get(api + path, headers=headers)
        except (httpx.HTTPError, TimeoutError):
            return None
        body = response.json_object()
        if response.status_code == _HTTP_OK and body and (login := _text(body.get("username"))):
            return login
    return None


def _github_expiry(raw: str | None) -> datetime | None:
    if not raw:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S %Z", "%Y-%m-%d %H:%M:%S %z"):
        try:
            parsed = datetime.strptime(raw.strip(), fmt)  # noqa: DTZ007 — зона разбирается форматом
        except ValueError:
            continue
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    return None


async def _github_user(fetcher: _Fetcher, api: str, token: str) -> TokenIntrospection:
    response = await fetcher.get(f"{api}/user", headers={"Authorization": f"Bearer {token}"})
    if response.status_code == _HTTP_UNAUTHORIZED:
        return TokenIntrospection(TokenState.rejected)
    body = response.json_object()
    if response.status_code != _HTTP_OK or body is None:
        return TokenIntrospection(TokenState.unknown)
    expires_at = _github_expiry(response.headers.get(_GITHUB_EXPIRY_HEADER))
    if _expired(expires_at):
        return TokenIntrospection(TokenState.expired, expires_at=expires_at)
    # Заголовок с правами есть только у классических токенов; у точных токенов его нет, права неизвестны.
    raw_scopes = response.headers.get(_GITHUB_SCOPES_HEADER)
    scopes = None if raw_scopes is None else tuple(item.strip() for item in raw_scopes.split(",") if item.strip())
    return TokenIntrospection(TokenState.valid, login=_text(body.get("login")), scopes=scopes, expires_at=expires_at)


async def _gitea_user(fetcher: _Fetcher, api: str, token: str) -> TokenIntrospection:
    response = await fetcher.get(f"{api}/user", headers={"Authorization": f"token {token}"})
    if response.status_code == _HTTP_UNAUTHORIZED:
        return TokenIntrospection(TokenState.rejected)
    body = response.json_object()
    if response.status_code == _HTTP_FORBIDDEN or response.status_code != _HTTP_OK or body is None:
        # Токен с узкими правами не читает /user: он может быть годным, просто о нём ничего не узнать.
        return TokenIntrospection(TokenState.unknown)
    return TokenIntrospection(TokenState.valid, login=_text(body.get("login") or body.get("username")))
