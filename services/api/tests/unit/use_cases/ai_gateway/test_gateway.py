"""ИИ-шлюз: квоты токенов, белый список, повторы, автомат отказов, замена провайдера, аудит, раннерные провайдеры."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.agent.entities import AgentMessage, NormalizedTurn, StopReason, TokenUsage
from hse_doc_studio.core.ai_gateway.breaker import CircuitBreakers
from hse_doc_studio.core.ai_gateway.errors import AiModelNotAllowedError, AiProviderUnavailableError
from hse_doc_studio.core.ai_gateway.usage import AiOperation, AiOutcome, AiUsageRecord
from hse_doc_studio.core.entities import AIProvider
from hse_doc_studio.core.enums import AIProviderOwnerKind, AIProviderType
from hse_doc_studio.core.quotas.errors import QuotaExceededError
from hse_doc_studio.core.quotas.kinds import QuotaKind
from hse_doc_studio.use_cases.admin.ops_quotas import QuotaService
from hse_doc_studio.use_cases.ai_gateway.gateway import AiGateway, GatewayConfig
from hse_doc_studio.use_cases.quotas.gate import QuotaGate

from tests.fakes.identity import InMemoryInstanceSettingsRepository
from tests.fakes.job_quotas import FixedProjectOrgs, InMemoryQuotaOverrides
from tests.fakes.ops import InMemoryAIProviderRepository
from tests.fakes.quotas import InMemoryFootprint, InMemoryUsageCounters
from tests.fixtures.actors import as_actor

NOW = datetime(2026, 11, 10, 12, tzinfo=UTC)
USER = uuid4()


class Boom(Exception):  # noqa: N818
    """Временная ошибка провайдера."""


class BadKey(Exception):  # noqa: N818
    """Постоянная ошибка: повтор не поможет."""


def _transient(exc: BaseException) -> bool:
    return isinstance(exc, Boom)


def _turn(tokens_in: int = 10, tokens_out: int = 5) -> NormalizedTurn:
    return NormalizedTurn(
        text="ok",
        tool_calls=(),
        stop_reason=StopReason.end_turn,
        usage=TokenUsage(input_tokens=tokens_in, output_tokens=tokens_out),
    )


class FakeAgent:
    """Ответы по провайдерам: исключение, готовый ход или функция; журнал вызовов."""

    def __init__(self) -> None:
        self.script: dict[UUID, list[object]] = {}
        self.calls: list[UUID] = []
        self.stream_text_first = False

    async def run_turn(self, *, provider: AIProvider, sink: object = None, **_: object) -> NormalizedTurn:
        self.calls.append(provider.id)
        step = self.script.get(provider.id, [_turn()]).pop(0) if self.script.get(provider.id) else _turn()
        if self.stream_text_first and sink is not None:
            sink.on_text_delta("partial")  # type: ignore[attr-defined]
        if isinstance(step, Exception):
            raise step
        assert isinstance(step, NormalizedTurn)
        return step


class FakeLister:
    def __init__(self) -> None:
        self.calls: list[UUID] = []
        self.error: Exception | None = None

    async def list_models(self, provider: AIProvider) -> list[str]:
        self.calls.append(provider.id)
        if self.error:
            raise self.error
        return ["m1"]


class MemoryUsageLog:
    def __init__(self) -> None:
        self.items: list[AiUsageRecord] = []

    async def record(self, item: AiUsageRecord) -> None:
        self.items.append(item)

    async def summary(self, since: datetime) -> list[object]:
        return []

    async def prune(self, before: datetime) -> int:
        return 0


class Sink:
    def __init__(self) -> None:
        self.text: list[str] = []

    def on_text_delta(self, text: str) -> None:
        self.text.append(text)


def _provider(
    name: str,
    *,
    owner: AIProviderOwnerKind = AIProviderOwnerKind.instance,
    models: list[str] | None = None,
    type_: AIProviderType = AIProviderType.openai,
    created: int = 0,
) -> AIProvider:
    return AIProvider(
        id=uuid4(),
        name=name,
        type=type_,
        api_key="k",
        base_url="",
        models=models if models is not None else [],
        created_at=datetime(2026, 1, 1 + created, tzinfo=UTC),
        owner_kind=owner,
    )


class Rig:
    def __init__(self, settings: dict[str, object], org: UUID | None = None) -> None:
        self.settings = InMemoryInstanceSettingsRepository()
        self.values = settings
        self.agent = FakeAgent()
        self.lister = FakeLister()
        self.log = MemoryUsageLog()
        self.counters = InMemoryUsageCounters()
        self.providers = InMemoryAIProviderRepository()
        self.slept: list[float] = []
        self.org = org
        self.gate: QuotaGate
        self.gateway: AiGateway

    async def build(self, *, retries: int = 2, threshold: int = 5) -> Rig:
        for key, value in self.values.items():
            await self.settings.set(key, value, source="admin")
        self.gate = QuotaGate(
            QuotaService(self.settings, InMemoryQuotaOverrides(), ttl_s=0),
            self.counters,
            InMemoryFootprint(),
            clock=lambda: NOW,
        )

        async def sleep(seconds: float) -> None:
            self.slept.append(seconds)

        self.gateway = AiGateway(
            self.agent,  # type: ignore[arg-type]
            self.lister,  # type: ignore[arg-type]
            self.gate,
            self.log,  # type: ignore[arg-type]
            self.providers,
            FixedProjectOrgs(self.org),
            _transient,
            config=GatewayConfig(retries=retries, base_delay_s=1.0, max_delay_s=4.0),
            breakers=CircuitBreakers(threshold=threshold, open_for_s=30),
            clock=lambda: NOW,
            monotonic=lambda: 100.0,
            sleep=sleep,
            jitter=lambda: 0.0,
        )
        return self

    async def turn(
        self, provider: AIProvider, *, model: str = "m1", sink: object = None, project: UUID | None = None
    ) -> NormalizedTurn:
        with as_actor(Actor.user(str(USER), "Анна")):
            return await self.gateway.run_turn(
                provider=provider,
                model=model,
                messages=[AgentMessage(role="user", content="hi")],
                tools=[],
                system=None,
                tool_choice_allowed=False,
                max_output_tokens=10,
                temperature=0.0,
                sink=sink,  # type: ignore[arg-type]
                cancel=asyncio.Event(),
                project_id=project,
            )


async def test__turn__shared_provider_charges_day_and_month_tokens_and_audits() -> None:
    rig = await Rig({"quota.ai_tokens_month.user": 1000}).build()
    shared = _provider("shared")

    turn = await rig.turn(shared)

    assert turn.text == "ok"
    month = (await rig.gate.assess_counted(QuotaKind.ai_tokens_month, USER, None))[0]
    day = (await rig.gate.assess_counted(QuotaKind.ai_tokens_day, USER, None))[0]
    assert (month.used, day.used) == (15, 15)
    (record,) = rig.log.items
    assert (record.outcome, record.counted, record.input_tokens, record.output_tokens) == (AiOutcome.ok, True, 10, 5)
    assert record.operation is AiOperation.turn
    assert record.user_id == str(USER)


async def test__turn__organization_of_the_project_is_charged_too() -> None:
    org = uuid4()
    rig = await Rig({}, org=org).build()

    await rig.turn(_provider("shared"), project=uuid4())

    assert rig.counters.rows[("org", str(org), QuotaKind.ai_tokens_month, NOW.date().replace(day=1))] == 15  # type: ignore[index]
    assert rig.log.items[0].org_id == str(org)


async def test__turn__exhausted_token_quota_is_denied_before_the_provider_is_called() -> None:
    rig = await Rig({"quota.ai_tokens_day.user": 10, "quota.on_exceed": "reject"}).build()
    shared = _provider("shared")
    await rig.turn(shared)

    with pytest.raises(QuotaExceededError) as caught:
        await rig.turn(shared)

    assert caught.value.kind is QuotaKind.ai_tokens_day
    assert len(rig.agent.calls) == 1
    assert [r.outcome for r in rig.log.items] == [AiOutcome.ok, AiOutcome.denied]


async def test__turn__warn_mode_lets_an_exhausted_quota_through() -> None:
    rig = await Rig({"quota.ai_tokens_day.user": 10, "quota.on_exceed": "warn"}).build()
    shared = _provider("shared")

    await rig.turn(shared)
    await rig.turn(shared)

    assert len(rig.agent.calls) == 2


async def test__turn__model_outside_the_allow_list_is_refused_and_audited() -> None:
    rig = await Rig({}).build()

    with pytest.raises(AiModelNotAllowedError):
        await rig.turn(_provider("shared", models=["m1"]), model="expensive")

    assert rig.agent.calls == []
    assert rig.log.items[0].outcome is AiOutcome.denied


async def test__turn__personal_provider_is_audited_but_not_counted() -> None:
    rig = await Rig({"quota.ai_tokens_day.user": 1, "quota.on_exceed": "reject"}).build()
    mine = _provider("mine", owner=AIProviderOwnerKind.user)

    await rig.turn(mine)
    await rig.turn(mine)

    assert (await rig.gate.assess_counted(QuotaKind.ai_tokens_day, USER, None))[0].used == 0
    assert [(r.counted, r.provider_owner) for r in rig.log.items] == [(False, "user")] * 2


async def test__turn__runner_provider_bypasses_accounting_and_audit_entirely() -> None:
    rig = await Rig({"quota.ai_tokens_day.user": 1, "quota.on_exceed": "reject"}).build()
    via_runner = _provider("home", owner=AIProviderOwnerKind.user, type_=AIProviderType.runner)

    await rig.turn(via_runner)
    await rig.turn(via_runner)

    assert rig.log.items == []
    assert rig.counters.rows == {}
    assert len(rig.agent.calls) == 2


async def test__turn__transient_error_is_retried_with_growing_pauses() -> None:
    rig = await Rig({}).build(retries=2)
    shared = _provider("shared")
    rig.agent.script[shared.id] = [Boom(), Boom(), _turn()]

    turn = await rig.turn(shared)

    assert turn.text == "ok"
    assert rig.slept == [1.0, 2.0]
    assert [r.outcome for r in rig.log.items] == [AiOutcome.error, AiOutcome.error, AiOutcome.ok]


async def test__turn__permanent_error_is_not_retried_and_does_not_trip_the_breaker() -> None:
    rig = await Rig({}).build(threshold=1)
    shared = _provider("shared")
    rig.agent.script[shared.id] = [BadKey(), _turn()]

    with pytest.raises(BadKey):
        await rig.turn(shared)
    await rig.turn(shared)

    assert rig.slept == []
    assert len(rig.agent.calls) == 2


async def test__turn__no_retry_after_the_stream_has_started() -> None:
    rig = await Rig({}).build()
    rig.agent.stream_text_first = True
    shared = _provider("shared")
    rig.agent.script[shared.id] = [Boom(), _turn()]
    sink = Sink()

    with pytest.raises(Boom):
        await rig.turn(shared, sink=sink)

    assert sink.text == ["partial"]
    assert len(rig.agent.calls) == 1


async def test__turn__fails_over_to_another_shared_provider_with_the_same_model() -> None:
    rig = await Rig({}).build(retries=0)
    primary, backup, other_model = (
        _provider("primary", created=1),
        _provider("backup", created=2, models=["m1"]),
        _provider("other", created=3, models=["zzz"]),
    )
    for item in (primary, backup, other_model):
        await rig.providers.create(item)
    rig.agent.script[primary.id] = [Boom()]

    turn = await rig.turn(primary)

    assert turn.text == "ok"
    assert rig.agent.calls == [primary.id, backup.id]
    assert [(r.provider_id, r.outcome) for r in rig.log.items] == [
        (primary.id, AiOutcome.error),
        (backup.id, AiOutcome.ok),
    ]


async def test__turn__breaker_opens_then_calls_fail_fast_without_touching_the_provider() -> None:
    rig = await Rig({}).build(retries=0, threshold=2)
    shared = _provider("shared")
    rig.agent.script[shared.id] = [Boom(), Boom()]
    for _ in range(2):
        with pytest.raises(Boom):
            await rig.turn(shared)

    with pytest.raises(AiProviderUnavailableError):
        await rig.turn(shared)

    assert len(rig.agent.calls) == 2
    assert rig.log.items[-1].outcome is AiOutcome.unavailable


async def test__list_models__is_audited_without_tokens_and_retried() -> None:
    rig = await Rig({"quota.ai_tokens_day.user": 1, "quota.on_exceed": "reject"}).build()
    shared = _provider("shared")

    with as_actor(Actor.user(str(USER), "Анна")):
        models = await rig.gateway.list_models(shared)

    assert models == ["m1"]
    assert rig.log.items[0].operation is AiOperation.models
    assert (await rig.gate.assess_counted(QuotaKind.ai_tokens_day, USER, None))[0].used == 0


async def test__list_models__runner_provider_is_passed_through() -> None:
    rig = await Rig({}).build()

    with as_actor(Actor.user(str(USER), "Анна")):
        await rig.gateway.list_models(_provider("home", type_=AIProviderType.runner))

    assert rig.log.items == []
