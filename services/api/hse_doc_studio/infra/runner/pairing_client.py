"""Сопряжение раннера с аккаунтом по коду устройства: `pair/start` и `pair/poll` протокола раннера.

Оба вызова публичные (токена ещё нет), секрет устройства `device_code` знает только этот процесс.
Ответы разбираются строго: лишнее или пропавшее поле это несовместимый сервер, а не повод гадать.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import httpx

from hse_doc_studio.core.jobs.enums import RunnerErrorCode
from hse_doc_studio.core.jobs.wire import RUNNER_API_PREFIX
from hse_doc_studio.infra.runner.client import (
    RUNNER_ID_HEADER,
    RUNNER_VERSION_HEADER,
    RunnerApiError,
    RunnerUnreachable,
)

_START_FIELDS = frozenset(
    {"device_code", "user_code", "verification_uri", "verification_uri_complete", "expires_in", "interval"}
)
_POLL_FIELDS = frozenset({"status", "registration_token"})
# Код протокола «опрос чаще interval»: сервер просит замедлиться, сопряжение при этом живо.
SLOW_DOWN_CODE = "slow_down"


class PairingStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    denied = "denied"
    expired = "expired"


@dataclass(frozen=True)
class PairingStart:
    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str
    expires_in: int
    interval: int


@dataclass(frozen=True)
class PairingPoll:
    status: PairingStatus
    # Непусто ровно один раз: при первом ответе approved.
    registration_token: str | None


class RunnerPairingClient:
    def __init__(
        self,
        server_url: str,
        *,
        version: str,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_s: float = 15.0,
    ) -> None:
        self._http = httpx.AsyncClient(
            base_url=server_url, transport=transport, timeout=timeout_s, follow_redirects=False
        )
        self._version = version

    async def aclose(self) -> None:
        await self._http.aclose()

    async def start(self, name: str, host_kind: str) -> PairingStart:
        body = await self._post("/pair/start", {"name": name, "host_kind": host_kind})
        _require_fields(body, _START_FIELDS)
        return PairingStart(
            device_code=_str(body, "device_code"),
            user_code=_str(body, "user_code"),
            verification_uri=_str(body, "verification_uri"),
            verification_uri_complete=_str(body, "verification_uri_complete"),
            expires_in=_int(body, "expires_in"),
            interval=_int(body, "interval"),
        )

    async def poll(self, device_code: str) -> PairingPoll:
        body = await self._post("/pair/poll", {"device_code": device_code})
        _require_fields(body, _POLL_FIELDS)
        token = body["registration_token"]
        if token is not None and not isinstance(token, str):
            raise RunnerApiError(200, None, "registration_token is not a string")
        try:
            status = PairingStatus(_str(body, "status"))
        except ValueError as exc:
            raise RunnerApiError(200, None, "unknown pairing status") from exc
        return PairingPoll(status=status, registration_token=token)

    async def deregister(self, runner_id: str, runner_token: str) -> None:
        """Раннер снимает себя сам: сервер отзывает его, как если бы хозяин нажал «Отозвать»."""
        headers = {"Authorization": f"Bearer {runner_token}", RUNNER_ID_HEADER: runner_id}
        await self._request("/deregister", None, headers)

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self._request(path, payload, {})
        try:
            body = response.json()
        except ValueError as exc:
            raise RunnerApiError(response.status_code, None, "response is not JSON") from exc
        if not isinstance(body, dict):
            raise RunnerApiError(response.status_code, None, "response is not a JSON object")
        return body

    async def _request(self, path: str, payload: dict[str, Any] | None, headers: dict[str, str]) -> httpx.Response:
        try:
            response = await self._http.post(
                f"{RUNNER_API_PREFIX}{path}", json=payload, headers={RUNNER_VERSION_HEADER: self._version, **headers}
            )
        except httpx.TransportError as exc:
            raise RunnerUnreachable(f"POST {path}: {type(exc).__name__}") from exc
        if response.status_code >= 500:
            raise RunnerUnreachable(f"POST {path}: http {response.status_code}")
        if response.status_code >= 400:
            raise _api_error(response)
        return response


def is_disabled(exc: RunnerApiError) -> bool:
    return exc.code == RunnerErrorCode.runner_disabled.value


def _api_error(response: httpx.Response) -> RunnerApiError:
    code: str | None = None
    detail = response.reason_phrase
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        code = body["code"] if isinstance(body.get("code"), str) else None
        detail = body["detail"] if isinstance(body.get("detail"), str) else detail
    return RunnerApiError(response.status_code, code, detail)


def _require_fields(body: dict[str, Any], expected: frozenset[str]) -> None:
    if set(body) != expected:
        raise RunnerApiError(200, None, f"unexpected pairing response fields: {sorted(set(body) ^ expected)}")


def _str(body: dict[str, Any], key: str) -> str:
    value = body[key]
    if not isinstance(value, str) or not value:
        raise RunnerApiError(200, None, f"{key} is not a non-empty string")
    return value


def _int(body: dict[str, Any], key: str) -> int:
    value = body[key]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RunnerApiError(200, None, f"{key} is not a non-negative integer")
    return value
