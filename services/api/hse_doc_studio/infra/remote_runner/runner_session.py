"""Сессия облачных сборок поверх настоящего цикла раннера: тот же контейнер, что у консольного раннера.

Состояние связи видно по ответам api раннера: наблюдающий транспорт стоит между клиентом протокола и
сетью и ничего не меняет в запросах, кроме первого опроса без ожидания. Шлюз «уступать локальным
сборкам» передаётся циклу раннера: пока он закрыт, цикл не берёт сборки (`free_slots = 0`), но
ретрансляцию ИИ берёт; без открытых облаку моделей он и вовсе не опрашивает сервер.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import structlog
from pydantic import SecretStr

from hse_doc_studio.core.jobs.enums import RunnerErrorCode
from hse_doc_studio.core.jobs.relay import AiEndpointFlavor
from hse_doc_studio.core.jobs.runners import DeclaredAiEndpoint, RunnerHostKind
from hse_doc_studio.core.jobs.wire import FEATURE_AI_RELAY
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
from hse_doc_studio.infra.runner.relay_executor import AiEndpoint, AiRelayExecutor

logger = structlog.get_logger(__name__)

# Токен регистрации не нужен, когда личность уже на диске: клиент восстанавливается по ней.
_NO_REGISTRATION_TOKEN = "hsrt_identity-on-disk"  # noqa: S105 — заглушка, не секрет
_UNAVAILABLE = frozenset({502, 503, 504})


class ObservingTransport(httpx.AsyncBaseTransport):
    """Сообщает слушателю о связи с сервером по ответам опроса и регистрации."""

    def __init__(self, listener: IRunnerSessionListener, *, inner: httpx.AsyncBaseTransport | None = None) -> None:
        self._listener = listener
        self._inner = inner or httpx.AsyncHTTPTransport()
        self._confirmed = False

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        is_poll = path.endswith("/poll")
        if is_poll and not self._confirmed:
            request = _short_poll(request)
        try:
            response = await self._inner.handle_async_request(request)
        except httpx.TransportError:
            if is_poll or path.endswith("/register"):
                self._set_reachable(reachable=False)
            raise
        self._observe(path, response.status_code)
        return response

    def _observe(self, path: str, status: int) -> None:
        if path.endswith("/poll") and status < 400:
            self._set_reachable(reachable=True)
        elif path.endswith("/poll") and status in _UNAVAILABLE:
            self._set_reachable(reachable=False)
        elif path.endswith("/register") and status < 400:
            self._listener.on_registered()

    def _set_reachable(self, *, reachable: bool) -> None:
        self._confirmed = reachable
        self._listener.on_session_state(SessionState.online if reachable else SessionState.offline)

    async def aclose(self) -> None:
        await self._inner.aclose()


def _short_poll(request: httpx.Request) -> httpx.Request:
    """Первый опрос после подключения без ожидания: долгий опрос ответил бы только через 25 с,
    а «в сети» человек должен увидеть сразу. Остальное в запросе не меняется."""
    try:
        body = json.loads(request.content)
    except ValueError:
        return request
    if not isinstance(body, dict):
        return request
    headers = {k: v for k, v in request.headers.items() if k.lower() != "content-length"}
    return httpx.Request(
        request.method, request.url, headers=headers, json={**body, "wait_s": 0}, extensions=request.extensions
    )


class LoopSession:
    def __init__(self, loop: RunnerLoop, relay: AiRelayExecutor, ai_endpoints: tuple[LocalAiEndpoint, ...]) -> None:
        self._loop = loop
        self._relay = relay
        self._names = frozenset(e.name for e in ai_endpoints)

    @property
    def running_jobs(self) -> int:
        return self._loop.running_jobs

    @property
    def announced_endpoints(self) -> frozenset[str]:
        """Имена адресов, о которых знает сервер: только после согласования ретрансляции в `/announce`."""
        return self._names if FEATURE_AI_RELAY in self._loop.features else frozenset()

    def request_stop(self) -> None:
        self._loop.request_stop()

    async def reannounce(self, ai_endpoints: tuple[LocalAiEndpoint, ...]) -> None:
        """Новый список моделей для облака: исполнитель сразу знает адреса, сервер узнаёт имена через `/announce`.

        Цикл не перезапускается, идущие сборки не прерываются.
        """
        self._relay.replace_endpoints(relay_endpoints(ai_endpoints))
        self._names = frozenset(e.name for e in ai_endpoints)
        await self._loop.reannounce(ai_endpoints=declared_endpoints(ai_endpoints))
        logger.info("remote runner ai endpoints updated", names=sorted(self._names))

    async def run(self) -> None:
        try:
            await self._loop.run()
        except RunnerFatalError as exc:
            raise fatal_of(exc) from exc


def relay_endpoints(endpoints: tuple[LocalAiEndpoint, ...]) -> tuple[AiEndpoint, ...]:
    """Адреса для исполнителя ретрансляции: ключ берётся у локального провайдера в момент запроса."""
    return tuple(
        AiEndpoint(name=e.name, base_url=e.base_url, flavor=AiEndpointFlavor(e.flavor), api_key=e.api_key)
        for e in endpoints
    )


def declared_endpoints(endpoints: tuple[LocalAiEndpoint, ...]) -> tuple[DeclaredAiEndpoint, ...]:
    return tuple(DeclaredAiEndpoint(e.name, AiEndpointFlavor(e.flavor)) for e in endpoints)


def fatal_of(exc: RunnerFatalError) -> RunnerSessionFatal:
    """Код отказа сервера из причины `RunnerFatalError` (цикл оборачивает `RunnerApiError`)."""
    cause = exc.__cause__
    code = cause.code if isinstance(cause, RunnerApiError) else None
    if code == RunnerErrorCode.runner_unauthorized.value:
        return RunnerSessionFatal(SessionFatalCode.unauthorized)
    if code == RunnerErrorCode.runner_disabled.value:
        return RunnerSessionFatal(SessionFatalCode.disabled)
    return RunnerSessionFatal(SessionFatalCode.refused, code or "runner_refused")


# Облачные сборки идут со своим томом кэша TeX: том смонтирован на запись как HOME контейнера (кэши luaotfload,
# поиск latexmkrc), и общий с локальными сборками том дал бы документам соавторов (политика owner) путь
# испортить кэш частных локальных проектов хозяина.
CLOUD_CACHE_SUFFIX = "-cloud"


def cloud_cache_volume(local_volume: str) -> str:
    """Том кэша TeX облачных сборок Студии: отдельный от тома локальных сборок."""
    return local_volume + CLOUD_CACHE_SUFFIX


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
            host_kind=RunnerHostKind.desktop,
        )
        observing = ObservingTransport(listener, inner=transport)
        container = create_runner_container(
            config,
            transport=observing,
            host_paths=host_paths,
            ai_endpoints=relay_endpoints(spec.ai_endpoints),
            gate=spec.gate,
        )
        try:
            loop = await container.get(RunnerLoop)
            relay = await container.get(AiRelayExecutor)
            logger.info("remote runner session opened", server=spec.server_url, tags=sorted(tags))
            yield LoopSession(loop, relay, spec.ai_endpoints)
        finally:
            await container.close()

    return open_session
