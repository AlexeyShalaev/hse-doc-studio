"""Поддельный сервер сопряжения раннера на httpx.MockTransport: `pair/start`, `pair/poll`, `deregister`."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx

DEVICE_CODE = "hsdc_RGV2aWNlQ29kZUV4YW1wbGVWYWx1ZTEyMzQ"
USER_CODE = "BCDF-2345"
PAIRED_TOKEN = "hsrt_UGFpcmluZ1Rva2VuRXhhbXBsZTM"  # noqa: S105 — значение эталона контракта


@dataclass
class FakePairingServer:
    # Ответы pair/poll по порядку; последний повторяется.
    statuses: list[str] = field(default_factory=lambda: ["pending", "approved"])
    start_error: tuple[int, str] | None = None
    poll_errors: list[tuple[int, str]] = field(default_factory=list)
    unreachable: bool = False
    interval: int = 0
    expires_in: int = 600
    starts: list[dict[str, Any]] = field(default_factory=list)
    polls: int = 0
    deregistered: list[tuple[str, str]] = field(default_factory=list)
    _delivered: bool = False

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        if self.unreachable:
            raise httpx.ConnectError("refused", request=request)
        path = request.url.path
        if path.endswith("/pair/start"):
            return self._start(request)
        if path.endswith("/pair/poll"):
            return self._poll(request)
        if path.endswith("/deregister"):
            token = request.headers.get("authorization", "").removeprefix("Bearer ")
            self.deregistered.append((request.headers.get("x-runner-id", ""), token))
            return httpx.Response(204)
        return httpx.Response(404, json={"detail": "x", "code": "not_found"})

    def _start(self, request: httpx.Request) -> httpx.Response:
        if self.start_error is not None:
            status, code = self.start_error
            return httpx.Response(status, json={"detail": code, "code": code})
        self.starts.append(json.loads(request.content))
        uri = "https://studio.example.org/settings/runners/pair"
        return httpx.Response(
            200,
            json={
                "device_code": DEVICE_CODE,
                "user_code": USER_CODE,
                "verification_uri": uri,
                "verification_uri_complete": f"{uri}?code={USER_CODE}",
                "expires_in": self.expires_in,
                "interval": self.interval,
            },
        )

    def _poll(self, request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content) == {"device_code": DEVICE_CODE}
        self.polls += 1
        if self.poll_errors:
            status, code = self.poll_errors.pop(0)
            return httpx.Response(status, json={"detail": code, "code": code})
        status = self.statuses[min(self.polls - 1, len(self.statuses) - 1)]
        token: str | None = None
        if status == "approved":
            # Секрет отдаётся один раз: повтор после выдачи это уже expired.
            if self._delivered:
                status = "expired"
            else:
                self._delivered = True
                token = PAIRED_TOKEN
        return httpx.Response(200, json={"status": status, "registration_token": token})
