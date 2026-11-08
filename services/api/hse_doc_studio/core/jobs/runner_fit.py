"""Может ли задачу взять хоть один раннер: «все подходящие заняты» и «подходящих нет совсем» это разное.

Раннеры, доступные задаче, делятся на два пула: общие раннеры установки и личные раннеры владельца проекта
(если маршрут их допускает). В каждом пуле смотрим только неотозванные раннеры с нужными тегами и берём лучшее
состояние: в сети (пусть и занят), на паузе, не в сети, нет вовсе. Задача ждёт, пока хоть один пул в сети;
иначе причина говорит, что делать: снять паузу, запустить раннер или подключить раннер с нужным тегом.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.jobs.admin import RunnerStatus, runner_status
from hse_doc_studio.core.jobs.routing import RunnerScope
from hse_doc_studio.core.jobs.runners import Runner


class PoolState(StrEnum):
    """Лучшее состояние среди подходящих раннеров пула (порядок важности сверху вниз)."""

    online = "online"
    paused = "paused"
    offline = "offline"
    absent = "absent"


class RunnerGapReason(StrEnum):
    """Почему задачу сейчас не может взять ни один раннер; порядок отражает, что человеку проще исправить."""

    personal_paused = "personal_paused"
    shared_paused = "shared_paused"
    personal_offline = "personal_offline"
    shared_offline = "shared_offline"
    no_runner = "no_runner"


_ORDER = (PoolState.online, PoolState.paused, PoolState.offline, PoolState.absent)


def pool_state(runners: Iterable[Runner], tags: frozenset[str], now: datetime) -> PoolState:
    """Состояние пула для тегов: `stale` (молчит до пяти минут) и мягкий уход считаются «не в сети»."""
    best = PoolState.absent
    for runner in runners:
        if runner.revoked_at is not None or not tags <= runner.tags:
            continue
        match runner_status(runner, now):
            case RunnerStatus.online:
                return PoolState.online
            case RunnerStatus.paused:
                state = PoolState.paused
            case RunnerStatus.revoked | RunnerStatus.disabled:
                continue
            case _:
                state = PoolState.offline
        if _ORDER.index(state) < _ORDER.index(best):
            best = state
    return best


@dataclass(frozen=True)
class RunnerFit:
    """Состояние общих раннеров и личных раннеров владельца (`None`: личные этой задаче недоступны)."""

    tags: frozenset[str]
    shared: PoolState
    personal: PoolState | None = None

    @classmethod
    def of(
        cls, tags: frozenset[str], runners: Iterable[Runner], now: datetime, *, personal_owner: str | None
    ) -> RunnerFit:
        """`runners` все раннеры установки; личные берутся только у `personal_owner`."""
        listed = list(runners)
        shared = pool_state((r for r in listed if r.scope is RunnerScope.shared), tags, now)
        personal = (
            pool_state(
                (r for r in listed if r.scope is RunnerScope.personal and r.owner_id == personal_owner), tags, now
            )
            if personal_owner is not None
            else None
        )
        return cls(tags=tags, shared=shared, personal=personal)

    @property
    def available(self) -> bool:
        """Хоть один подходящий раннер в сети: задача ждёт своей очереди, даже если все заняты."""
        return self.shared is PoolState.online or self.personal is PoolState.online

    @property
    def reason(self) -> RunnerGapReason | None:
        if self.available:
            return None
        if self.personal is PoolState.paused:
            return RunnerGapReason.personal_paused
        if self.shared is PoolState.paused:
            return RunnerGapReason.shared_paused
        if self.personal is PoolState.offline:
            return RunnerGapReason.personal_offline
        if self.shared is PoolState.offline:
            return RunnerGapReason.shared_offline
        return RunnerGapReason.no_runner

    def describe(self) -> str:
        """Одна фраза для отказа, журнала сборки и MCP: каких тегов нет и что с каждым пулом."""
        tags = ", ".join(sorted(self.tags)) or "-"
        phrases = [_shared_phrase(self.shared, tags)]
        if self.personal is not None:
            phrases.append(_personal_phrase(self.personal, tags))
        return localized_error(
            f"Нет раннера в сети, который умеет {tags}: {', '.join(ru for ru, _ in phrases)}.",
            f"No online runner can do {tags}: {', '.join(en for _, en in phrases)}.",
        )


def _shared_phrase(state: PoolState, tags: str) -> tuple[str, str]:
    match state:
        case PoolState.online:
            return "облачный раннер в сети", "a shared runner is online"
        case PoolState.paused:
            return "облачный раннер с этим тегом на паузе", "the shared runner with this tag is paused"
        case PoolState.offline:
            return "облачный раннер с этим тегом не в сети", "the shared runner with this tag is offline"
    return f"у облачных раннеров нет тега {tags}", f"no shared runner has the {tags} tag"


def _personal_phrase(state: PoolState, tags: str) -> tuple[str, str]:
    match state:
        case PoolState.online:
            return "личный раннер в сети", "the personal runner is online"
        case PoolState.paused:
            return (
                "личный раннер владельца на паузе (снимите паузу, и сборка пойдёт)",
                "the owner's personal runner is paused (resume it and the build will run)",
            )
        case PoolState.offline:
            return (
                "личный раннер владельца не в сети (запустите Студию на компьютере)",
                "the owner's personal runner is offline (start the desktop Studio)",
            )
    return f"у личного раннера владельца нет тега {tags}", f"the owner has no personal runner with the {tags} tag"
