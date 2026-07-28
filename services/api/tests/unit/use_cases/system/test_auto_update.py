from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from hse_doc_studio.core.update.entities import ReleaseEntry, UpdateCheckState, UpdateFeedProbe
from hse_doc_studio.use_cases.system.auto_update import (
    AUTO_UPDATE_SETTING,
    AutoUpdateOutcome,
    AutoUpdateUC,
)
from hse_doc_studio.use_cases.system.check_updates import CheckUpdatesUC

_CURRENT = "1.0.0"
_NEWER = "2.0.0"


class _Feed:
    def __init__(self, latest: str) -> None:
        self.releases = (ReleaseEntry(version=latest, date="2026-08-01", notes=("Новое",)),) if latest else ()
        self.calls = 0

    async def probe(self) -> UpdateFeedProbe:
        self.calls += 1
        return UpdateFeedProbe(releases=self.releases, checked=True)


class _Cache:
    def __init__(self) -> None:
        self.state: UpdateCheckState | None = None

    def get(self) -> UpdateCheckState | None:
        return self.state

    def save(self, state: UpdateCheckState) -> None:
        self.state = state


class _Settings:
    def __init__(self, stored: dict[str, Any] | None = None) -> None:
        self.stored = stored if stored is not None else {}

    def get(self) -> dict[str, Any]:
        return self.stored

    def save(self, settings: dict[str, Any]) -> None:
        self.stored = settings


class _Updater:
    def __init__(self, *, can_update: bool = True, busy: bool = False, starts: bool = True) -> None:
        self.can_update = can_update
        self.busy = busy
        self.starts = starts
        self.started: list[str] = []

    async def can_self_update(self) -> bool:
        return self.can_update

    def target_image(self, version: str) -> str:
        return f"image:{version}"

    def is_busy(self) -> bool:
        return self.busy

    async def start(self, target_version: str) -> bool:
        self.started.append(target_version)
        return self.starts


def _make(
    feed: _Feed | None = None,
    updater: _Updater | None = None,
    settings_repo: _Settings | None = None,
) -> tuple[AutoUpdateUC, _Feed, _Updater, _Cache]:
    feed = feed or _Feed(_NEWER)
    updater = updater or _Updater()
    cache = _Cache()
    uc = AutoUpdateUC(
        check_updates=CheckUpdatesUC(feed=feed, cache=cache, current_version=_CURRENT),
        settings_repo=settings_repo or _Settings(),
        updater=updater,
        current_version=_CURRENT,
    )
    return uc, feed, updater, cache


async def test__run_once__newer_version_available__installs_it() -> None:
    uc, _feed, updater, _cache = _make()

    result = await uc.run_once()

    assert result.outcome is AutoUpdateOutcome.started
    assert result.target == _NEWER
    assert updater.started == [_NEWER]


async def test__run_once__setting_absent__treats_auto_update_as_on() -> None:
    # Дефолт включён, а config.json у свежей установки пуст — «нет ключа» обязано
    # значить то же самое, что явное true.
    uc, _feed, updater, _cache = _make(settings_repo=_Settings({}))

    result = await uc.run_once()

    assert result.outcome is AutoUpdateOutcome.started
    assert updater.started == [_NEWER]


async def test__run_once__disabled_by_user__does_nothing_and_skips_the_network() -> None:
    uc, feed, updater, _cache = _make(settings_repo=_Settings({AUTO_UPDATE_SETTING: False}))

    result = await uc.run_once()

    assert result.outcome is AutoUpdateOutcome.disabled
    assert updater.started == []
    assert feed.calls == 0, "выключенное автообновление не должно ходить в сеть"


async def test__run_once__deployment_cannot_self_update__skips_the_network() -> None:
    uc, feed, updater, _cache = _make(updater=_Updater(can_update=False))

    result = await uc.run_once()

    assert result.outcome is AutoUpdateOutcome.unsupported
    assert updater.started == []
    assert feed.calls == 0


async def test__run_once__work_in_flight__waits_for_the_next_tick() -> None:
    # Пересоздание контейнера убило бы идущую сборку или ход агента.
    uc, feed, updater, _cache = _make(updater=_Updater(busy=True))

    result = await uc.run_once()

    assert result.outcome is AutoUpdateOutcome.busy
    assert updater.started == []
    assert feed.calls == 0


async def test__run_once__already_on_the_newest__does_not_touch_the_container() -> None:
    uc, _feed, updater, _cache = _make(feed=_Feed(_CURRENT))

    result = await uc.run_once()

    assert result.outcome is AutoUpdateOutcome.up_to_date
    assert updater.started == []


async def test__run_once__feed_lists_only_older_versions__does_not_roll_back() -> None:
    # Автообновление ходит только вперёд: откат — осознанное решение человека.
    uc, _feed, updater, _cache = _make(feed=_Feed("0.9.0"))

    result = await uc.run_once()

    assert result.outcome is AutoUpdateOutcome.up_to_date
    assert updater.started == []


async def test__run_once__updater_fails_to_start__reports_failure() -> None:
    uc, _feed, updater, _cache = _make(updater=_Updater(starts=False))

    result = await uc.run_once()

    assert result.outcome is AutoUpdateOutcome.failed
    assert result.target == _NEWER


async def test__run_once__work_starts_while_the_feed_answers__aborts_before_touching_anything() -> None:
    # Проверка идёт по сети и не мгновенна; к моменту ответа пользователь мог
    # запустить сборку. Решение принимается по состоянию ПОСЛЕ ответа.
    updater = _Updater()

    class _SlowFeed(_Feed):
        async def probe(self) -> UpdateFeedProbe:
            updater.busy = True
            return await super().probe()

    uc, _feed, _updater, _cache = _make(feed=_SlowFeed(_NEWER), updater=updater)

    result = await uc.run_once()

    assert result.outcome is AutoUpdateOutcome.busy
    assert result.target == _NEWER
    assert updater.started == []


async def test__run_once__caches_the_versions_it_saw() -> None:
    # Один поход в сеть закрывает и автообновление, и список версий в UI.
    uc, _feed, _updater, cache = _make()

    await uc.run_once()

    assert cache.state is not None
    assert [release.version for release in cache.state.releases] == [_NEWER]


@pytest.mark.parametrize("checked_at", [datetime.now(UTC)])
def test__cache_state__latest__is_the_first_release(checked_at: datetime) -> None:
    state = UpdateCheckState(
        checked_at=checked_at,
        releases=(ReleaseEntry("2.0.0", "", ()), ReleaseEntry("1.0.0", "", ())),
    )

    assert state.latest == "2.0.0"
