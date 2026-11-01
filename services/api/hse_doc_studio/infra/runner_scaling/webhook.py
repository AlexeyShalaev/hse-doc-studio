"""Оркестратор через внешний webhook: любая платформа (Nomad, Kubernetes-оператор, свой скрипт) принимает POST.

Тело `{event: "scale", desired, current, reason, metrics, at}`, подпись HMAC-SHA256 тела в заголовке
`X-Autoscale-Signature: sha256=<hex>`. Ответ 2xx значит «принято». Повторов нет: следующий цикл повторит решение.
Адрес проходит проверку исходящих запросов (метаданные облака закрыты, частные сети для админа открыты).
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable
from dataclasses import asdict

import httpx

from hse_doc_studio.core.jobs.autoscale import OrchestratorError, ScaleRequest

SIGNATURE_HEADER = "X-Autoscale-Signature"


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def request_body(request: ScaleRequest) -> bytes:
    return json.dumps(
        {
            "event": "scale",
            "desired": request.desired,
            "current": request.current,
            "reason": request.reason,
            "metrics": asdict(request.metrics),
            "at": request.at.isoformat(),
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


class WebhookOrchestrator:
    def __init__(self, url: str, secret: str | None, client_factory: Callable[[], httpx.AsyncClient]) -> None:
        self._url = url
        self._secret = secret
        self._client_factory = client_factory

    async def scale_to(self, request: ScaleRequest) -> None:
        body = request_body(request)
        headers = {"Content-Type": "application/json"}
        if self._secret:
            headers[SIGNATURE_HEADER] = sign(self._secret, body)
        try:
            async with self._client_factory() as client:
                response = await client.post(self._url, content=body, headers=headers)
        except (httpx.HTTPError, OSError) as exc:
            raise OrchestratorError(f"webhook unreachable: {type(exc).__name__}") from exc
        if not response.is_success:
            raise OrchestratorError(f"webhook answered {response.status_code}")

    async def current(self) -> int | None:
        return None
