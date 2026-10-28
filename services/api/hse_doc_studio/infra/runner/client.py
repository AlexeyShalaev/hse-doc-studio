from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Mapping
from typing import Any, cast

import httpx

from hse_doc_studio.core.jobs.codec import decode, decode_poll_response, encode
from hse_doc_studio.core.jobs.wire import (
    RUNNER_API_PREFIX,
    ArtifactUploadRequest,
    ArtifactUploadResponse,
    BlobNeedRequest,
    BlobNeedResponse,
    CompleteRequest,
    CompleteResponse,
    HeartbeatRequest,
    HeartbeatResponse,
    LogBatch,
    PollRequest,
    PollResponse,
    RunnerRegisterRequest,
    RunnerRegisterResponse,
)
from hse_doc_studio.infra.runner.backoff import Backoff

logger = logging.getLogger(__name__)

# Заголовки: токен раннера идёт как Bearer, токен задачи из конверта отдельным заголовком.
JOB_TOKEN_HEADER = "X-Job-Token"  # noqa: S105
RUNNER_VERSION_HEADER = "X-Runner-Version"
RUNNER_ID_HEADER = "X-Runner-Id"

_RETRY_STATUSES = frozenset({429, 502, 503, 504})


class RunnerApiError(Exception):
    """Ответ API с ошибкой, которую повтор не исправит: `code` из закрытого списка протокола или None."""

    def __init__(self, status: int, code: str | None, detail: str) -> None:
        super().__init__(f"{status} {code or '-'}: {detail}")
        self.status = status
        self.code = code
        self.detail = detail


class RunnerUnreachable(Exception):  # noqa: N818
    """API недоступен: сеть, таймаут или 5xx после всех повторов. Вызывающий решает, ждать ли."""


class RunnerClient:
    """Клиент протокола раннера поверх httpx.

    Повторяет сетевые сбои и 429/502/503/504 с паузой; остальные 4xx сразу `RunnerApiError`.
    Секреты в журнал не попадают: пишутся только метод, путь и статус.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        version: str,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_s: float = 30.0,
        retries: int = 3,
        backoff_factory: Callable[[], Backoff] = lambda: Backoff(base_s=0.2, cap_s=5.0),
    ) -> None:
        self._token = token
        self._version = version
        self._retries = retries
        self._backoff_factory = backoff_factory
        self._timeout_s = timeout_s
        self._runner_id: str | None = None
        self._http = httpx.AsyncClient(base_url=base_url, transport=transport, timeout=timeout_s)

    async def aclose(self) -> None:
        await self._http.aclose()

    def bind_runner(self, runner_id: str) -> None:
        self._runner_id = runner_id

    def _headers(self, job_token: str | None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self._token}", RUNNER_VERSION_HEADER: self._version}
        if self._runner_id is not None:
            headers[RUNNER_ID_HEADER] = self._runner_id
        if job_token is not None:
            headers[JOB_TOKEN_HEADER] = job_token
        return headers

    async def _send(
        self,
        method: str,
        path: str,
        *,
        job_token: str | None = None,
        json: object | None = None,
        content: bytes | None = None,
        retries: int | None = None,
        timeout_s: float | None = None,
    ) -> httpx.Response:
        url = f"{RUNNER_API_PREFIX}{path}"
        attempts = (self._retries if retries is None else retries) + 1
        backoff = self._backoff_factory()
        for attempt in range(1, attempts + 1):
            try:
                response = await self._http.request(
                    method,
                    url,
                    headers=self._headers(job_token),
                    json=json,
                    content=content,
                    timeout=httpx.USE_CLIENT_DEFAULT if timeout_s is None else timeout_s,
                )
            except httpx.TransportError as exc:
                failure = f"{type(exc).__name__}"
            else:
                if response.status_code < 400:
                    return response
                if response.status_code not in _RETRY_STATUSES:
                    raise _api_error(response)
                failure = f"http {response.status_code}"
            logger.warning("runner api %s %s failed (%s), attempt %d/%d", method, path, failure, attempt, attempts)
            if attempt == attempts:
                raise RunnerUnreachable(f"{method} {path}: {failure}")
            await asyncio.sleep(backoff.next())
        raise AssertionError("unreachable")

    async def register(self, request: RunnerRegisterRequest) -> RunnerRegisterResponse:
        response = await self._send("POST", "/register", json=encode(request))
        registered = decode(RunnerRegisterResponse, _json_object(response))
        self.bind_runner(registered.runner_id)
        return registered

    async def poll(self, request: PollRequest) -> PollResponse:
        # Долгий опрос не повторяем здесь: паузой и перерегистрацией управляет цикл.
        response = await self._send(
            "POST", "/poll", json=encode(request), retries=0, timeout_s=request.wait_s + self._timeout_s
        )
        return decode_poll_response(_json_object(response))

    async def heartbeat(self, job_id: str, job_token: str, request: HeartbeatRequest) -> HeartbeatResponse:
        response = await self._send(
            "POST", f"/jobs/{job_id}/heartbeat", job_token=job_token, json=encode(request), retries=0
        )
        return decode(HeartbeatResponse, _json_object(response))

    async def send_log(self, job_id: str, job_token: str, batch: LogBatch) -> None:
        await self._send("POST", f"/jobs/{job_id}/log", job_token=job_token, json=encode(batch), retries=1)

    async def need_blobs(self, job_id: str, job_token: str, request: BlobNeedRequest) -> BlobNeedResponse:
        response = await self._send("POST", f"/jobs/{job_id}/blobs/need", job_token=job_token, json=encode(request))
        return decode(BlobNeedResponse, _json_object(response))

    async def get_blob(self, job_id: str, job_token: str, sha256: str) -> bytes:
        response = await self._send("GET", f"/jobs/{job_id}/blobs/{sha256}", job_token=job_token)
        return response.content

    async def announce_artifact(
        self, job_id: str, job_token: str, request: ArtifactUploadRequest
    ) -> ArtifactUploadResponse:
        response = await self._send("POST", f"/jobs/{job_id}/artifacts", job_token=job_token, json=encode(request))
        return decode(ArtifactUploadResponse, _json_object(response))

    async def put_artifact(self, job_id: str, job_token: str, sha256: str, data: bytes) -> None:
        await self._send("PUT", f"/jobs/{job_id}/artifacts/{sha256}", job_token=job_token, content=data)

    async def put_to_url(self, url: str, data: bytes) -> None:
        """Загрузка по подписанной ссылке хранилища: наши заголовки и токены туда не уходят."""
        try:
            response = await self._http.put(url, content=data)
        except httpx.TransportError as exc:
            raise RunnerUnreachable(f"PUT presigned url: {type(exc).__name__}") from exc
        if response.status_code >= 400:
            raise RunnerApiError(response.status_code, None, "presigned upload rejected")

    async def complete(self, job_id: str, job_token: str, request: CompleteRequest) -> CompleteResponse:
        response = await self._send(
            "POST", f"/jobs/{job_id}/complete", job_token=job_token, json=encode(request), retries=5
        )
        return decode(CompleteResponse, _json_object(response))


def _json_object(response: httpx.Response) -> dict[str, object]:
    body = response.json()
    if not isinstance(body, dict):
        raise RunnerApiError(response.status_code, None, "response is not a JSON object")
    return cast("dict[str, object]", body)


def _api_error(response: httpx.Response) -> RunnerApiError:
    code: str | None = None
    detail = response.reason_phrase
    try:
        body: Mapping[str, Any] = response.json()
        raw_code, raw_detail = body.get("code"), body.get("detail")
        code = raw_code if isinstance(raw_code, str) else None
        detail = raw_detail if isinstance(raw_detail, str) else detail
    except (ValueError, AttributeError):
        pass
    return RunnerApiError(response.status_code, code, detail)
