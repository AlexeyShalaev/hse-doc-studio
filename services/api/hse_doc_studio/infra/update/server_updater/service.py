"""Цикл апдейтера: опрос api, исполнение запуска, сердцебиение во время работы, доставка событий."""

from __future__ import annotations

import contextlib
import logging
import signal
import threading
import urllib.error
import urllib.request
from pathlib import Path
from types import FrameType
from typing import Any, Protocol

from hse_doc_studio import __version__
from hse_doc_studio.infra.compile.k8s.api import KubeApiError
from hse_doc_studio.infra.update.server_updater.client import ApiUnavailableError, HttpApi, IApi
from hse_doc_studio.infra.update.server_updater.config import UpdaterConfig
from hse_doc_studio.infra.update.server_updater.docker import CliDocker
from hse_doc_studio.infra.update.server_updater.engine import AbortError, Engine
from hse_doc_studio.infra.update.server_updater.journal import Journal

log = logging.getLogger("hse-updater")
MAX_DIGEST_DOC = 64 * 1024


def http_get(url: str, headers: dict[str, str], timeout: float) -> tuple[int, str]:
    """GET без редиректов на чужие схемы; тело ограничено (файл дайджеста крошечный)."""
    request = urllib.request.Request(url, headers=headers, method="GET")  # noqa: S310 — https проверен вызывающим
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return response.status, response.read(MAX_DIGEST_DOC).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, ""
    except (urllib.error.URLError, TimeoutError) as exc:
        raise OSError(str(exc)) from exc


class Heartbeat:
    """Во время запуска сообщает api «жив, занят»: без этого долгий pull выглядел бы потерянным апдейтером."""

    def __init__(self, api: IApi, every_s: float) -> None:
        self._api = api
        self._every = every_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> Heartbeat:
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        while not self._stop.wait(self._every):
            # api гасится на время обновления: молчание ожидаемо
            with contextlib.suppress(ApiUnavailableError):
                self._api.poll(busy=True)


class Runnable(Protocol):
    def recover(self, reason: str = ...) -> None: ...
    def flush(self) -> None: ...
    def execute(self, spec: dict[str, Any]) -> None: ...


def build_kube_engine(config: UpdaterConfig, api: IApi) -> Runnable:
    """Исполнитель kubernetes: клиент и токен ServiceAccount те же, что у исполнителя сборки в подах раннера."""
    from hse_doc_studio.infra.compile.k8s.client import KubernetesApiClient, TokenSource  # noqa: PLC0415
    from hse_doc_studio.infra.compile.k8s.config import KubernetesExecutorConfig  # noqa: PLC0415
    from hse_doc_studio.infra.update.server_updater.kube import KubeCluster  # noqa: PLC0415
    from hse_doc_studio.infra.update.server_updater.kube_engine import KubeEngine  # noqa: PLC0415
    from hse_doc_studio.infra.update.server_updater.kube_journal import KubeJournal  # noqa: PLC0415

    assert config.kube is not None  # noqa: S101
    k8s = KubernetesExecutorConfig(namespace=config.kube.namespace, api_url=config.kube.api_url)
    client = KubernetesApiClient(k8s.resolved_api_url(), TokenSource(k8s.token_file), k8s.ca_file)
    cluster = KubeCluster(client, namespace=k8s.resolved_namespace(), deployment=config.kube.deployment)
    return KubeEngine(config, cluster, api, KubeJournal(config.data_dir / "journal.json", cluster), http_get=http_get)


def serve(config: UpdaterConfig) -> int:
    engine_api: IApi = HttpApi(config.api_url, config.token, config.version or __version__)
    engine: Runnable
    if config.kube is not None:
        engine = build_kube_engine(config, engine_api)
    else:
        engine = Engine(config, CliDocker(), engine_api, Journal(config.data_dir / "journal.json"), http_get=http_get)
    stop = threading.Event()

    def _stop(_sig: int, _frame: FrameType | None) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    where = (
        f"kubernetes deployment={config.kube.deployment}" if config.kube else f"services={','.join(config.services)}"
    )
    log.info("updater started: api=%s %s", config.api_url, where)
    try:
        engine.recover()
    except (AbortError, KubeApiError) as exc:  # кластер недоступен: под перезапустится и повторит
        log.error("cannot recover the previous run: %s", getattr(exc, "message", exc))  # noqa: TRY400
        return 1
    while not stop.is_set():
        engine.flush()
        try:
            spec = engine_api.poll(busy=False)
        except ApiUnavailableError as exc:
            log.warning("api is not reachable: %s", exc)
            spec = None
        if spec is not None:
            log.info("run %s: %s -> %s", spec.get("run_id"), spec.get("from_version"), spec.get("to_version"))
            with Heartbeat(engine_api, config.heartbeat_s):
                engine.execute(spec)
            continue
        stop.wait(config.poll_s)
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        config = UpdaterConfig.from_env(version=__version__)
    except ValueError as exc:
        log.error("%s", exc)  # noqa: TRY400 — трассировка пользователю не нужна
        return 2
    Path(config.data_dir).mkdir(parents=True, exist_ok=True)
    return serve(config)
