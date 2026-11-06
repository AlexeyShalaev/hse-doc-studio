"""HTTP к самим движкам: готовность, список и загрузка моделей, проба «модель отвечает»."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from hse_doc_studio.core.model_servers import Engine, PullProgress

_PING_TIMEOUT_S = 120.0  # первая генерация грузит веса в память


def _headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


class HttpModelServerClient:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    def _client(self, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=timeout, transport=self._transport)

    async def healthy(self, base_url: str, health_path: str, api_key: str = "") -> bool:
        try:
            async with self._client(5.0) as client:
                response = await client.get(f"{base_url}{health_path}", headers=_headers(api_key))
        except httpx.HTTPError:
            return False
        return response.status_code == httpx.codes.OK

    async def installed_models(self, engine: Engine, base_url: str, api_key: str = "") -> list[str]:
        path = "/api/tags" if engine is Engine.ollama else "/v1/models"
        try:
            async with self._client(10.0) as client:
                response = await client.get(f"{base_url}{path}", headers=_headers(api_key))
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return []
        if engine is Engine.ollama:
            return [str(m.get("name")) for m in payload.get("models", []) if m.get("name")]
        return [str(m.get("id")) for m in payload.get("data", []) if m.get("id")]

    async def pull(self, base_url: str, model: str) -> AsyncIterator[PullProgress]:
        try:
            async with (
                httpx.AsyncClient(timeout=httpx.Timeout(None, connect=10.0), transport=self._transport) as client,
                client.stream("POST", f"{base_url}/api/pull", json={"model": model, "stream": True}) as response,
            ):
                if response.status_code != httpx.codes.OK:
                    yield PullProgress("", error=f"HTTP {response.status_code}")
                    return
                async for line in response.aiter_lines():
                    event = _parse_event(line)
                    if event is not None:
                        yield event
                        if event.done or event.error:
                            return
        except httpx.HTTPError as exc:
            yield PullProgress("", error=type(exc).__name__)

    async def delete_model(self, base_url: str, model: str) -> bool:
        try:
            async with self._client(30.0) as client:
                response = await client.request("DELETE", f"{base_url}/api/delete", json={"model": model})
        except httpx.HTTPError:
            return False
        return response.status_code == httpx.codes.OK

    async def ping(self, base_url: str, model: str, api_key: str = "") -> bool:
        body = {"model": model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1}
        try:
            async with self._client(_PING_TIMEOUT_S) as client:
                response = await client.post(f"{base_url}/v1/chat/completions", json=body, headers=_headers(api_key))
        except httpx.HTTPError:
            return False
        return response.status_code == httpx.codes.OK


def _parse_event(line: str) -> PullProgress | None:
    if not line.strip():
        return None
    try:
        obj = json.loads(line)
    except ValueError:
        return None
    if not isinstance(obj, dict):
        return None
    if obj.get("error"):
        return PullProgress("", error=str(obj["error"])[:200])
    status = str(obj.get("status", ""))
    if status == "success":
        return PullProgress(status, percent=100, done=True)
    total, completed = obj.get("total"), obj.get("completed")
    percent = (
        int(completed * 100 / total) if isinstance(total, int) and total > 0 and isinstance(completed, int) else None
    )
    return PullProgress(status, percent=percent)
