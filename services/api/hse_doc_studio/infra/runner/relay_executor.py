"""Исполнитель `ai.relay` на раннере: запрос к модели в сети хозяина и поток ответа обратно порциями событий.

URL знает только раннер: задача несёт имя адреса из его конфигурации и путь из белого списка. Заголовки сервера
не пересылаются, редиректы не следуются, ключ модели раннер берёт у себя. Отмену приносит подтверждение порции
(`cancel`) или пульс цикла, который отменяет саму задачу; соединение с моделью при этом закрывается.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import httpx

from hse_doc_studio import __version__
from hse_doc_studio.core.jobs.entities import JobResult
from hse_doc_studio.core.jobs.enums import JobErrorCategory, JobStatus
from hse_doc_studio.core.jobs.errors import JobError, JobFailure
from hse_doc_studio.core.jobs.relay import (
    MAX_RELAY_BATCH_BYTES,
    MAX_RELAY_EVENT_BYTES,
    MAX_RELAY_EVENTS,
    AiEndpointFlavor,
    AiRelayPayload,
    AiRelayResult,
    RelayErrorCode,
    RelayEventKind,
    RelayMethod,
    is_relay_route,
)
from hse_doc_studio.core.jobs.wire import JobEnvelope, RelayEvent, RelayEventBatch
from hse_doc_studio.infra.runner.client import RunnerApiError, RunnerClient, RunnerUnreachable
from hse_doc_studio.infra.runner.executor import JobContext, JobOutcome

logger = logging.getLogger(__name__)

CONNECT_TIMEOUT_S = 10.0
# Порция уходит раз в столько секунд или раньше, когда набрался предел порции.
FLUSH_S = 0.05


def _no_key() -> str | None:
    return None


@dataclass(frozen=True)
class AiEndpoint:
    """ИИ-адрес в сети раннера; ключ отдаётся в момент запроса (Студия берёт его у локального провайдера)."""

    name: str
    base_url: str
    flavor: AiEndpointFlavor
    api_key: Callable[[], str | None] = field(default=_no_key, repr=False)


def relay_url(base_url: str, path: str) -> str:
    """URL адреса и пути из белого списка; путь не может выйти за базовый URL."""
    if not path or any(part in path for part in ("..", "//", "?", "#", "\\")) or ":" in path:
        raise ValueError(f"relay path {path!r} is not allowed")
    base = base_url.rstrip("/")
    url = f"{base}/{path}"
    if not url.startswith(base + "/"):
        raise ValueError("relay url escapes the endpoint")
    return url


def _failure(code: RelayErrorCode, detail: str = "") -> JobFailure:
    category = JobErrorCategory.invalid_input if code is RelayErrorCode.path_forbidden else JobErrorCategory.unavailable
    return JobFailure.of(category, code.value, detail or code.value)


class _Emitter:
    """Копит события и шлёт порциями: по таймеру `FLUSH_S` или по пределам порции; помнит `cancel` из ответа."""

    def __init__(self, client: RunnerClient, envelope: JobEnvelope) -> None:
        self._client = client
        self._job_id = str(envelope.spec.id)
        self._token = envelope.job_token
        self._attempt = envelope.attempt
        self._pending: list[RelayEvent] = []
        self._pending_bytes = 0
        self._seq = 0
        self._lock = asyncio.Lock()
        self.cancelled = False

    async def add(self, event: RelayEvent, size: int = 0) -> None:
        if len(self._pending) >= MAX_RELAY_EVENTS or self._pending_bytes + size > MAX_RELAY_BATCH_BYTES:
            await self.flush()
        self._pending.append(event)
        self._pending_bytes += size

    async def flush(self) -> None:
        async with self._lock:
            if not self._pending:
                return
            batch = RelayEventBatch(attempt=self._attempt, seq=self._seq, events=tuple(self._pending))
            self._pending, self._pending_bytes = [], 0
            ack = await self._client.relay_events(self._job_id, self._token, batch)
            self._seq += 1
            # Порция с `end` доставила ответ целиком: дочитавший потребитель уже закрыл канал, и сервер
            # может ответить `cancel` (канала нет). Это не отмена, итог остаётся успешным.
            if ack.cancel and not any(event.kind is RelayEventKind.end for event in batch.events):
                self.cancelled = True

    async def run_timer(self) -> None:
        while True:
            await asyncio.sleep(FLUSH_S)
            await self.flush()


@dataclass
class _Progress:
    status_code: int | None = None
    bytes_out: int = 0
    started: float = field(default_factory=time.monotonic)

    def result(self) -> AiRelayResult:
        return AiRelayResult(
            status_code=self.status_code,
            bytes_out=self.bytes_out,
            upstream_ms=int((time.monotonic() - self.started) * 1000),
        )


class AiRelayExecutor:
    """`JobExecutor` для `JobKind.ai_relay`."""

    def __init__(
        self,
        client: RunnerClient,
        endpoints: Sequence[AiEndpoint],
        *,
        max_response_bytes: int,
        keepalive_s: float = 2.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = client
        self._endpoints = {endpoint.name: endpoint for endpoint in endpoints}
        self._max_response_bytes = max_response_bytes
        self._keepalive_s = keepalive_s
        self._transport = transport

    def replace_endpoints(self, endpoints: Sequence[AiEndpoint]) -> None:
        """Студия меняет список «Моделей для облака» без перезапуска цикла."""
        self._endpoints = {endpoint.name: endpoint for endpoint in endpoints}

    async def execute(self, envelope: JobEnvelope, ctx: JobContext) -> JobOutcome:
        payload = envelope.spec.payload
        if not isinstance(payload, AiRelayPayload):
            raise _failure(RelayErrorCode.path_forbidden, f"not a relay job: {envelope.spec.kind}")
        endpoint = self._endpoints.get(payload.endpoint)
        if endpoint is None:
            raise _failure(RelayErrorCode.endpoint_unknown, f"no ai endpoint {payload.endpoint!r} on this runner")
        if not is_relay_route(payload.method.value, payload.path.value):
            raise _failure(RelayErrorCode.path_forbidden)
        try:
            url = relay_url(endpoint.base_url, payload.path.value)
        except ValueError as exc:
            raise _failure(RelayErrorCode.path_forbidden, str(exc)) from exc
        body = await self._fetch_body(envelope, payload)
        emitter = _Emitter(self._client, envelope)
        timer = asyncio.create_task(emitter.run_timer())
        try:
            return await self._relay(envelope, payload, endpoint, url, body, emitter)
        finally:
            timer.cancel()
            with contextlib.suppress(asyncio.CancelledError, RunnerApiError, RunnerUnreachable):
                await timer

    async def _fetch_body(self, envelope: JobEnvelope, payload: AiRelayPayload) -> bytes:
        # Забрать тело нужно и у GET: по этому вызову сервер узнаёт, что раннер взялся за запрос.
        try:
            body, sha = await self._client.relay_request(str(envelope.spec.id), envelope.job_token)
        except (RunnerApiError, RunnerUnreachable) as exc:
            raise _failure(RelayErrorCode.relay_unavailable, f"relay request body: {exc}") from exc
        digest = hashlib.sha256(body).hexdigest()
        expected = payload.body_sha256 if payload.method is RelayMethod.post else hashlib.sha256(b"").hexdigest()
        if len(body) != payload.body_size or digest != expected or (sha is not None and sha != digest):
            raise _failure(RelayErrorCode.relay_unavailable, "relay request body does not match its hash")
        return body

    def _headers(self, payload: AiRelayPayload, endpoint: AiEndpoint) -> dict[str, str]:
        headers = {
            "Accept": "text/event-stream" if payload.stream else "application/json",
            "User-Agent": f"hse-doc-studio-runner/{__version__}",
        }
        if payload.content_type and payload.method is RelayMethod.post:
            headers["Content-Type"] = payload.content_type
        key = endpoint.api_key()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        return headers

    async def _relay(  # noqa: PLR0913
        self,
        envelope: JobEnvelope,
        payload: AiRelayPayload,
        endpoint: AiEndpoint,
        url: str,
        body: bytes,
        emitter: _Emitter,
    ) -> JobOutcome:
        progress = _Progress()
        timeout = httpx.Timeout(payload.idle_timeout_s, connect=CONNECT_TIMEOUT_S)
        async with httpx.AsyncClient(transport=self._transport, timeout=timeout, follow_redirects=False) as http:
            request = http.build_request(
                payload.method.value, url, content=body or None, headers=self._headers(payload, endpoint)
            )
            try:
                async with asyncio.timeout(payload.head_timeout_s):
                    response = await http.send(request, stream=True)
            except (TimeoutError, httpx.TimeoutException) as exc:
                return await self._fail(emitter, RelayErrorCode.upstream_timeout, f"no response head: {exc!r}")
            except httpx.TransportError as exc:
                return await self._fail(emitter, RelayErrorCode.upstream_unreachable, type(exc).__name__)
            try:
                return await self._stream(response, emitter, progress)
            finally:
                await response.aclose()

    async def _stream(self, response: httpx.Response, emitter: _Emitter, progress: _Progress) -> JobOutcome:
        progress.status_code = response.status_code
        content_type = response.headers.get("content-type")
        await emitter.add(
            RelayEvent(kind=RelayEventKind.head, status=response.status_code, content_type=_short(content_type))
        )
        await emitter.flush()
        try:
            async for chunk in response.aiter_raw():
                progress.bytes_out += len(chunk)
                if progress.bytes_out > self._max_response_bytes:
                    return await self._fail(emitter, RelayErrorCode.response_too_large, "model answer is too large")
                await _forward(emitter, chunk)
                if emitter.cancelled:
                    return _cancelled(progress)
        except httpx.TimeoutException:
            return await self._fail(emitter, RelayErrorCode.upstream_timeout, "model went silent")
        except httpx.TransportError as exc:
            return await self._fail(emitter, RelayErrorCode.upstream_unreachable, type(exc).__name__)
        await emitter.add(RelayEvent(kind=RelayEventKind.end))
        await emitter.flush()
        if emitter.cancelled:
            return _cancelled(progress)
        return JobOutcome(JobResult(status=JobStatus.succeeded, data=progress.result()))

    async def _fail(self, emitter: _Emitter, code: RelayErrorCode, detail: str) -> JobOutcome:
        logger.warning("ai relay failed: %s (%s)", code.value, detail)
        with contextlib.suppress(RunnerApiError, RunnerUnreachable):
            await emitter.add(RelayEvent(kind=RelayEventKind.error, code=code.value))
            await emitter.flush()
        raise _failure(code, detail)


async def _forward(emitter: _Emitter, chunk: bytes) -> None:
    for start in range(0, len(chunk), MAX_RELAY_EVENT_BYTES):
        part = chunk[start : start + MAX_RELAY_EVENT_BYTES]
        await emitter.add(RelayEvent(kind=RelayEventKind.data, data=base64.b64encode(part).decode("ascii")), len(part))


def _cancelled(progress: _Progress) -> JobOutcome:
    error = JobError(JobErrorCategory.internal, RelayErrorCode.cancelled.value, "consumer closed the stream")
    return JobOutcome(JobResult(status=JobStatus.cancelled, data=progress.result(), error=error))


def _short(content_type: str | None) -> str | None:
    return content_type[:128] if content_type else None
