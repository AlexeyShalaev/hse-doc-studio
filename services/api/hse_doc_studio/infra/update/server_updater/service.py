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

from hse_doc_studio import __version__
from hse_doc_studio.infra.update.server_updater.client import ApiUnavailableError, HttpApi, IApi
from hse_doc_studio.infra.update.server_updater.config import UpdaterConfig
from hse_doc_studio.infra.update.server_updater.docker import CliDocker
from hse_doc_studio.infra.update.server_updater.engine import Engine
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


def serve(config: UpdaterConfig) -> int:
    engine_api: IApi = HttpApi(config.api_url, config.token, config.version or __version__)
    journal = Journal(config.data_dir / "journal.json")
    engine = Engine(config, CliDocker(), engine_api, journal, http_get=http_get)
    stop = threading.Event()

    def _stop(_sig: int, _frame: FrameType | None) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    log.info("updater started: api=%s services=%s", config.api_url, ",".join(config.services))
    engine.recover()
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
