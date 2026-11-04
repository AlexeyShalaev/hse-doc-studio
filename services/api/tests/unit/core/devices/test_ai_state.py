"""Почему облако может или не может пользоваться моделью через Студию: код состояния на каждый случай."""

from __future__ import annotations

from uuid import uuid4

import pytest
from hse_doc_studio.core.devices.ai import ProviderRef, RunnerFacts, endpoint_state, overall_state
from hse_doc_studio.core.devices.entities import AiState, EndpointReport

PROVIDER = ProviderRef(uuid4(), "Моя Ollama")


def facts(status: str = "online", *, declared: tuple[str, ...] = ("ollama",), relay: bool = True) -> RunnerFacts:
    return RunnerFacts(status=status, declared=frozenset(declared), relay_feature=relay)


def report(*, reachable: bool | None = True, models: tuple[str, ...] = ("qwen3",)) -> EndpointReport:
    return EndpointReport(name="ollama", flavor="ollama", reachable=reachable, models=models)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("revoked", AiState.runner_revoked),
        ("disabled", AiState.disabled),
        ("paused", AiState.runner_paused),
        ("offline", AiState.runner_offline),
        ("stale", AiState.runner_offline),
    ],
)
def test__endpoint_state__runner_problem_wins_over_everything(status: str, expected: AiState) -> None:
    assert endpoint_state(runner=facts(status), report=report(), provider=PROVIDER) is expected


def test__endpoint_state__ready_needs_reachable_models_and_a_provider() -> None:
    assert endpoint_state(runner=facts(), report=report(), provider=PROVIDER) is AiState.ready


def test__endpoint_state__no_provider_is_the_silent_gap_this_slice_makes_visible() -> None:
    assert endpoint_state(runner=facts(), report=report(), provider=None) is AiState.no_provider


def test__endpoint_state__model_down_and_empty_catalog_have_own_reasons() -> None:
    assert endpoint_state(runner=facts(), report=report(reachable=False, models=()), provider=PROVIDER) is (
        AiState.endpoint_unreachable
    )
    assert endpoint_state(runner=facts(), report=report(models=()), provider=PROVIDER) is AiState.no_models


def test__endpoint_state__old_runner_without_relay_feature_is_not_opened() -> None:
    assert endpoint_state(runner=facts(relay=False), report=report(), provider=PROVIDER) is AiState.not_opened


def test__endpoint_state__no_report_yet_does_not_claim_the_model_is_down() -> None:
    assert endpoint_state(runner=facts(), report=None, provider=PROVIDER) is AiState.ready


def test__overall_state__offline_studio_beats_all() -> None:
    assert (
        overall_state(online=False, paired=True, runner=facts(), endpoints=(AiState.ready,)) is AiState.studio_offline
    )


def test__overall_state__unpaired_studio_has_no_runner() -> None:
    assert overall_state(online=True, paired=False, runner=None, endpoints=()) is AiState.runner_unpaired


def test__overall_state__paired_but_nothing_opened() -> None:
    assert overall_state(online=True, paired=True, runner=facts(declared=()), endpoints=()) is AiState.not_opened


def test__overall_state__best_endpoint_decides() -> None:
    states = (AiState.endpoint_unreachable, AiState.no_provider, AiState.ready)

    assert overall_state(online=True, paired=True, runner=facts(), endpoints=states) is AiState.ready
    assert overall_state(online=True, paired=True, runner=facts(), endpoints=states[:2]) is AiState.no_provider


def test__overall_state__paused_runner_is_reported_as_such() -> None:
    assert overall_state(online=True, paired=True, runner=facts("paused"), endpoints=()) is AiState.runner_paused
