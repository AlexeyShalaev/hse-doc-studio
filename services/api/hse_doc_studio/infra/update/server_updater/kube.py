"""Kubernetes для апдейтера: узкий синхронный порт `IKube` и его реализация поверх клиента исполнителя сборки.

Клиент (`infra/compile/k8s/client.py`) асинхронный, а движок апдейтера линейный и синхронный (как у compose), поэтому
`KubeCluster` гоняет клиента в собственном потоке с циклом событий и ждёт ответы. Права ServiceAccount (Role чарта)
ровно те, что вызывает этот класс: get/patch одного Deployment по имени, Job, pods и pods/log.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from typing import Any, Protocol
from urllib.parse import quote

from hse_doc_studio.infra.compile.k8s.api import KubeApiError
from hse_doc_studio.infra.compile.k8s.client import KubernetesApiClient

STRATEGIC_MERGE = "application/strategic-merge-patch+json"
MERGE = "application/merge-patch+json"
_CALL_TIMEOUT_S = 120.0
_LOG_TAIL = "400"


class IKube(Protocol):
    """Всё, что апдейтер делает с кластером. Исключения: `KubeApiError` (у него `status`, 404 это «нет такого»)."""

    @property
    def namespace(self) -> str: ...

    def get_deployment(self) -> dict[str, Any]: ...

    def patch_deployment(self, patch: dict[str, Any], *, content_type: str = STRATEGIC_MERGE) -> dict[str, Any]: ...

    def create_job(self, manifest: dict[str, Any]) -> None: ...

    def get_job(self, name: str) -> dict[str, Any] | None: ...

    def list_jobs(self, selector: str) -> list[dict[str, Any]]: ...

    def delete_job(self, name: str) -> None: ...

    def list_pods(self, selector: str) -> list[dict[str, Any]]: ...

    def pod_log(self, name: str, container: str) -> str: ...


class KubeCluster:
    def __init__(self, client: KubernetesApiClient, *, namespace: str, deployment: str) -> None:
        self._client = client
        self._namespace = namespace
        self._deployment = deployment
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, name="kube-client", daemon=True)
        self._thread.start()

    @property
    def namespace(self) -> str:
        return self._namespace

    def _run[T](self, coro: Coroutine[Any, Any, T]) -> T:
        try:
            return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout=_CALL_TIMEOUT_S)
        except TimeoutError as exc:
            raise KubeApiError("kubernetes api call timed out") from exc

    def _ns(self, resource: str, group: str = "api/v1") -> str:
        return f"/{group}/namespaces/{quote(self._namespace)}/{resource}"

    def _call(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        return dict(self._run(self._client.request_json(method, path, **kwargs)))

    def get_deployment(self) -> dict[str, Any]:
        return self._call("GET", self._ns(f"deployments/{quote(self._deployment)}", "apis/apps/v1"))

    def patch_deployment(self, patch: dict[str, Any], *, content_type: str = STRATEGIC_MERGE) -> dict[str, Any]:
        path = self._ns(f"deployments/{quote(self._deployment)}", "apis/apps/v1")
        return self._call("PATCH", path, body=patch, content_type=content_type, params={"fieldManager": "hds-updater"})

    def create_job(self, manifest: dict[str, Any]) -> None:
        self._call("POST", self._ns("jobs", "apis/batch/v1"), body=manifest)

    def get_job(self, name: str) -> dict[str, Any] | None:
        try:
            return self._call("GET", self._ns(f"jobs/{quote(name)}", "apis/batch/v1"))
        except KubeApiError as exc:
            if exc.status == 404:  # noqa: PLR2004
                return None
            raise

    def list_jobs(self, selector: str) -> list[dict[str, Any]]:
        reply = self._call("GET", self._ns("jobs", "apis/batch/v1"), params={"labelSelector": selector})
        return _items(reply)

    def delete_job(self, name: str) -> None:
        try:
            self._call(
                "DELETE", self._ns(f"jobs/{quote(name)}", "apis/batch/v1"), params={"propagationPolicy": "Background"}
            )
        except KubeApiError as exc:
            if exc.status != 404:  # noqa: PLR2004
                raise

    def list_pods(self, selector: str) -> list[dict[str, Any]]:
        return _items(self._call("GET", self._ns("pods"), params={"labelSelector": selector}))

    def pod_log(self, name: str, container: str) -> str:
        params = {"container": container, "tailLines": _LOG_TAIL}
        return self._run(self._client.read_text(self._ns(f"pods/{quote(name)}/log"), params=params))

    def close(self) -> None:
        self._run(self._client.aclose())
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)


def _items(reply: dict[str, Any]) -> list[dict[str, Any]]:
    items = reply.get("items")
    return [i for i in items if isinstance(i, dict)] if isinstance(items, list) else []
