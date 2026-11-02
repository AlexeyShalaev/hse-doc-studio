"""Клиент api для апдейтера: опрос работы и доставка событий. Только urllib."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Protocol

PROTOCOL = 1


class ApiUnavailableError(Exception):
    """api не ответил или отказал: событие остаётся в очереди журнала и уйдёт позже."""


class IApi(Protocol):
    def poll(self, *, busy: bool) -> dict[str, Any] | None: ...
    def post_event(self, run_id: str, event: dict[str, Any]) -> None: ...


class HttpApi:
    def __init__(self, base_url: str, token: str, version: str, timeout_s: float = 15.0) -> None:
        self._base = base_url.rstrip("/") + "/api/updater/v1"
        self._token = token
        self._version = version
        self._timeout = timeout_s

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(  # noqa: S310 — адрес api из настроек оператора
            self._base + path,
            data=json.dumps(body).encode(),
            method="POST",
            headers={"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:  # noqa: S310
                data = json.loads(response.read() or b"{}")
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise ApiUnavailableError(str(exc)) from exc
        return data if isinstance(data, dict) else {}

    def poll(self, *, busy: bool) -> dict[str, Any] | None:
        data = self._post("/poll", {"protocol": PROTOCOL, "updater_version": self._version, "busy": busy})
        run = data.get("run")
        return run if isinstance(run, dict) else None

    def post_event(self, run_id: str, event: dict[str, Any]) -> None:
        self._post(f"/runs/{run_id}/events", event)
