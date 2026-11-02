from __future__ import annotations

from typing import Protocol

from hse_doc_studio.core.onboarding.entities import OnboardingState


class IOnboardingRepository(Protocol):
    """Состояние онбординга текущего человека.

    Локально это файл в каталоге данных (человек один), на сервере строка пользователя из
    `current_actor()`. `None` значит, что записи ещё нет.
    """

    async def get(self) -> OnboardingState | None: ...
    async def save(self, state: OnboardingState) -> None: ...


class IExistingUserProbe(Protocol):
    """Работал ли человек в Студии до появления онбординга: такому тур не открывается сам."""

    async def is_existing_user(self) -> bool: ...
