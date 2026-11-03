from __future__ import annotations

from datetime import UTC, datetime

import pytest
from hse_doc_studio.core.onboarding.entities import (
    OnboardingInvalidError,
    OnboardingPatch,
    OnboardingState,
    OnboardingStatus,
    apply_patch,
    normalize_answers,
    restart,
)

_T0 = datetime(2026, 11, 3, 10, 0, tzinfo=UTC)
_T1 = datetime(2026, 11, 3, 10, 5, tzinfo=UTC)


def test__apply_patch__start__sets_started_at_and_step() -> None:
    state = apply_patch(
        OnboardingState.fresh(OnboardingStatus.pending),
        OnboardingPatch(status=OnboardingStatus.in_progress, step="questions", scenario_version=1),
        _T0,
    )

    assert (state.status, state.step, state.scenario_version) == (OnboardingStatus.in_progress, "questions", 1)
    assert state.started_at == _T0
    assert state.finished_at is None


def test__apply_patch__progress_again__keeps_started_at() -> None:
    started = apply_patch(
        OnboardingState.fresh(OnboardingStatus.pending), OnboardingPatch(status=OnboardingStatus.in_progress), _T0
    )

    moved = apply_patch(started, OnboardingPatch(status=OnboardingStatus.in_progress, step="demo.build"), _T1)

    assert moved.started_at == _T0
    assert moved.updated_at == _T1


@pytest.mark.parametrize("status", [OnboardingStatus.completed, OnboardingStatus.skipped])
def test__apply_patch__finish__sets_finished_at(status: OnboardingStatus) -> None:
    started = apply_patch(
        OnboardingState.fresh(OnboardingStatus.pending), OnboardingPatch(status=OnboardingStatus.in_progress), _T0
    )

    done = apply_patch(started, OnboardingPatch(status=status, clear_step=True), _T1)

    assert done.status is status
    assert done.finished_at == _T1
    assert done.step is None


def test__apply_patch__suggested_from_client__rejected() -> None:
    with pytest.raises(OnboardingInvalidError) as exc:
        apply_patch(
            OnboardingState.fresh(OnboardingStatus.pending), OnboardingPatch(status=OnboardingStatus.suggested), _T0
        )
    assert exc.value.field == "status"


@pytest.mark.parametrize("step", ["", "Шаг", "a" * 65, "demo build"])
def test__apply_patch__bad_step__rejected(step: str) -> None:
    with pytest.raises(OnboardingInvalidError):
        apply_patch(OnboardingState.fresh(OnboardingStatus.pending), OnboardingPatch(step=step), _T0)


def test__normalize_answers__known_keys__trimmed() -> None:
    assert normalize_answers({"role": " student ", "work": "hse-cs-se/vkr"}) == {
        "role": "student",
        "work": "hse-cs-se/vkr",
    }


@pytest.mark.parametrize("answers", [{"age": "20"}, {"role": "Студент"}, {"role": ""}])
def test__normalize_answers__invalid__rejected(answers: dict[str, str]) -> None:
    with pytest.raises(OnboardingInvalidError):
        normalize_answers(answers)


def test__restart__keeps_answers_and_clears_progress() -> None:
    done = OnboardingState(
        status=OnboardingStatus.completed,
        scenario_version=1,
        step="finish",
        answers={"role": "student"},
        started_at=_T0,
        finished_at=_T0,
    )

    again = restart(done, _T1)

    assert again.status is OnboardingStatus.pending
    assert again.answers == {"role": "student"}
    assert (again.step, again.started_at, again.finished_at) == (None, None, None)
