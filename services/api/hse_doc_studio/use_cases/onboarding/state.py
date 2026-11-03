"""Чтение, обновление и сброс состояния онбординга; одинаково в локальном и серверном режиме."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import structlog

from hse_doc_studio.core.onboarding.entities import (
    OnboardingPatch,
    OnboardingState,
    OnboardingStatus,
    apply_patch,
    restart,
)
from hse_doc_studio.core.onboarding.protocols import IExistingUserProbe, IOnboardingRepository

logger = structlog.get_logger()

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


async def _current(repo: IOnboardingRepository, probe: IExistingUserProbe) -> OnboardingState:
    stored = await repo.get()
    if stored is not None:
        return stored
    existing = await probe.is_existing_user()
    return OnboardingState.fresh(OnboardingStatus.suggested if existing else OnboardingStatus.pending)


class GetOnboardingUC:
    """Состояние человека; без записи новичок получает `pending`, давний пользователь `suggested`."""

    def __init__(self, repo: IOnboardingRepository, probe: IExistingUserProbe) -> None:
        self._repo = repo
        self._probe = probe

    async def execute(self) -> OnboardingState:
        return await _current(self._repo, self._probe)


class UpdateOnboardingUC:
    def __init__(self, repo: IOnboardingRepository, probe: IExistingUserProbe, clock: Clock = _utc_now) -> None:
        self._repo = repo
        self._probe = probe
        self._clock = clock

    async def execute(self, patch: OnboardingPatch) -> OnboardingState:
        state = apply_patch(await _current(self._repo, self._probe), patch, self._clock())
        await self._repo.save(state)
        logger.info("onboarding updated", status=state.status.value, step=state.step)
        return state


class ResetOnboardingUC:
    """«Пройти заново» из профиля или меню справки."""

    def __init__(self, repo: IOnboardingRepository, probe: IExistingUserProbe, clock: Clock = _utc_now) -> None:
        self._repo = repo
        self._probe = probe
        self._clock = clock

    async def execute(self) -> OnboardingState:
        state = restart(await _current(self._repo, self._probe), self._clock())
        await self._repo.save(state)
        logger.info("onboarding reset")
        return state
