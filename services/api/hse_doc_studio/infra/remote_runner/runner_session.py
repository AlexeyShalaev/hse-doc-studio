"""Сессия облачных сборок поверх настоящего цикла раннера: тот же контейнер, что у консольного раннера.

Состояние связи видно по ответам api раннера: наблюдающий транспорт стоит между клиентом протокола и
сетью и ничего не меняет в запросах. Он же держит шлюз «уступать локальным сборкам»: пока шлюз
закрыт, опрос до сервера не доходит, сервер не видит раннер в сети и отдаёт сборки общим раннерам.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import httpx
import structlog
from pydantic import SecretStr

from hse_doc_studio.core.jobs.enums import RunnerErrorCode
from hse_doc_studio.infra.compile.host_path_resolver import HostPathResolver
from hse_doc_studio.infra.di.containers.runner import create_runner_container
from hse_doc_studio.infra.remote_runner.session import (
    IRunnerSession,
    IRunnerSessionListener,
    LocalAiEndpoint,
    RunnerSessionFactory,
    RunnerSessionFatal,
    RunnerSessionSpec,
    SessionFatalCode,
    SessionState,
)
from hse_doc_studio.infra.runner.capabilities import detect_tags
from hse_doc_studio.infra.runner.client import RunnerApiError
from hse_doc_studio.infra.runner.config import RunnerConfig
from hse_doc_studio.infra.runner.loop import RunnerFatalError, RunnerLoop

logger = structlog.get_logger(__name__)

# Токен регистрации не нужен, когда личность уже на диске: клиент восстанавливается по ней.
_NO_REGISTRATION_TOKEN = "hsrt_identity-on-disk"  # noqa: S105 — заглушка, не секрет
_GATE_CHECK_S = 1.0
_UNAVAILABLE = frozenset({502, 503, 504})


class ObservingTransport(httpx.AsyncBaseTransport):
    """Сообщает слушателю о связи с сервером и держит опрос, пока шлюз закрыт."""

    def __init__(
        self,
        listener: IRunnerSessionListener,
        gate: Callable[[], bool],
        *,
        hold_s: float,
        inner: httpx.AsyncBaseTransport | None = None,
        gate_check_s: float = _GATE_CHECK_S,
    ) -> None:
        self._listener = listener
        self._gate = gate
        self._hold_s = hold_s
        self._inner = inner or httpx.AsyncHTTPTransport()
        self._gate_check_s = gate_check_s

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        is_poll = path.endswith("/poll")
        if is_poll and not await self._gate_opens():
            # Пустой ответ опроса, будто задач нет: цикл сразу опросит снова и снова упрётся в шлюз.
            return httpx.Response(200, json={"envelope": None}, request=request)
        try:
            response = await self._inner.handle_async_request(request)
        except httpx.TransportError:
            if is_poll or path.endswith("/register"):
                self._listener.on_session_state(SessionState.offline)
            raise
        if is_poll and response.status_code < 400:
            self._listener.on_session_state(SessionState.online)
        elif is_poll and response.status_code in _UNAVAILABLE:
            self._listener.on_session_state(SessionState.offline)
        elif path.endswith("/register") and response.status_code < 400:
            self._listener.on_registered()
        return response

    async def aclose(self) -> None:
        await self._inner.aclose()

    async def _gate_opens(self) -> bool:
        deadline = time.monotonic() + self._hold_s
        while not self._gate():
            if time.monotonic() >= deadline:
                return False
            await asyncio.sleep(self._gate_check_s)
        return True


class LoopSession:
    def __init__(self, loop: RunnerLoop) -> None:
        self._loop = loop

    @property
    def running_jobs(self) -> int:
        return self._loop.running_jobs

    def request_stop(self) -> None:
        self._loop.request_stop()

    async def reannounce(self, ai_endpoints: tuple[LocalAiEndpoint, ...]) -> None:
        """ИИ-адреса доходят до сервера только через /announce протокола 1.1 (срез R2 трека ретрансляции).

        Цикл этой ветки /announce не знает: список хранится в спецификации сессии и уйдёт на сервер,
        как только цикл научится объявлять возможности. Сборки при этом не прерываются.
        """
        logger.info("remote runner ai endpoints updated", names=[e.name for e in ai_endpoints])

    async def run(self) -> None:
        try:
            await self._loop.run()
        except RunnerFatalError as exc:
            raise fatal_of(exc) from exc


def fatal_of(exc: RunnerFatalError) -> RunnerSessionFatal:
    """Код отказа сервера из причины `RunnerFatalError` (цикл оборачивает `RunnerApiError`)."""
    cause = exc.__cause__
    code = cause.code if isinstance(cause, RunnerApiError) else None
    if code == RunnerErrorCode.runner_unauthorized.value:
        return RunnerSessionFatal(SessionFatalCode.unauthorized)
    if code == RunnerErrorCode.runner_disabled.value:
        return RunnerSessionFatal(SessionFatalCode.disabled)
    return RunnerSessionFatal(SessionFatalCode.refused, code or "runner_refused")


def runner_session_factory(
    *,
    cache_volume: str,
    host_paths: HostPathResolver | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> RunnerSessionFactory:
    """Фабрика сессий Студии; `transport` подменяет сеть в тестах."""

    @asynccontextmanager
    async def open_session(spec: RunnerSessionSpec, listener: IRunnerSessionListener) -> AsyncIterator[IRunnerSession]:
        # Теги объявляются явно: без Docker или образа tex нет, сборки LaTeX уходят на общие раннеры.
        tags = detect_tags(office_url=None, tex_available=spec.tex_available)
        config = RunnerConfig(
            api_url=spec.server_url,
            token=SecretStr(spec.registration_token or _NO_REGISTRATION_TOKEN),
            name=spec.name,
            tags=",".join(sorted(tags)),
            concurrency=spec.concurrency,
            data_dir=spec.data_dir,
            tex_image=spec.tex_image,
            tex_cache_volume=cache_volume,
            isolation=True,
        )
        observing = ObservingTransport(listener, spec.gate, hold_s=float(config.poll_wait_s), inner=transport)
        container = create_runner_container(config, transport=observing, host_paths=host_paths)
        try:
            loop = await container.get(RunnerLoop)
            logger.info("remote runner session opened", server=spec.server_url, tags=sorted(tags))
            yield LoopSession(loop)
        finally:
            await container.close()

    return open_session
