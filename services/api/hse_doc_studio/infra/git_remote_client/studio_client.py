"""HTTP-клиент локальной Студии к серверу Студии: только `/git/-/*` и `/api/v1/auth/device/*` (угроза T26).

Без перенаправлений, с проверкой сертификата как у git (свой CA и закреплённый сертификат из настроек хоста).
"""

from __future__ import annotations

import ssl
from datetime import datetime, timezone
from typing import Any

import httpx

from hse_doc_studio.core.git_remote.client import (
    DeviceGrant,
    DeviceTokenReply,
    StudioAccount,
    StudioProject,
    StudioProjectPage,
    StudioServerError,
    StudioServerErrorCode,
    StudioServerTarget,
)
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.infra.git_sync.tls_certificates import verifying_ssl_context

_USER_AGENT = "HSE-Doc-Studio"
_OK = 200
_BAD_REQUEST = 400
_UNAUTHORIZED = 401


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


class HttpStudioServerClient:
    def __init__(self, timeout_s: float = 20.0) -> None:
        self._timeout_s = timeout_s

    def _client(self, target: StudioServerTarget) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=target.base_url,
            timeout=self._timeout_s,
            follow_redirects=False,
            verify=verifying_ssl_context(target.ca_file),
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
        )

    async def _request(
        self, target: StudioServerTarget, method: str, path: str, **kwargs: Any
    ) -> tuple[int, dict[str, Any]]:
        try:
            async with self._client(target) as client:
                response = await client.request(method, path, **kwargs)
        except (httpx.HTTPError, ssl.SSLError, OSError):
            raise StudioServerError(StudioServerErrorCode.unreachable) from None
        try:
            body = response.json()
        except ValueError:
            body = None
        return response.status_code, body if isinstance(body, dict) else {}

    async def info(self, target: StudioServerTarget) -> str:
        status, body = await self._request(target, "GET", "/git/-/info")
        if status != _OK or body.get("server") != "hse-doc-studio":
            raise StudioServerError(StudioServerErrorCode.not_studio)
        return str(body.get("version", ""))

    async def device_code(self, target: StudioServerTarget, client_name: str) -> DeviceGrant:
        status, body = await self._request(
            target,
            "POST",
            "/api/v1/auth/device/code",
            json={"client_name": client_name, "client_kind": "desktop", "scopes": ["git:read", "git:write"]},
        )
        if status != _OK:
            raise StudioServerError(StudioServerErrorCode.unreachable)
        return DeviceGrant(
            device_code=str(body["device_code"]),
            user_code=str(body["user_code"]),
            verification_uri_complete=str(body["verification_uri_complete"]),
            expires_in=int(body["expires_in"]),
            interval=int(body["interval"]),
        )

    async def device_token(self, target: StudioServerTarget, device_code: str) -> DeviceTokenReply:
        status, body = await self._request(
            target, "POST", "/api/v1/auth/device/token", json={"device_code": device_code}
        )
        if status == _OK and isinstance(body.get("access_token"), str):
            return DeviceTokenReply(
                access_token=Secret(body["access_token"]),
                expires_in=int(body.get("expires_in") or 0) or None,
                scope=str(body.get("scope", "")),
            )
        if status == _BAD_REQUEST and isinstance(body.get("error"), str):
            return DeviceTokenReply(error=body["error"])
        raise StudioServerError(StudioServerErrorCode.unreachable)

    async def whoami(self, target: StudioServerTarget, token: Secret) -> StudioAccount:
        status, body = await self._request(target, "GET", "/git/-/whoami", headers=_auth(token))
        if status == _UNAUTHORIZED:
            raise StudioServerError(StudioServerErrorCode.unauthorized)
        if status != _OK:
            raise StudioServerError(StudioServerErrorCode.unreachable)
        user = _dict(body.get("user"))
        meta = _dict(body.get("token"))
        raw_scopes = body.get("scopes")
        scopes: list[Any] = raw_scopes if isinstance(raw_scopes, list) else []
        return StudioAccount(
            user_id=str(user.get("id", "")),
            name=str(user.get("name", "")),
            scopes=tuple(str(s) for s in scopes),
            expires_at=_parse_dt(meta.get("expires_at")),
        )

    async def projects(
        self, target: StudioServerTarget, token: Secret, *, q: str | None, limit: int, offset: int
    ) -> StudioProjectPage:
        params: dict[str, str | int] = {"limit": limit, "offset": offset}
        if q:
            params["q"] = q
        status, body = await self._request(target, "GET", "/git/-/projects", headers=_auth(token), params=params)
        if status == _UNAUTHORIZED:
            raise StudioServerError(StudioServerErrorCode.unauthorized)
        if status != _OK:
            raise StudioServerError(StudioServerErrorCode.unreachable)
        items = [
            StudioProject(
                id=str(item["id"]),
                name=str(item["name"]),
                owner_name=str(item.get("owner_name", "")),
                role=str(item.get("role", "reader")),
                can_push=bool(item.get("can_push")),
                clone_url=str(item["clone_url"]),
                updated_at=_parse_dt(item.get("updated_at")),
            )
            for item in body.get("items", [])
            if isinstance(item, dict)
        ]
        return StudioProjectPage(
            tuple(items), int(body.get("total", len(items))), int(body.get("limit", limit)), int(body.get("offset", 0))
        )


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _auth(token: Secret) -> dict[str, str]:
    return {"Authorization": f"Bearer {token.reveal()}"}
