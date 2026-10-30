"""Провайдер «через мой раннер»: создание, правка, описание ретрансляции и список моделей через раннер."""

from __future__ import annotations

import asyncio
import base64
import dataclasses
import json
from uuid import UUID

import pytest
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.entities import AIProvider
from hse_doc_studio.core.enums import AIProviderOwnerKind, AIProviderType
from hse_doc_studio.core.jobs.relay import AiEndpointFlavor, RelayErrorCode, RelayEventKind
from hse_doc_studio.core.jobs.routing import PersonalRunnerSettings
from hse_doc_studio.core.jobs.runners import DeclaredAiEndpoint
from hse_doc_studio.core.jobs.wire import RelayEvent
from hse_doc_studio.infra.ai.sdk_model_lister import SdkAIModelLister
from hse_doc_studio.infra.jobs.relay_hub import RelayHub
from hse_doc_studio.use_cases.ai_providers.create_ai_provider import CreateAIProviderInput, CreateAIProviderUC
from hse_doc_studio.use_cases.ai_providers.delete_ai_provider import DeleteAIProviderInput, DeleteAIProviderUC
from hse_doc_studio.use_cases.ai_providers.list_provider_models import ListProviderModelsInput, ListProviderModelsUC
from hse_doc_studio.use_cases.ai_providers.relay_info import (
    AiProviderRunnerInvalidError,
    AiProviderSource,
    ProviderRelayDescriber,
    RelayState,
    source_of,
)
from hse_doc_studio.use_cases.ai_providers.update_ai_provider import UpdateAIProviderInput, UpdateAIProviderUC
from hse_doc_studio.use_cases.ai_relay.client import AiRelayClient, AiRelayError, RelayLimits, relay_error_of
from hse_doc_studio.use_cases.ai_relay.request_store import RelayRequestStore
from hse_doc_studio.use_cases.jobs.queue_service import JobQueueService
from hse_doc_studio.use_cases.jobs.wakeup import JobWakeup

from tests.fakes.auth import InMemoryAuditLog
from tests.fakes.job_queue import InMemoryJobQueue
from tests.fakes.ops import InMemoryAIProviderRepository
from tests.fakes.runners import InMemoryRunnerRepository
from tests.fakes.settings import InMemorySettingsRepository
from tests.fixtures.actors import as_actor
from tests.unit.use_cases.ai_relay.helpers import NOW, OWNER_ID, make_personal_runner

_ANNA = Actor.user(OWNER_ID, "Анна")
_BORIS = Actor.user("0b0b0b0b-0000-4000-8000-000000000000", "Борис")
_RUNNER = "4f1c2b3a5d6e47f89a0b1c2d3e4f5a6b"


@pytest.fixture
async def runners() -> InMemoryRunnerRepository:
    repo = InMemoryRunnerRepository()
    await repo.add(make_personal_runner(_RUNNER))
    return repo


def _input(**changes: object) -> CreateAIProviderInput:
    base = CreateAIProviderInput(
        name="Ollama на ноутбуке",
        type=AIProviderType.runner,
        api_key="",
        runner_id=_RUNNER,
        runner_endpoint="ollama",
        request_timeout_s=120.0,
    )
    return dataclasses.replace(base, **changes)  # type: ignore[arg-type]


async def test__create__own_runner_and_declared_endpoint__no_key_no_url(runners: InMemoryRunnerRepository) -> None:
    repo = InMemoryAIProviderRepository()
    uc = CreateAIProviderUC(repo, relay=ProviderRelayDescriber(runners, clock=lambda: NOW))

    with as_actor(_ANNA):
        created = (await uc.execute(_input(api_key="ignored", base_url="http://10.0.0.1"))).provider

    assert (created.api_key, created.base_url) == ("", "")
    assert (created.runner_id, created.runner_endpoint) == (_RUNNER, "ollama")
    assert await repo.get(created.id) == created


@pytest.mark.parametrize(
    ("actor", "changes"),
    [
        (_BORIS, {}),
        (_ANNA, {"runner_endpoint": "vllm"}),
        (_ANNA, {"runner_id": "nope"}),
        (_ANNA, {"owner_kind": AIProviderOwnerKind.instance}),
    ],
    ids=["someone_elses_runner", "undeclared_endpoint", "unknown_runner", "shared_provider"],
)
async def test__create__invalid_runner__422_code(
    runners: InMemoryRunnerRepository, actor: Actor, changes: dict[str, object]
) -> None:
    uc = CreateAIProviderUC(InMemoryAIProviderRepository(), relay=ProviderRelayDescriber(runners))

    with as_actor(actor), pytest.raises(AiProviderRunnerInvalidError) as caught:
        await uc.execute(_input(**changes))

    assert caught.value.code == "ai_provider_runner_invalid"


async def test__create__revoked_runner__invalid(runners: InMemoryRunnerRepository) -> None:
    await runners.revoke(_RUNNER, NOW)
    uc = CreateAIProviderUC(InMemoryAIProviderRepository(), relay=ProviderRelayDescriber(runners))

    with as_actor(_ANNA), pytest.raises(AiProviderRunnerInvalidError):
        await uc.execute(_input())


async def test__create__local_mode_has_no_runners__invalid() -> None:
    uc = CreateAIProviderUC(InMemoryAIProviderRepository())

    with as_actor(_ANNA), pytest.raises(AiProviderRunnerInvalidError):
        await uc.execute(_input())


async def test__create__direct_provider_still_needs_a_key() -> None:
    uc = CreateAIProviderUC(InMemoryAIProviderRepository())

    with as_actor(_ANNA), pytest.raises(ValueError, match="api_key|API"):
        await uc.execute(_input(type=AIProviderType.openai_compat, runner_id=None, runner_endpoint=None))


async def test__update__kind_cannot_change_and_endpoint_is_revalidated(runners: InMemoryRunnerRepository) -> None:
    repo = InMemoryAIProviderRepository()
    describer = ProviderRelayDescriber(runners)
    with as_actor(_ANNA):
        created = (await CreateAIProviderUC(repo, relay=describer).execute(_input())).provider
        update = UpdateAIProviderUC(repo, relay=describer)

        with pytest.raises(AiProviderRunnerInvalidError):
            await update.execute(UpdateAIProviderInput(provider_id=created.id, type=AIProviderType.openai))
        with pytest.raises(AiProviderRunnerInvalidError):
            await update.execute(UpdateAIProviderInput(provider_id=created.id, runner_endpoint="vllm"))
        renamed = (await update.execute(UpdateAIProviderInput(provider_id=created.id, name="Ноутбук"))).provider

    assert renamed.name == "Ноутбук"
    assert renamed.runner_endpoint == "ollama"


@pytest.mark.parametrize(
    ("changes", "state"),
    [
        ({}, RelayState.ready),
        ({"paused": True}, RelayState.runner_paused),
        ({"last_seen_at": None}, RelayState.runner_offline),
        ({"revoked_at": NOW}, RelayState.runner_revoked),
        ({"ai_endpoints": ()}, RelayState.endpoint_missing),
    ],
)
async def test__describe__relay_state_follows_the_runner(
    runners: InMemoryRunnerRepository, changes: dict[str, object], state: RelayState
) -> None:
    describer = ProviderRelayDescriber(runners, clock=lambda: NOW)
    with as_actor(_ANNA):
        provider = (
            await CreateAIProviderUC(InMemoryAIProviderRepository(), relay=describer).execute(_input())
        ).provider
    await runners.add(make_personal_runner(_RUNNER, **changes))

    with as_actor(_ANNA):
        info = (await describer.describe([provider]))[provider.id]

    assert info.state is state
    assert info.endpoint == "ollama"


class _DisabledSettings:
    async def current(self) -> PersonalRunnerSettings:
        return PersonalRunnerSettings(enabled=False)


async def test__describe__personal_runners_disabled__state_disabled(runners: InMemoryRunnerRepository) -> None:
    describer = ProviderRelayDescriber(runners, clock=lambda: NOW)
    with as_actor(_ANNA):
        provider = (
            await CreateAIProviderUC(InMemoryAIProviderRepository(), relay=describer).execute(_input())
        ).provider

    disabled = ProviderRelayDescriber(runners, _DisabledSettings(), clock=lambda: NOW)
    with as_actor(_ANNA):
        info = (await disabled.describe([provider]))[provider.id]

    assert info.state is RelayState.disabled


async def test__describe__direct_providers_have_no_relay_and_a_source() -> None:
    direct = AIProvider(
        id=UUID(int=5),
        name="x",
        type=AIProviderType.openai,
        api_key="k",
        base_url="",
        models=[],
        created_at=NOW,
        owner_kind=AIProviderOwnerKind.instance,
    )

    assert await ProviderRelayDescriber().describe([direct]) == {}
    assert source_of(direct) is AiProviderSource.instance
    assert source_of(dataclasses.replace(direct, owner_kind=AIProviderOwnerKind.user)) is AiProviderSource.own


async def _answer_models(hub: RelayHub, queue: InMemoryJobQueue) -> None:
    for _ in range(200):
        jobs = await queue.list()
        if jobs:
            break
        await asyncio.sleep(0.005)
    job_id = jobs[0].id
    hub.mark_picked(job_id)
    body = json.dumps({"object": "list", "data": [{"id": "qwen2.5:7b", "object": "model"}]}).encode()
    await hub.push(
        job_id,
        0,
        (
            RelayEvent(kind=RelayEventKind.head, status=200, content_type="application/json"),
            RelayEvent(kind=RelayEventKind.data, data=base64.b64encode(body).decode()),
            RelayEvent(kind=RelayEventKind.end),
        ),
    )


async def test__list_models__runner_provider_goes_through_the_relay_without_egress(
    runners: InMemoryRunnerRepository,
) -> None:
    queue = InMemoryJobQueue(lambda: NOW)
    hub = RelayHub()
    relay = AiRelayClient(
        queue,
        JobQueueService(queue),
        runners,
        hub,
        RelayRequestStore(),
        JobWakeup(),
        limits=RelayLimits(pickup_s=2.0),
        clock=lambda: NOW,
    )
    repo = InMemoryAIProviderRepository()

    class _Egress:
        async def authorize(self, *_args: object, **_kwargs: object) -> None:
            raise AssertionError("egress must not be consulted for a runner provider")

    with as_actor(_ANNA):
        provider = (
            await CreateAIProviderUC(repo, relay=ProviderRelayDescriber(runners, clock=lambda: NOW)).execute(_input())
        ).provider
        uc = ListProviderModelsUC(repo, SdkAIModelLister(relay), egress=_Egress())  # type: ignore[arg-type]
        answering = asyncio.create_task(_answer_models(hub, queue))
        models = (await uc.execute(ListProviderModelsInput(provider_id=provider.id))).models
        await answering

    assert models == ["qwen2.5:7b"]
    (job,) = await queue.list()
    assert job.payload["spec"]["payload"]["path"] == "models"
    assert job.payload["spec"]["payload"]["method"] == "GET"


async def test__list_models__runner_offline__relay_error_reaches_the_caller(
    runners: InMemoryRunnerRepository,
) -> None:
    queue = InMemoryJobQueue(lambda: NOW)
    relay = AiRelayClient(
        queue, JobQueueService(queue), runners, RelayHub(), RelayRequestStore(), JobWakeup(), clock=lambda: NOW
    )
    repo = InMemoryAIProviderRepository()
    with as_actor(_ANNA):
        provider = (
            await CreateAIProviderUC(repo, relay=ProviderRelayDescriber(runners, clock=lambda: NOW)).execute(_input())
        ).provider
    await runners.add(make_personal_runner(_RUNNER, last_seen_at=None))

    with as_actor(_ANNA), pytest.raises(Exception) as caught:  # noqa: PT011 — SDK может обернуть ошибку
        await ListProviderModelsUC(repo, SdkAIModelLister(relay)).execute(ListProviderModelsInput(provider.id))

    error = relay_error_of(caught.value)
    assert isinstance(error, AiRelayError)
    assert error.code is RelayErrorCode.runner_offline


async def test__runner_provider__create_rebind_and_delete_are_audited(runners: InMemoryRunnerRepository) -> None:
    """Провайдер привязывает ретрансляцию к раннеру и адресу: создание, смена адреса и удаление в журнале."""
    runner = await runners.get(_RUNNER)
    assert runner is not None
    await runners.add(
        dataclasses.replace(
            runner, ai_endpoints=(*runner.ai_endpoints, DeclaredAiEndpoint("vllm", AiEndpointFlavor.openai))
        )
    )
    repo, audit = InMemoryAIProviderRepository(), InMemoryAuditLog()
    relay = ProviderRelayDescriber(runners, clock=lambda: NOW)

    with as_actor(_ANNA):
        created = (await CreateAIProviderUC(repo, relay=relay, audit=audit).execute(_input())).provider
        update = UpdateAIProviderUC(repo, relay=relay, audit=audit)
        await update.execute(UpdateAIProviderInput(provider_id=created.id, name="Другое имя"))
        await update.execute(UpdateAIProviderInput(provider_id=created.id, runner_endpoint="vllm"))
        await DeleteAIProviderUC(repo, InMemorySettingsRepository(), audit=audit).execute(
            DeleteAIProviderInput(provider_id=created.id)
        )

    entries = sorted(await audit.list(limit=10), key=lambda e: e.id)
    assert [(e.action, e.actor_id, e.target, e.details["endpoint"]) for e in entries] == [
        ("ai_provider.create", OWNER_ID, str(created.id), "ollama"),
        ("ai_provider.update", OWNER_ID, str(created.id), "vllm"),
        ("ai_provider.delete", OWNER_ID, str(created.id), "vllm"),
    ]
    assert all(e.details["runner_id"] == _RUNNER and e.details["type"] == "runner" for e in entries)


async def test__direct_provider__not_audited() -> None:
    audit = InMemoryAuditLog()
    uc = CreateAIProviderUC(InMemoryAIProviderRepository(), audit=audit)

    with as_actor(_ANNA):
        await uc.execute(_input(type=AIProviderType.openai, api_key="sk-1", runner_id=None, runner_endpoint=None))

    assert await audit.list(limit=10) == []
