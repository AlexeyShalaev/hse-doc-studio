"""Чат и провайдер через раннер: порядок по умолчанию, модель по умолчанию, код ошибки ретрансляции."""

from __future__ import annotations

import dataclasses
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.entities import AgentRunRecord, AIProvider
from hse_doc_studio.core.enums import AgentRunStatus, AIProviderOwnerKind, AIProviderType
from hse_doc_studio.core.jobs.relay import RelayErrorCode
from hse_doc_studio.infra.db.repositories.chat import _error_code_of, _with_error_code
from hse_doc_studio.infra.persistence.serializers import deserialize_agent_run, serialize_agent_run
from hse_doc_studio.use_cases.ai_providers.relay_info import ProviderRelayDescriber
from hse_doc_studio.use_cases.ai_relay.client import AiRelayError
from hse_doc_studio.use_cases.chat._support import describe_run_error, run_error_code
from hse_doc_studio.use_cases.chat.get_chat_run_stream import GetChatRunStreamUC
from hse_doc_studio.use_cases.chat.start_chat_turn import StartChatTurnInput, StartChatTurnUC
from tests.fakes.ops import InMemoryAIProviderRepository
from tests.fakes.runners import InMemoryRunnerRepository
from tests.fixtures.actors import as_actor
from tests.unit.use_cases.ai_relay.helpers import NOW, OWNER_ID, make_personal_runner

_ANNA = Actor.user(OWNER_ID, "Анна")
_RUNNER = "4f1c2b3a5d6e47f89a0b1c2d3e4f5a6b"


def _provider(name: str, *, minutes: int, **changes: Any) -> AIProvider:
    base = AIProvider(
        id=uuid4(),
        name=name,
        type=AIProviderType.openai_compat,
        api_key="k",
        base_url="https://llm.example.org/v1",
        models=[f"{name}-model"],
        created_at=NOW + timedelta(minutes=minutes),
    )
    return dataclasses.replace(base, **changes)


class _Settings:
    def __init__(self, data: dict[str, object] | None = None) -> None:
        self._data = data or {}

    async def get(self) -> dict[str, object]:
        return self._data


async def _resolver(
    providers: list[AIProvider], *, runner_online: bool = True, settings: dict[str, object] | None = None
):  # type: ignore[no-untyped-def]  # noqa: E501
    repo = InMemoryAIProviderRepository()
    for provider in providers:
        await repo.create(provider)
    runners = InMemoryRunnerRepository()
    await runners.add(make_personal_runner(_RUNNER, **({} if runner_online else {"last_seen_at": None})))
    uc = object.__new__(StartChatTurnUC)
    uc._ai_provider_repo = repo  # noqa: SLF001
    uc._settings_repo = _Settings(settings)  # type: ignore[assignment]  # noqa: SLF001
    uc._relay = ProviderRelayDescriber(runners, clock=lambda: NOW)  # noqa: SLF001
    return uc


_INPUT = StartChatTurnInput(project_id=uuid4(), session_id=uuid4())


async def test__default_order__own_before_instance_and_ready_runner_first_by_age() -> None:
    instance = _provider("inst", minutes=0, owner_kind=AIProviderOwnerKind.instance)
    runner = _provider(
        "runner", minutes=1, type=AIProviderType.runner, api_key="", runner_id=_RUNNER, runner_endpoint="ollama"
    )
    own = _provider("own", minutes=2)
    uc = await _resolver([instance, own, runner])

    with as_actor(_ANNA):
        provider, model = await uc._resolve_provider(_INPUT, None, None)  # noqa: SLF001

    assert provider.id == runner.id
    assert model == "runner-model"


async def test__default_order__runner_not_ready_is_skipped() -> None:
    instance = _provider("inst", minutes=0, owner_kind=AIProviderOwnerKind.instance)
    runner = _provider(
        "runner", minutes=1, type=AIProviderType.runner, api_key="", runner_id=_RUNNER, runner_endpoint="ollama"
    )
    uc = await _resolver([instance, runner], runner_online=False)

    with as_actor(_ANNA):
        provider, _ = await uc._resolve_provider(_INPUT, None, None)  # noqa: SLF001

    assert provider.id == instance.id


async def test__default_provider_setting_still_wins() -> None:
    first = _provider("first", minutes=0)
    chosen = _provider("chosen", minutes=5)
    uc = await _resolver([first, chosen], settings={"default_ai_provider_id": str(chosen.id), "default_ai_model": "m"})

    with as_actor(_ANNA):
        provider, model = await uc._resolve_provider(_INPUT, None, None)  # noqa: SLF001

    assert (provider.id, model) == (chosen.id, "m")


async def test__no_provider_at_all__clear_error() -> None:
    uc = await _resolver([])

    with as_actor(_ANNA), pytest.raises(ValueError, match="provider"):
        await uc._resolve_provider(_INPUT, None, None)  # noqa: SLF001


@pytest.mark.parametrize(
    ("code", "expected"),
    [(RelayErrorCode.relay_unavailable, "relay_unavailable"), (RelayErrorCode.relay_busy, "relay_busy")],
)
def test__run_error__relay_failure_is_described_with_a_code(code: RelayErrorCode, expected: str) -> None:
    outer = RuntimeError("sdk")
    outer.__cause__ = AiRelayError(code, runner_name="MacBook Анны")

    assert run_error_code(outer) == expected
    assert run_error_code(ValueError("x")) is None
    if code is RelayErrorCode.relay_unavailable:
        assert "MacBook Анны" in describe_run_error(outer)


def _run(**changes: Any) -> AgentRunRecord:
    run = AgentRunRecord(
        id=uuid4(),
        session_id=uuid4(),
        project_folder=Path("/p"),
        status=AgentRunStatus.failed,
        created_at=NOW,
        started_at=NOW,
        finished_at=NOW,
        trigger_seq=0,
        error="Раннер не ответил",
        error_code="relay_unavailable",
    )
    return dataclasses.replace(run, **changes)


def test__run_record__error_code_round_trips_through_json_and_pg_diagnostics() -> None:
    run = _run(diagnostics=[{"kind": "stop", "reason": "x"}])

    assert deserialize_agent_run(serialize_agent_run(run), Path("/p")) == run
    stored = _with_error_code(run.diagnostics, run.error_code)
    assert _error_code_of(stored) == "relay_unavailable"
    assert _with_error_code(stored, None) == run.diagnostics
    assert deserialize_agent_run({**serialize_agent_run(run), "error_code": None}, Path("/p")).error_code is None


def test__terminal_event__carries_the_code() -> None:
    event = GetChatRunStreamUC._terminal_event(_run())  # noqa: SLF001

    assert event.data["code"] == "relay_unavailable"
    assert "code" not in GetChatRunStreamUC._terminal_event(_run(error_code=None)).data  # noqa: SLF001
    assert UUID(str(event.data["run_id"]))
