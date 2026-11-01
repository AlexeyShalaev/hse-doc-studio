"""Запрос к модели через личный раннер хозяина: задача `ai.relay`, тело в памяти, ответ потоком из канала.

Сервер не открывает адресов в сети человека: задача несёт имя ИИ-адреса, объявленного раннером, и путь из белого
списка. Ретрансляцию ставит и получает только хозяин раннера. Ответ это обычный HTTP-ответ для OpenAI SDK: статус
и тип из заголовка модели, тело порциями по мере прихода от раннера.
"""

from __future__ import annotations

import contextlib
import dataclasses
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

import structlog

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.jobs.admin import RunnerStatus, runner_status
from hse_doc_studio.core.jobs.codec import encode_spec
from hse_doc_studio.core.jobs.entities import JobSpec, job_tags
from hse_doc_studio.core.jobs.enums import JobKind
from hse_doc_studio.core.jobs.errors import QueuedJobNotFoundError
from hse_doc_studio.core.jobs.queue import EnqueueRequest, IJobQueue
from hse_doc_studio.core.jobs.registry import job_kind_spec
from hse_doc_studio.core.jobs.relay import (
    NO_PROJECT_ID,
    AiRelayPayload,
    IRelayChannel,
    IRelayHub,
    RelayErrorCode,
    RelayMethod,
    RelayPath,
    RelayStreamError,
    is_relay_route,
)
from hse_doc_studio.core.jobs.routing import IPersonalRunnerSettings, JobRoute, RouteReason
from hse_doc_studio.core.jobs.runners import IRunnerRepository, Runner, RunnerOwnerKind
from hse_doc_studio.core.jobs.wire import FEATURE_AI_RELAY
from hse_doc_studio.use_cases.ai_relay.request_store import RelayRequestStore
from hse_doc_studio.use_cases.jobs.queue_service import JobQueueService
from hse_doc_studio.use_cases.jobs.wakeup import JobWakeup

logger = structlog.get_logger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class RelayLimits:
    """Пределы ретрансляции (HSE_STUDIO__JOBS__RELAY_*)."""

    pickup_s: float = 10.0
    max_request_bytes: int = 8 * 1024 * 1024
    max_response_bytes: int = 64 * 1024 * 1024
    max_pending_per_user: int = 8
    max_duration_s: float = 900.0
    # Тела и буферы каналов живут в памяти api, а личные раннеры есть у каждого: предел на человека в штуках
    # не держит память процесса. Поэтому ещё байты тел на человека и общий бюджет процесса.
    max_pending_bytes_per_user: int = 16 * 1024 * 1024
    max_pending_total: int = 32
    max_pending_bytes_total: int = 128 * 1024 * 1024


@dataclass(frozen=True)
class RelayRequest:
    runner_id: str
    endpoint: str
    path: RelayPath
    method: RelayMethod
    body: bytes
    content_type: str | None
    stream: bool
    head_timeout_s: float
    idle_timeout_s: float
    project_id: UUID | None


class RelayResponse(Protocol):
    status_code: int
    content_type: str | None

    def aiter_bytes(self) -> AsyncIterator[bytes]: ...

    async def aclose(self) -> None: ...


class AiRelayError(Exception):
    """Ретрансляция невозможна или оборвалась; `code` из `RelayErrorCode`, имя раннера для текста ошибки."""

    def __init__(self, code: RelayErrorCode, *, runner_name: str | None = None, reason: str = "") -> None:
        super().__init__(f"{code.value}: {reason}" if reason else code.value)
        self.code = code
        self.runner_name = runner_name
        self.reason = reason


class AiRelayTimeoutError(AiRelayError):
    """Модель за раннером не прислала заголовок или замолчала дольше таймаута провайдера."""

    def __init__(self, *, runner_name: str | None, reason: str) -> None:
        super().__init__(RelayErrorCode.upstream_timeout, runner_name=runner_name, reason=reason)


def relay_error_of(exc: BaseException) -> AiRelayError | None:
    """Ищет AiRelayError по цепочке __cause__/__context__ (OpenAI SDK оборачивает транспортные ошибки)."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        if isinstance(current, AiRelayError):
            return current
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return None


def relay_state_of(runner: Runner | None, endpoint: str, *, now: datetime, enabled: bool) -> RelayErrorCode | None:
    """Почему этот раннер сейчас не ретранслирует; `None` значит готов. Порядок как у проверок `open`."""
    if not enabled:
        return RelayErrorCode.disabled
    if runner is None or runner.revoked_at is not None:
        return RelayErrorCode.runner_revoked
    if runner.paused:
        return RelayErrorCode.runner_paused
    if _is_offline(runner, now):
        return RelayErrorCode.runner_offline
    if FEATURE_AI_RELAY not in runner.features or runner.ai_endpoint(endpoint) is None:
        return RelayErrorCode.endpoint_missing
    return None


def _is_offline(runner: Runner, now: datetime) -> bool:
    if runner.offline_at is not None and (runner.last_seen_at is None or runner.offline_at >= runner.last_seen_at):
        return True
    return runner_status(runner, now) is RunnerStatus.offline


class AiRelayClient:
    """`open` ставит задачу `ai.relay` на раннер хозяина и отдаёт поток ответа модели."""

    def __init__(  # noqa: PLR0913
        self,
        queue: IJobQueue,
        queue_service: JobQueueService,
        runners: IRunnerRepository,
        hub: IRelayHub,
        store: RelayRequestStore,
        wakeup: JobWakeup,
        personal_settings: IPersonalRunnerSettings | None = None,
        *,
        limits: RelayLimits | None = None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._queue = queue
        self._service = queue_service
        self._runners = runners
        self._hub = hub
        self._store = store
        self._wakeup = wakeup
        self._settings = personal_settings
        self._limits = limits or RelayLimits()
        self._clock = clock

    async def check(self, actor: Actor, runner_id: str, endpoint: str) -> Runner:
        """Раннер годится как ретранслятор для этого человека, иначе `AiRelayError` с причиной."""
        # Без источника настроек личные раннеры считаются включёнными (значение установки по умолчанию).
        enabled = (await self._settings.current()).enabled if self._settings is not None else True
        runner = await self._runners.get(runner_id)
        if runner is not None and not _owned_by(runner, actor):
            # Чужой раннер неотличим от несуществующего.
            runner = None
        problem = relay_state_of(runner, endpoint, now=self._clock(), enabled=enabled)
        if problem is not None:
            raise AiRelayError(problem, runner_name=runner.name if runner is not None else None)
        assert runner is not None  # noqa: S101 — relay_state_of вернул бы runner_revoked
        return runner

    async def open(self, actor: Actor, request: RelayRequest) -> RelayResponse:
        runner = await self.check(actor, request.runner_id, request.endpoint)
        self._check_request(actor, request, runner.name)
        assert actor.id is not None  # noqa: S101 — check требует владельца с id
        job_id = uuid4()
        stored = self._store.put(job_id, request.body, user_id=actor.id, runner_id=runner.id)
        channel = self._hub.open(job_id)
        try:
            await self._enqueue(job_id, actor, runner, request, stored.sha256)
            self._wakeup.notify()
            status, content_type = await self._await_head(channel, request, runner.name)
        except RelayStreamError as exc:
            await self.abort(job_id)
            raise _stream_error(exc, runner.name) from exc
        except BaseException:
            await self.abort(job_id)
            raise
        logger.info("ai_relay_opened", job_id=str(job_id), runner_id=runner.id, status=status)
        return _ChannelResponse(
            self, job_id, channel, status, content_type, request.idle_timeout_s, runner.name, self._limits
        )

    def _check_request(self, actor: Actor, request: RelayRequest, runner_name: str) -> None:
        if not is_relay_route(request.method.value, request.path.value):
            raise AiRelayError(RelayErrorCode.path_forbidden, runner_name=runner_name)
        if len(request.body) > self._limits.max_request_bytes:
            raise AiRelayError(RelayErrorCode.relay_too_large, runner_name=runner_name)
        if actor.id is not None and self._user_busy(actor.id, len(request.body)):
            raise AiRelayError(RelayErrorCode.relay_busy, runner_name=runner_name)
        if self._process_busy(len(request.body)):
            raise AiRelayError(RelayErrorCode.relay_busy, runner_name=runner_name)

    def _user_busy(self, user_id: str, size: int) -> bool:
        limits = self._limits
        return (
            self._store.pending_for(user_id) >= limits.max_pending_per_user
            or self._store.bytes_for(user_id) + size > limits.max_pending_bytes_per_user
        )

    def _process_busy(self, size: int) -> bool:
        """Бюджет всего процесса: много аккаунтов вместе не выедают память api телами и буферами каналов."""
        limits = self._limits
        return (
            self._store.pending_total() >= limits.max_pending_total
            or self._store.bytes_total() + size > limits.max_pending_bytes_total
        )

    async def _await_head(
        self, channel: IRelayChannel, request: RelayRequest, runner_name: str
    ) -> tuple[int, str | None]:
        """Раннер забрал тело за `pickup_s`, затем модель ответила заголовком за `head_timeout_s`."""
        if not await channel.wait_picked(self._limits.pickup_s):
            raise AiRelayError(RelayErrorCode.relay_unavailable, runner_name=runner_name, reason="pickup_timeout")
        try:
            return await channel.wait_head(request.head_timeout_s)
        except TimeoutError as exc:
            raise AiRelayTimeoutError(runner_name=runner_name, reason="no response head") from exc

    async def _enqueue(self, job_id: UUID, actor: Actor, runner: Runner, request: RelayRequest, sha: str) -> None:
        payload = AiRelayPayload(
            endpoint=request.endpoint,
            path=request.path,
            method=request.method,
            content_type=request.content_type if request.method is RelayMethod.post else None,
            body_sha256=sha if request.method is RelayMethod.post else None,
            body_size=len(request.body) if request.method is RelayMethod.post else 0,
            stream=request.stream,
            head_timeout_s=request.head_timeout_s,
            idle_timeout_s=request.idle_timeout_s,
        )
        project_id = request.project_id or NO_PROJECT_ID
        spec = JobSpec(
            id=job_id,
            kind=JobKind.ai_relay,
            tags=job_tags(JobKind.ai_relay, payload),
            project_id=project_id,
            # Машине хозяина почта и признак админа не нужны (S3).
            actor=dataclasses.replace(actor, email=None, link_id=None, is_instance_admin=False, scopes=frozenset()),
            locale=Lang.ru,
            payload=payload,
        )
        timeout = self._limits.max_duration_s
        policy = job_kind_spec(JobKind.ai_relay).policy
        await self._queue.enqueue(
            EnqueueRequest(
                job_id=job_id,
                kind=JobKind.ai_relay,
                project_id=project_id,
                user_id=UUID(actor.id),
                tags=spec.tags,
                payload={"spec": encode_spec(spec), "manifest": [], "timeout_s": timeout, "actor_role": None},
                priority_class=policy.priority_class,
                max_attempts=policy.max_attempts,
                timeout_s=timeout,
                route=JobRoute.pinned,
                target_runner_id=UUID(runner.id),
                route_reason=RouteReason.pinned,
                fair_share=False,
            )
        )

    async def abort(self, job_id: UUID) -> None:
        """Потребитель ушёл раньше `end`: задача отменяется, раннер узнаёт об этом в подтверждении или пульсе."""
        self.release(job_id)
        with contextlib.suppress(QueuedJobNotFoundError):
            job = await self._queue.get(job_id)
            if job is not None and not job.state.is_terminal:
                await self._service.cancel(job_id)

    def release(self, job_id: UUID) -> None:
        """Тело и канал больше не нужны; раннер, который ещё шлёт порции, получит `cancel`."""
        self._store.drop(job_id)
        self._hub.discard(job_id)


def _owned_by(runner: Runner, actor: Actor) -> bool:
    return runner.owner_kind is RunnerOwnerKind.user and actor.id is not None and runner.owner_id == actor.id


def _stream_error(exc: RelayStreamError, runner_name: str) -> AiRelayError:
    try:
        code = RelayErrorCode(exc.code)
    except ValueError:
        code = RelayErrorCode.relay_unavailable
    if code is RelayErrorCode.upstream_timeout:
        return AiRelayTimeoutError(runner_name=runner_name, reason="upstream timeout")
    return AiRelayError(code, runner_name=runner_name, reason=str(exc))


class _ChannelResponse:
    """Поток тела из канала; закрытие до `end` отменяет задачу."""

    def __init__(  # noqa: PLR0913
        self,
        client: AiRelayClient,
        job_id: UUID,
        channel: IRelayChannel,
        status_code: int,
        content_type: str | None,
        idle_timeout_s: float,
        runner_name: str,
        limits: RelayLimits,
    ) -> None:
        self.status_code = status_code
        self.content_type = content_type
        self.job_id = job_id
        self._client = client
        self._channel = channel
        self._idle = idle_timeout_s
        self._runner_name = runner_name
        self._limits = limits
        self._finished = False
        self._closed = False
        self.bytes_received = 0

    async def aiter_bytes(self) -> AsyncIterator[bytes]:
        while not self._finished:
            try:
                chunk = await self._channel.read(self._idle)
            except TimeoutError as exc:
                await self.aclose()
                raise AiRelayTimeoutError(runner_name=self._runner_name, reason="model went silent") from exc
            except RelayStreamError as exc:
                self._finished = True
                await self.aclose()
                raise _stream_error(exc, self._runner_name) from exc
            if chunk is None:
                self._finished = True
                await self.aclose()
                return
            self.bytes_received += len(chunk)
            if self.bytes_received > self._limits.max_response_bytes:
                await self.aclose()
                raise AiRelayError(RelayErrorCode.relay_too_large, runner_name=self._runner_name)
            yield chunk

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._channel.close()
        if self._finished:
            self._client.release(self.job_id)
            return
        await self._client.abort(self.job_id)
