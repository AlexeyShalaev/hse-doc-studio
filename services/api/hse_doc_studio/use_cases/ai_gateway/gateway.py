"""ИИ-шлюз сервера: единая точка вызовов моделей общих провайдеров.

Шлюз стоит перед `IAgentProvider` и `IAIModelLister` и добавляет то, что нужно серверу:

- белый список моделей общего провайдера и квоты токенов (день и месяц) человека и организации проекта;
- повторы временных ошибок, пока в поток ничего не ушло, автомат отказов на провайдера и замену на другой
  общий провайдер с той же моделью;
- аудит каждого вызова (кто, куда, сколько токенов, чем кончилось) без тел запросов.

Провайдер «через мой раннер» идёт мимо учёта и аудита (решение S7: ключи и токены личного раннера сервер не
видит). Личный провайдер со своим ключом пишется в аудит, но в квоту не идёт: платит человек.
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID, uuid4

import structlog

from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.access.entities import ActorKind
from hse_doc_studio.core.agent.entities import AgentMessage, NormalizedTurn, ToolSpec
from hse_doc_studio.core.agent.protocols import IAgentProvider, StreamSink
from hse_doc_studio.core.ai import IAIModelLister
from hse_doc_studio.core.ai_gateway.breaker import CircuitBreakers
from hse_doc_studio.core.ai_gateway.errors import AiModelNotAllowedError, AiProviderUnavailableError
from hse_doc_studio.core.ai_gateway.usage import AiOperation, AiOutcome, AiUsageRecord, IAiUsageLog
from hse_doc_studio.core.entities import AIProvider
from hse_doc_studio.core.enums import AIProviderOwnerKind, AIProviderType
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.jobs.quotas import IProjectOrgReader
from hse_doc_studio.core.quotas.errors import QuotaExceededError
from hse_doc_studio.core.quotas.kinds import QuotaKind
from hse_doc_studio.core.quotas.protocols import IQuotaGate
from hse_doc_studio.core.repositories import IAIProviderRepository

logger = structlog.get_logger()

TOKEN_KINDS = (QuotaKind.ai_tokens_day, QuotaKind.ai_tokens_month)


@dataclass(frozen=True)
class GatewayConfig:
    retries: int = 2
    base_delay_s: float = 0.5
    max_delay_s: float = 8.0

    def delay(self, attempt: int, jitter: float) -> float:
        """Пауза перед повтором: удвоение с потолком и разбросом до четверти, чтобы повторы не шли волной."""
        base = min(self.max_delay_s, self.base_delay_s * (2**attempt))
        return base * (1 + 0.25 * jitter)


@dataclass(frozen=True)
class _Context:
    user_id: UUID | None
    org_id: UUID | None
    project_id: UUID | None


class _Transient(Exception):  # noqa: N818 — внутренний сигнал «попробовать другого провайдера»
    def __init__(self, cause: BaseException) -> None:
        super().__init__(str(cause))
        self.cause = cause


class _TrackingSink:
    """Запоминает, что в поток уже ушли данные: после этого повтор продублировал бы текст в окне чата."""

    def __init__(self, inner: StreamSink | None) -> None:
        self._inner = inner
        self.started = False

    def __getattr__(self, name: str) -> Any:
        target = getattr(self._inner, name)

        def call(*args: Any, **kwargs: Any) -> Any:
            self.started = True
            return target(*args, **kwargs)

        return call


class AiGateway:
    """Реализует `IAgentProvider` и `IAIModelLister`; под ним стоят настоящие SDK-реализации."""

    def __init__(  # noqa: PLR0913
        self,
        agent: IAgentProvider,
        lister: IAIModelLister,
        gate: IQuotaGate,
        usage: IAiUsageLog,
        providers: IAIProviderRepository,
        project_orgs: IProjectOrgReader,
        is_transient: Callable[[BaseException], bool],
        *,
        config: GatewayConfig | None = None,
        breakers: CircuitBreakers | None = None,
        clock: Clock = utc_now,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        self._agent = agent
        self._lister = lister
        self._gate = gate
        self._usage = usage
        self._providers = providers
        self._project_orgs = project_orgs
        self._is_transient = is_transient
        self._config = config or GatewayConfig()
        self.breakers = breakers or CircuitBreakers()
        self._clock = clock
        self._monotonic = monotonic
        self._sleep = sleep
        self._jitter = jitter

    # --- IAgentProvider ---

    async def run_turn(  # noqa: PLR0913
        self,
        *,
        provider: AIProvider,
        model: str,
        messages: Sequence[AgentMessage],
        tools: Sequence[ToolSpec],
        system: str | None,
        tool_choice_allowed: bool,
        max_output_tokens: int,
        temperature: float,
        sink: StreamSink | None,
        cancel: asyncio.Event,
        project_id: UUID | None = None,
    ) -> NormalizedTurn:
        def call(chosen: AIProvider, tracked: _TrackingSink) -> Awaitable[NormalizedTurn]:
            return self._agent.run_turn(
                provider=chosen,
                model=model,
                messages=messages,
                tools=tools,
                system=system,
                tool_choice_allowed=tool_choice_allowed,
                max_output_tokens=max_output_tokens,
                temperature=temperature,
                sink=cast("StreamSink", tracked) if sink is not None else None,
                cancel=cancel,
                project_id=project_id,
            )

        if provider.type is AIProviderType.runner:
            return await call(provider, _TrackingSink(sink))
        ctx = await self._context(project_id)
        metered = provider.owner_kind is AIProviderOwnerKind.instance
        if metered:
            await self._guard(provider, model, ctx, AiOperation.turn)
        tracked = _TrackingSink(sink)
        return await self._with_failover(
            provider, model, ctx, metered, AiOperation.turn, lambda chosen: call(chosen, tracked), tracked, cancel
        )

    # --- IAIModelLister ---

    async def list_models(self, provider: AIProvider) -> list[str]:
        if provider.type is AIProviderType.runner:
            return await self._lister.list_models(provider)
        ctx = await self._context(None)
        metered = provider.owner_kind is AIProviderOwnerKind.instance
        return await self._with_failover(
            provider,
            "",
            ctx,
            metered,
            AiOperation.models,
            self._lister.list_models,
            _TrackingSink(None),
            None,
            alternatives=False,
        )

    # --- допуск ---

    async def _context(self, project_id: UUID | None) -> _Context:
        actor = current_actor()
        user_id: UUID | None = None
        if actor is not None and actor.kind is ActorKind.user and actor.id:
            try:
                user_id = UUID(actor.id)
            except ValueError:
                user_id = None
        org_id = await self._project_orgs.org_of(project_id) if project_id is not None else None
        return _Context(user_id, org_id, project_id)

    async def _guard(self, provider: AIProvider, model: str, ctx: _Context, op: AiOperation) -> None:
        """Белый список моделей и квоты токенов; отказ пишется в аудит."""
        if provider.models and model not in provider.models:
            await self._log(provider, model, ctx, op, AiOutcome.denied, error_code="model_not_allowed")
            raise AiModelNotAllowedError(provider.name, model)
        for kind in TOKEN_KINDS:
            try:
                await self._gate.admit(kind, ctx.user_id, ctx.org_id)
            except QuotaExceededError as exc:
                await self._log(provider, model, ctx, op, AiOutcome.denied, error_code=f"quota_{exc.kind.value}")
                raise

    # --- вызов с повторами и заменой ---

    async def _with_failover[T](  # noqa: PLR0913
        self,
        provider: AIProvider,
        model: str,
        ctx: _Context,
        metered: bool,
        op: AiOperation,
        call: Callable[[AIProvider], Awaitable[T]],
        tracked: _TrackingSink,
        cancel: asyncio.Event | None,
        *,
        alternatives: bool = True,
    ) -> T:
        candidates = [provider]
        if metered and alternatives:
            candidates += await self._alternatives(provider, model)
        last: BaseException | None = None
        for chosen in candidates:
            if not self.breakers.allow(chosen.id, self._monotonic()):
                continue
            try:
                return await self._attempts(chosen, model, ctx, metered, op, call, tracked, cancel)
            except _Transient as exc:
                last = exc.cause
        if last is not None:
            raise last
        await self._log(provider, model, ctx, op, AiOutcome.unavailable, error_code="breaker_open")
        raise AiProviderUnavailableError(provider.name, self.breakers.open_for_s)

    async def _attempts[T](  # noqa: PLR0913
        self,
        provider: AIProvider,
        model: str,
        ctx: _Context,
        metered: bool,
        op: AiOperation,
        call: Callable[[AIProvider], Awaitable[T]],
        tracked: _TrackingSink,
        cancel: asyncio.Event | None,
    ) -> T:
        for attempt in range(self._config.retries + 1):
            began = self._monotonic()
            try:
                result = await call(provider)
            except asyncio.CancelledError:
                self.breakers.release_probe(provider.id)
                raise
            except Exception as exc:
                elapsed = self._monotonic() - began
                transient = self._is_transient(exc)
                if transient:
                    self.breakers.failure(provider.id, self._monotonic())
                else:
                    self.breakers.release_probe(provider.id)
                await self._log(
                    provider, model, ctx, op, AiOutcome.error, error_code=type(exc).__name__, duration_s=elapsed
                )
                if not transient or tracked.started or (cancel is not None and cancel.is_set()):
                    raise
                if attempt < self._config.retries and self.breakers.allow(provider.id, self._monotonic()):
                    await self._sleep(self._config.delay(attempt, self._jitter()))
                    continue
                raise _Transient(exc) from exc
            self.breakers.success(provider.id)
            await self._on_success(provider, model, ctx, metered, op, result, self._monotonic() - began)
            return result
        raise AssertionError("unreachable")  # noqa: S101 — цикл всегда возвращает или бросает

    async def _alternatives(self, failed: AIProvider, model: str) -> list[AIProvider]:
        """Другие общие провайдеры с этой моделью: сначала живые, потом по дате создания."""
        try:
            listed = await self._providers.list_all()
        except Exception:  # noqa: BLE001 — замена необязательна, основной вызов важнее
            logger.warning("ai gateway: provider list failed")
            return []
        now = self._monotonic()
        found = [
            p
            for p in listed
            if p.id != failed.id
            and p.owner_kind is AIProviderOwnerKind.instance
            and p.type is not AIProviderType.runner
            and (not model or not p.models or model in p.models)
        ]
        return sorted(found, key=lambda p: (not self.breakers.allow_peek(p.id, now), p.created_at))

    # --- учёт ---

    async def _on_success(
        self,
        provider: AIProvider,
        model: str,
        ctx: _Context,
        metered: bool,
        op: AiOperation,
        result: object,
        spent: float,
    ) -> None:
        tokens_in = tokens_out = 0
        if isinstance(result, NormalizedTurn):
            tokens_in, tokens_out = result.usage.input_tokens, result.usage.output_tokens
        if metered and op is AiOperation.turn and tokens_in + tokens_out > 0:
            try:
                for kind in TOKEN_KINDS:
                    await self._gate.charge(kind, ctx.user_id, ctx.org_id, tokens_in + tokens_out)
            except Exception:  # noqa: BLE001 — учёт не должен ронять уже полученный ответ
                logger.exception("ai gateway: charge failed")
        await self._log(
            provider, model, ctx, op, AiOutcome.ok, tokens=(tokens_in, tokens_out), counted=metered, duration_s=spent
        )

    async def _log(  # noqa: PLR0913
        self,
        provider: AIProvider,
        model: str,
        ctx: _Context,
        op: AiOperation,
        outcome: AiOutcome,
        *,
        error_code: str | None = None,
        tokens: tuple[int, int] = (0, 0),
        counted: bool = False,
        duration_s: float = 0.0,
    ) -> None:
        record = AiUsageRecord(
            id=uuid4(),
            at=self._clock(),
            user_id=str(ctx.user_id) if ctx.user_id is not None else None,
            org_id=str(ctx.org_id) if ctx.org_id is not None else None,
            project_id=ctx.project_id,
            provider_id=provider.id,
            provider_owner=provider.owner_kind.value,
            model=model[:200],
            operation=op,
            input_tokens=tokens[0],
            output_tokens=tokens[1],
            outcome=outcome,
            error_code=error_code[:64] if error_code else None,
            duration_ms=int(duration_s * 1000),
            counted=counted,
        )
        try:
            await self._usage.record(record)
        except Exception:  # noqa: BLE001 — журнал не должен ронять вызов модели
            logger.exception("ai gateway: usage log failed")
