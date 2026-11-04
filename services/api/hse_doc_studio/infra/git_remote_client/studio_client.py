"""HTTP-клиент локальной Студии к серверу Студии: только `/git/-/*` и `/api/v1/auth/device/*` (угроза T26).

Без перенаправлений, с проверкой сертификата как у git (свой CA и закреплённый сертификат из настроек хоста).
"""

from __future__ import annotations

import hashlib
import ssl
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx

from hse_doc_studio.core.git_remote.client import (
    CloudPdfReply,
    DeviceGrant,
    DeviceTokenReply,
    JsonObject,
    PdfUpload,
    PdfUploadReply,
    PresenceReply,
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
_FORBIDDEN = 403
_NOT_FOUND = 404
_TOO_LARGE = 413
_REJECTED = frozenset({415, 422})
_CREATED = 201
_UPLOAD_CHUNK = 1 << 20
# Загрузка файла идёт дольше обычных вызовов: ответ ждёт, пока сервер примет и запишет тело.
_UPLOAD_TIMEOUT = httpx.Timeout(20.0, read=180.0, write=300.0)
_NOT_MODIFIED = 304
_CONFLICT = 409
_DOWNLOAD_TIMEOUT = httpx.Timeout(20.0, read=120.0)


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

    async def upload_pdf(self, target: StudioServerTarget, token: Secret, upload: PdfUpload) -> PdfUploadReply:
        params = _pdf_params(upload)
        headers = {**_auth(token), "Content-Type": "application/pdf", "Content-Length": str(upload.size)}
        path = f"/git/-/projects/{upload.project_id}/documents/{upload.doc_id}/pdf"
        try:
            async with self._client(target) as client:
                response = await client.put(
                    path, params=params, headers=headers, content=_file_chunks(upload.path), timeout=_UPLOAD_TIMEOUT
                )
        except (httpx.HTTPError, ssl.SSLError, OSError):
            raise StudioServerError(StudioServerErrorCode.unreachable) from None
        try:
            parsed = response.json()
        except ValueError:
            parsed = None
        body = parsed if isinstance(parsed, dict) else {}
        if response.status_code not in {_OK, _CREATED}:
            raise _pdf_failure(response.status_code, body)
        artifact = _dict(body.get("artifact"))
        return PdfUploadReply(
            artifact_id=str(artifact.get("id", "")),
            created=bool(body.get("created")),
            size=int(artifact.get("size") or upload.size),
        )

    async def send_presence(self, target: StudioServerTarget, token: Secret, report: JsonObject) -> PresenceReply:
        status, body = await self._request(target, "POST", "/git/-/presence", headers=_auth(token), json=report)
        if status == _UNAUTHORIZED:
            raise StudioServerError(StudioServerErrorCode.unauthorized)
        if status == _NOT_FOUND:
            raise StudioServerError(StudioServerErrorCode.presence_unsupported)
        if status == _CONFLICT:
            raise StudioServerError(StudioServerErrorCode.too_many_devices)
        if status != _OK:
            raise StudioServerError(StudioServerErrorCode.unreachable)
        return PresenceReply(
            interval_s=int(body.get("interval_s") or 60), online_window_s=int(body.get("online_window_s") or 180)
        )

    async def presence_overview(
        self, target: StudioServerTarget, token: Secret, device_id: str, project_id: UUID | None
    ) -> JsonObject:
        params: dict[str, str] = {"device_id": device_id}
        if project_id is not None:
            params["project_id"] = str(project_id)
        status, body = await self._request(
            target, "GET", "/git/-/presence/overview", headers=_auth(token), params=params
        )
        return _checked(status, body, StudioServerErrorCode.presence_unsupported)

    async def project_builds(self, target: StudioServerTarget, token: Secret, project_id: UUID) -> JsonObject:
        status, body = await self._request(target, "GET", f"/git/-/projects/{project_id}/builds", headers=_auth(token))
        return _checked(status, body, StudioServerErrorCode.presence_unsupported)

    async def download_cloud_pdf(  # noqa: PLR0913 — параметры одной загрузки
        self,
        target: StudioServerTarget,
        token: Secret,
        project_id: UUID,
        doc_id: str,
        dest: Path,
        *,
        known_sha256: str | None,
        max_bytes: int,
    ) -> CloudPdfReply:
        headers = _auth(token)
        if known_sha256:
            headers["If-None-Match"] = f'"{known_sha256}"'
        path = f"/git/-/projects/{project_id}/documents/{doc_id}/pdf"
        try:
            async with (
                self._client(target) as client,
                client.stream("GET", path, headers=headers, timeout=_DOWNLOAD_TIMEOUT) as response,
            ):
                if response.status_code == _NOT_MODIFIED:
                    return CloudPdfReply(unchanged=True, sha256=known_sha256)
                if response.status_code != _OK:
                    await response.aread()
                    raise _cloud_pdf_failure(response.status_code, _json_body(response))
                return await _save_stream(response, dest, max_bytes)
        except (httpx.HTTPError, ssl.SSLError, OSError):
            raise StudioServerError(StudioServerErrorCode.unreachable) from None


def _json_body(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _checked(status: int, body: dict[str, Any], unsupported: str) -> JsonObject:
    if status == _UNAUTHORIZED:
        raise StudioServerError(StudioServerErrorCode.unauthorized)
    if status in {_NOT_FOUND, _FORBIDDEN}:
        raise StudioServerError(unsupported)
    if status != _OK:
        raise StudioServerError(StudioServerErrorCode.unreachable)
    return body


async def _save_stream(response: httpx.Response, dest: Path, max_bytes: int) -> CloudPdfReply:
    """Тело в файл `dest` частями: предел размера и сверка SHA-256 до того, как файл станет виден."""
    declared = response.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > max_bytes:
        raise StudioServerError(StudioServerErrorCode.cloud_pdf_too_large)
    digest = hashlib.sha256()
    size = 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with dest.open("wb") as handle:
            async for chunk in response.aiter_bytes(_UPLOAD_CHUNK):
                size += len(chunk)
                if size > max_bytes:
                    raise StudioServerError(StudioServerErrorCode.cloud_pdf_too_large)
                digest.update(chunk)
                handle.write(chunk)
    except BaseException:
        dest.unlink(missing_ok=True)
        raise
    sha256 = digest.hexdigest()
    claimed = response.headers.get("x-content-sha256")
    if claimed and claimed.lower() != sha256:
        dest.unlink(missing_ok=True)
        raise StudioServerError(StudioServerErrorCode.unreachable)
    pages = response.headers.get("x-pages")
    return CloudPdfReply(
        unchanged=False,
        sha256=sha256,
        size=size,
        source_commit=response.headers.get("x-source-commit"),
        built_at=_parse_dt(response.headers.get("x-built-at")),
        pages=int(pages) if pages and pages.isdigit() else None,
    )


def _cloud_pdf_failure(status: int, body: dict[str, Any]) -> StudioServerError:
    if status == _UNAUTHORIZED:
        return StudioServerError(StudioServerErrorCode.unauthorized)
    if status == _FORBIDDEN:
        return StudioServerError(StudioServerErrorCode.cloud_pdf_forbidden)
    if status == _NOT_FOUND:
        return StudioServerError(StudioServerErrorCode.cloud_pdf_missing)
    if status == _TOO_LARGE:
        return StudioServerError(StudioServerErrorCode.cloud_pdf_too_large)
    return StudioServerError(StudioServerErrorCode.unreachable)


def _pdf_params(upload: PdfUpload) -> dict[str, str | int]:
    """Подпись к файлу в адресе запроса: имя может быть любым, а заголовки HTTP только ASCII."""
    params: dict[str, str | int] = {"sha256": upload.sha256}
    optional: dict[str, str | int | None] = {
        "name": upload.name,
        "pages": upload.pages,
        "commit": upload.source_commit,
        "built_at": upload.built_at.isoformat() if upload.built_at is not None else None,
    }
    params.update({key: value for key, value in optional.items() if value})
    return params


async def _file_chunks(path: Path) -> AsyncIterator[bytes]:
    with path.open("rb") as handle:
        while chunk := handle.read(_UPLOAD_CHUNK):
            yield chunk


def _pdf_failure(status: int, body: dict[str, Any]) -> StudioServerError:
    code = body.get("code")
    if status == _UNAUTHORIZED:
        return StudioServerError(StudioServerErrorCode.unauthorized)
    if status == _FORBIDDEN:
        scope_missing = code == "git_scope_missing"
        return StudioServerError(
            StudioServerErrorCode.pdf_scope_missing if scope_missing else StudioServerErrorCode.pdf_forbidden
        )
    if status == _NOT_FOUND:
        unknown = code == "artifact_unknown_document"
        return StudioServerError(
            StudioServerErrorCode.pdf_unknown_document if unknown else StudioServerErrorCode.pdf_unsupported
        )
    if status == _TOO_LARGE:
        return StudioServerError(StudioServerErrorCode.pdf_too_large)
    if status in _REJECTED:
        return StudioServerError(StudioServerErrorCode.pdf_rejected)
    return StudioServerError(StudioServerErrorCode.unreachable)


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _auth(token: Secret) -> dict[str, str]:
    return {"Authorization": f"Bearer {token.reveal()}"}
