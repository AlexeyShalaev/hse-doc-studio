from __future__ import annotations

from datetime import UTC, datetime

import pytest
from hse_doc_studio.core.server_update.decision import Action, DecisionInput, Reason, decide
from hse_doc_studio.core.server_update.entities import MaxBump, ReleaseInfo, UpdatePolicy, UpdateSettings
from hse_doc_studio.core.server_update.settings import (
    releases_from,
    releases_to,
    settings_from,
    settings_to,
    validate_settings,
)
from hse_doc_studio.core.server_update.versions import Bump, bump_kind, is_allowed, newest_release, pick_target
from hse_doc_studio.core.server_update.window import in_window, next_window_start

R = ReleaseInfo


def rel(*versions: str) -> tuple[ReleaseInfo, ...]:
    return tuple(R(v) for v in versions)


@pytest.mark.parametrize(
    ("current", "candidate", "kind"),
    [
        ("0.3.1", "0.3.2", Bump.patch),
        ("0.3.1", "0.4.0", Bump.minor),
        ("0.3.1", "1.0.0", Bump.major),
        ("0.3.1", "0.3.1", Bump.none),
        ("0.3.1", "0.2.9", Bump.none),
        ("1.2.3", "v1.2.4", Bump.patch),
    ],
)
def test__bump_kind(current: str, candidate: str, kind: Bump) -> None:
    assert bump_kind(current, candidate) is kind


def test__pick_target__stays_inside_the_allowed_step() -> None:
    releases = rel("0.3.5", "0.4.0", "1.0.0")
    assert pick_target("0.3.1", releases, MaxBump.minor) == R("0.4.0")
    assert pick_target("0.3.1", releases, MaxBump.patch) == R("0.3.5")
    assert pick_target("0.3.1", rel("1.0.0"), MaxBump.minor) is None
    assert newest_release("0.3.1", releases) == R("1.0.0")
    assert is_allowed("0.3.1", "0.3.2", MaxBump.patch)
    assert not is_allowed("0.3.1", "0.4.0", MaxBump.patch)


def at(day: int, hh: int, mm: int = 0) -> datetime:
    return datetime(2026, 11, day, hh, mm, tzinfo=UTC)  # 2 ноября 2026 понедельник


def test__window__plain_and_wrapping_midnight() -> None:
    mon = (0,)
    assert in_window(at(2, 2, 30), mon, 120, 180)
    assert not in_window(at(2, 5, 0), mon, 120, 180)
    assert not in_window(at(3, 2, 30), mon, 120, 180)
    # суббота 23:00, 180 минут: воскресенье 01:00 ещё внутри, а день считается по началу окна
    sat = (5,)
    assert in_window(at(8, 1, 0), sat, 23 * 60, 180)
    assert not in_window(at(7, 1, 0), sat, 23 * 60, 180)
    assert not in_window(at(9, 1, 0), sat, 23 * 60, 180)
    assert not in_window(at(2, 12), (), 0, 60)
    assert in_window(at(4, 13), (2,), 0, 24 * 60)


def test__next_window_start() -> None:
    assert next_window_start(at(2, 10), (0,), 120, 60) == at(9, 2)
    assert next_window_start(at(2, 2, 10), (0,), 120, 60) == at(2, 2, 10)
    assert next_window_start(at(2, 10), (), 120, 60) is None


def inp(**kw: object) -> DecisionInput:
    base: dict[str, object] = {
        "settings": UpdateSettings(policy=UpdatePolicy.auto, window_start_min=0, window_minutes=24 * 60),
        "current": "0.3.1",
        "releases": rel("0.3.2"),
        "now": at(2, 3),
        "executor_ready": True,
        "updater_online": True,
        "run_active": False,
    }
    base.update(kw)
    return DecisionInput(**base)  # type: ignore[arg-type]


def test__decide__auto_starts_in_window() -> None:
    d = decide(inp())
    assert (d.action, d.reason, d.target) == (Action.start, Reason.in_window, R("0.3.2"))


@pytest.mark.parametrize(
    ("override", "action", "reason"),
    [
        ({"settings": UpdateSettings(policy=UpdatePolicy.off)}, Action.none, Reason.policy_off),
        ({"releases": rel("0.3.1")}, Action.none, Reason.up_to_date),
        ({"settings": UpdateSettings(policy=UpdatePolicy.notify)}, Action.notify, Reason.notify_only),
        ({"releases": rel("1.0.0")}, Action.notify, Reason.bump_too_large),
        ({"executor_ready": False}, Action.notify, Reason.no_executor),
        ({"run_active": True}, Action.none, Reason.run_active),
        ({"failed_versions": frozenset({"0.3.2"})}, Action.none, Reason.previously_failed),
        ({"updater_online": False}, Action.none, Reason.updater_offline),
        (
            {"settings": UpdateSettings(policy=UpdatePolicy.auto, window_days=(3,), window_start_min=0)},
            Action.none,
            Reason.outside_window,
        ),
        ({"notified_version": "0.3.2", "executor_ready": False}, Action.none, Reason.already_notified),
    ],
)
def test__decide__table(override: dict[str, object], action: Action, reason: Reason) -> None:
    d = decide(inp(**override))
    assert (d.action, d.reason) == (action, reason)


def test__settings__roundtrip_and_garbage_falls_back_to_defaults() -> None:
    s = UpdateSettings(policy=UpdatePolicy.auto, max_bump=MaxBump.patch, window_days=(1, 3), backup_first=False)
    assert settings_from(settings_to(s)) == s
    junk = {"update.policy": "boom", "update.window_days": "x", "update.window_minutes": True}
    assert settings_from(junk) == UpdateSettings()
    assert releases_from({"update.releases": releases_to(rel("0.4.0", "0.3.2"))}) == rel("0.4.0", "0.3.2")


def test__validate_settings() -> None:
    validate_settings(UpdateSettings())
    for bad in (
        UpdateSettings(window_days=()),
        UpdateSettings(window_minutes=5),
        UpdateSettings(window_start_min=24 * 60),
        UpdateSettings(channel="beta"),
    ):
        with pytest.raises(Exception, match="."):
            validate_settings(bad)
