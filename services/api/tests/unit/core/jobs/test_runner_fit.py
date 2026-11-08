"""Есть ли кому взять задачу: в сети (пусть занят), на паузе, не в сети или раннера с тегами нет."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from hse_doc_studio.core.i18n import set_interface_language
from hse_doc_studio.core.jobs.runner_fit import PoolState, RunnerFit, RunnerGapReason, pool_state
from hse_doc_studio.core.jobs.runners import Runner, RunnerOwnerKind

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
OFFICE = frozenset({"office"})
OWNER = uuid4().hex


def _runner(*tags: str, personal: bool = False, **changes: object) -> Runner:
    runner = Runner(
        id=uuid4().hex,
        name="r",
        token_hash="h",
        tags=frozenset(tags),
        concurrency=1,
        resource_class="standard",
        version="1",
        created_at=NOW,
        last_seen_at=NOW - timedelta(seconds=5),
        owner_kind=RunnerOwnerKind.user if personal else RunnerOwnerKind.instance,
        owner_id=OWNER if personal else None,
    )
    return replace(runner, **changes)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("runners", "expected"),
    [
        ((), PoolState.absent),
        ((_runner("tex"),), PoolState.absent),
        ((_runner("office", revoked_at=NOW),), PoolState.absent),
        ((_runner("office", last_seen_at=NOW - timedelta(minutes=10)),), PoolState.offline),
        ((_runner("office", last_seen_at=NOW - timedelta(minutes=2)),), PoolState.offline),
        ((_runner("office", paused=True), _runner("office", last_seen_at=None)), PoolState.paused),
        ((_runner("office", paused=True), _runner("office")), PoolState.online),
    ],
    ids=["empty", "other_tags", "revoked", "offline", "stale", "paused_beats_offline", "online_beats_paused"],
)
def test__pool_state__best_state_of_suitable_runners(runners: tuple[Runner, ...], expected: PoolState) -> None:
    assert pool_state(runners, OFFICE, NOW) is expected


def test__fit__online_busy_runner__available() -> None:
    # Подходящий раннер в сети, даже занятый: задача ждёт очереди, это не отказ.
    fit = RunnerFit.of(OFFICE, [_runner("office", personal=True)], NOW, personal_owner=OWNER)

    assert fit.available
    assert fit.reason is None


@pytest.mark.parametrize(
    ("runners", "owner", "reason"),
    [
        ((_runner("tex"), _runner("office", personal=True, paused=True)), OWNER, RunnerGapReason.personal_paused),
        ((_runner("office", paused=True),), OWNER, RunnerGapReason.shared_paused),
        ((_runner("office", personal=True, last_seen_at=None),), OWNER, RunnerGapReason.personal_offline),
        ((_runner("office", last_seen_at=None),), None, RunnerGapReason.shared_offline),
        ((_runner("tex"),), OWNER, RunnerGapReason.no_runner),
        # Личный раннер не владельца (или маршрут без личных) не в счёт.
        ((_runner("office", personal=True, paused=True),), None, RunnerGapReason.no_runner),
    ],
    ids=["personal_paused", "shared_paused", "personal_offline", "shared_offline", "no_runner", "personal_not_allowed"],
)
def test__fit__nobody_online__names_the_reason(
    runners: tuple[Runner, ...], owner: str | None, reason: RunnerGapReason
) -> None:
    fit = RunnerFit.of(OFFICE, runners, NOW, personal_owner=owner)

    assert not fit.available
    assert fit.reason is reason


def test__describe__names_tags_and_both_pools() -> None:
    set_interface_language("ru")
    fit = RunnerFit(tags=OFFICE, shared=PoolState.absent, personal=PoolState.paused)

    text = fit.describe()

    assert "office" in text
    assert "у облачных раннеров нет тега office" in text
    assert "личный раннер владельца на паузе" in text


def test__describe__english() -> None:
    set_interface_language("en")
    try:
        text = RunnerFit(tags=OFFICE, shared=PoolState.offline).describe()
    finally:
        set_interface_language("ru")

    assert text == "No online runner can do office: the shared runner with this tag is offline."
