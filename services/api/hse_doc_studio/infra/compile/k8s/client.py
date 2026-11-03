"""Клиент Kubernetes API на httpx (REST) и websockets (exec), с токеном ServiceAccount из файла."""

from __future__ import annotations

import asyncio
import json
import ssl
import time
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from pathlib import Path
from typing import IO, TYPE_CHECKING
from urllib.parse import quote, urlencode

import httpx

from hse_doc_studio.infra.compile.k8s.api import ExecResult, KubeApiError, PodManifest, PodState

if TYPE_CHECKING:
    from websockets.asyncio.client import ClientConnection

_TOKEN_TTL_S = 60.0
_EXEC_CHUNK = 64 * 1024
_STDERR_KEEP = 8 * 1024
_REST_TIMEOUT = httpx.Timeout(30.0)
_LOG_TIMEOUT = httpx.Timeout(30.0, read=None)
# Канал 0 stdin, 1 stdout, 2 stderr, 3 статус; в v4 статус приходит JSON-объектом Status.
EXEC_SUBPROTOCOL = "v4.channel.k8s.io"
CH_STDIN, CH_STDOUT, CH_STDERR, CH_STATUS = 0, 1, 2, 3


class TokenSource:
    """Токен projected ServiceAccount ротируется kubelet-ом: файл перечитывается раз в минуту."""

    def __init__(self, path: Path, *, ttl_s: float = _TOKEN_TTL_S) -> None:
        self._path = path
        self._ttl_s = ttl_s
        self._value = ""
        self._read_at = float("-inf")

    def get(self) -> str:
        now = time.monotonic()
        if now - self._read_at >= self._ttl_s:
            try:
                self._value = self._path.read_text(encoding="utf-8").strip()
            except OSError as exc:
                if not self._value:
                    raise KubeApiError(f"cannot read service account token {self._path}: {exc}") from exc
            self._read_at = now
        return self._value


def ssl_context(ca_file: Path) -> ssl.SSLContext:
    if ca_file.is_file():
        return ssl.create_default_context(cafile=str(ca_file))
    return ssl.create_default_context()


def parse_pod_state(pod: Mapping[str, object]) -> PodState:
    status = _obj(pod.get("status"))
    running = False
    waiting_reason = waiting_message = terminated_reason = ""
    exit_code: int | None = None
    for item in _list(status.get("containerStatuses")):
        state = _obj(_obj(item).get("state"))
        if "running" in state:
            running = True
        waiting = _obj(state.get("waiting"))
        if waiting:
            waiting_reason = _str(waiting.get("reason"))
            waiting_message = _str(waiting.get("message"))
        terminated = _obj(state.get("terminated"))
        if terminated:
            terminated_reason = _str(terminated.get("reason"))
            code = terminated.get("exitCode")
            exit_code = code if isinstance(code, int) else None
    unschedulable = ""
    for cond in _list(status.get("conditions")):
        c = _obj(cond)
        if c.get("type") == "PodScheduled" and c.get("status") == "False" and c.get("reason") == "Unschedulable":
            unschedulable = _str(c.get("message")) or "Unschedulable"
    return PodState(
        phase=_str(status.get("phase")) or "Pending",
        reason=_str(status.get("reason")),
        message=_str(status.get("message")),
        container_running=running,
        waiting_reason=waiting_reason,
        waiting_message=waiting_message,
        terminated_reason=terminated_reason,
        terminated_exit_code=exit_code,
        unschedulable=unschedulable,
    )


def exec_exit_code(status: Mapping[str, object]) -> tuple[int, str]:
    """Код выхода из Status канала 3: Success это 0, иначе причина ExitCode или -1 с сообщением."""
    if status.get("status") == "Success":
        return 0, ""
    message = _str(status.get("message"))
    for cause in _list(_obj(status.get("details")).get("causes")):
        c = _obj(cause)
        if c.get("reason") == "ExitCode":
            try:
                return int(_str(c.get("message"))), message
            except ValueError:
                break
    return -1, message or "exec failed"


class ExecFrames:
    """Разбор кадров `v4.channel.k8s.io`: первый байт канал, дальше данные."""

    def __init__(self, stdout: Callable[[bytes], None] | None) -> None:
        self._stdout = stdout
        self._stderr = bytearray()
        self._status: dict[str, object] | None = None

    def feed(self, frame: bytes) -> None:
        if not frame:
            return
        channel, data = frame[0], frame[1:]
        if channel == CH_STDOUT and self._stdout is not None and data:
            self._stdout(data)
        elif channel == CH_STDERR and len(self._stderr) < _STDERR_KEEP:
            self._stderr += data[: _STDERR_KEEP - len(self._stderr)]
        elif channel == CH_STATUS and data:
            self._status = _obj(json.loads(data))

    def result(self, name: str) -> ExecResult:
        text = self._stderr.decode("utf-8", errors="replace")
        if self._status is None:
            raise KubeApiError(f"exec {name}: connection closed without status; {text}".rstrip("; "))
        code, message = exec_exit_code(self._status)
        return ExecResult(exit_code=code, stderr=text or message)


class KubernetesApiClient:
    """`IKubeApi` поверх REST и websocket-exec; транспорт подменяется в тестах."""

    def __init__(
        self,
        api_url: str,
        token: TokenSource,
        ca_file: Path,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_url:
            raise KubeApiError("kubernetes api url is unknown: not in a cluster and HSE_RUNNER__K8S__API_URL is empty")
        self._api_url = api_url.rstrip("/")
        self._token = token
        self._ssl = ssl_context(ca_file) if api_url.startswith("https://") else None
        self._http = httpx.AsyncClient(
            base_url=self._api_url,
            verify=self._ssl if self._ssl is not None else True,
            timeout=_REST_TIMEOUT,
            transport=transport,
        )

    def _headers(self) -> dict[str, str]:
        token = self._token.get()
        return {"Authorization": f"Bearer {token}"} if token else {}

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        body: object = None,
        content_type: str | None = None,
    ) -> httpx.Response:
        headers = self._headers()
        try:
            if content_type is None:
                return await self._http.request(method, path, params=params, json=body, headers=headers)
            headers["Content-Type"] = content_type
            return await self._http.request(
                method, path, params=params, content=json.dumps(body).encode(), headers=headers
            )
        except httpx.HTTPError as exc:
            raise KubeApiError(f"{method} {path}: {exc}") from exc

    async def request_json(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        body: object = None,
        content_type: str | None = None,
    ) -> dict[str, object]:
        """Произвольный вызов REST (Deployment, Job и т. п.): тело ответа как объект; ошибка API это `KubeApiError`
        с `status` (404 тоже: вызывающий сам решает, отсутствие ресурса это норма или сбой)."""
        response = await self._request(method, path, params=params, body=body, content_type=content_type)
        _raise_for(response)
        try:
            return _obj(response.json())
        except ValueError:
            return {}

    async def read_text(self, path: str, *, params: Mapping[str, str] | None = None) -> str:
        """Текстовый ответ (лог пода без `follow`)."""
        response = await self._request("GET", path, params=params)
        _raise_for(response)
        return response.text

    async def create_pod(self, namespace: str, manifest: PodManifest) -> None:
        response = await self._request("POST", f"/api/v1/namespaces/{quote(namespace)}/pods", body=dict(manifest))
        _raise_for(response)

    async def read_pod(self, namespace: str, name: str) -> PodState | None:
        response = await self._request("GET", _pod_path(namespace, name))
        if response.status_code == httpx.codes.NOT_FOUND:
            return None
        _raise_for(response)
        return parse_pod_state(_obj(response.json()))

    async def delete_pod(self, namespace: str, name: str) -> None:
        response = await self._request("DELETE", _pod_path(namespace, name), params={"gracePeriodSeconds": "0"})
        if response.status_code == httpx.codes.NOT_FOUND:
            return
        _raise_for(response)

    async def list_pods(self, namespace: str, label_selector: str) -> list[str]:
        response = await self._request(
            "GET", f"/api/v1/namespaces/{quote(namespace)}/pods", params={"labelSelector": label_selector}
        )
        _raise_for(response)
        items = _list(_obj(response.json()).get("items"))
        return [name for item in items if (name := _str(_obj(_obj(item).get("metadata")).get("name")))]

    async def stream_log(self, namespace: str, name: str, container: str, since_time: str | None) -> AsyncIterator[str]:
        params = {"container": container, "follow": "true", "timestamps": "true"}
        if since_time:
            params["sinceTime"] = since_time
        try:
            async with self._http.stream(
                "GET", f"{_pod_path(namespace, name)}/log", params=params, headers=self._headers(), timeout=_LOG_TIMEOUT
            ) as response:
                if response.is_error:
                    await response.aread()
                    _raise_for(response)
                async for line in response.aiter_lines():
                    yield line
        except httpx.HTTPError as exc:
            raise KubeApiError(f"log {name}: {exc}") from exc

    async def exec(  # noqa: PLR0913
        self,
        namespace: str,
        name: str,
        container: str,
        command: Sequence[str],
        *,
        stdin: IO[bytes] | None = None,
        stdout: Callable[[bytes], None] | None = None,
    ) -> ExecResult:
        from websockets.asyncio.client import connect  # noqa: PLC0415
        from websockets.exceptions import ConnectionClosed, InvalidStatus, WebSocketException  # noqa: PLC0415
        from websockets.typing import Subprotocol  # noqa: PLC0415

        query = [("container", container), ("stdout", "true"), ("stderr", "true")]
        if stdin is not None:
            query.append(("stdin", "true"))
        query += [("command", part) for part in command]
        base = "wss://" + self._api_url[8:] if self._api_url.startswith("https://") else "ws://" + self._api_url[7:]
        url = f"{base}{_pod_path(namespace, name)}/exec?{urlencode(query)}"
        frames = ExecFrames(stdout)
        try:
            async with connect(
                url,
                additional_headers=self._headers(),
                subprotocols=[Subprotocol(EXEC_SUBPROTOCOL)],
                ssl=self._ssl,
                max_size=None,
                compression=None,
                open_timeout=30,
            ) as ws:
                sender = asyncio.create_task(_send_stdin(ws, stdin)) if stdin is not None else None
                try:
                    async for message in ws:
                        frames.feed(message.encode() if isinstance(message, str) else message)
                finally:
                    if sender is not None:
                        sender.cancel()
                        await asyncio.gather(sender, return_exceptions=True)
        except InvalidStatus as exc:
            code = exc.response.status_code
            raise KubeApiError(f"exec {name}: HTTP {code}", status=code) from exc
        except (ConnectionClosed, WebSocketException, OSError, TimeoutError) as exc:
            raise KubeApiError(f"exec {name}: {exc}") from exc
        return frames.result(name)

    async def aclose(self) -> None:
        await self._http.aclose()


async def _send_stdin(ws: ClientConnection, stdin: IO[bytes]) -> None:
    prefix = bytes([CH_STDIN])
    while chunk := await asyncio.to_thread(stdin.read, _EXEC_CHUNK):
        await ws.send(prefix + chunk)


def _pod_path(namespace: str, name: str) -> str:
    return f"/api/v1/namespaces/{quote(namespace)}/pods/{quote(name)}"


def _raise_for(response: httpx.Response) -> None:
    if not response.is_error:
        return
    message, reason = response.text[:500], ""
    try:
        body = _obj(response.json())
        message = _str(body.get("message")) or message
        reason = _str(body.get("reason"))
    except ValueError:
        pass
    raise KubeApiError(message or f"HTTP {response.status_code}", status=response.status_code, reason=reason)


def _obj(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _str(value: object) -> str:
    return value if isinstance(value, str) else ""
