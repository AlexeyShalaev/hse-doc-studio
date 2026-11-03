"""Реестр присутствия: запись в БД только при изменении состояния или по истечении интервала записи."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from hse_doc_studio.core.devices.entities import DeviceActivity, DeviceOs, DeviceReport
from hse_doc_studio.infra.devices.registry import PresenceRegistry

T0 = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
REPORT = DeviceReport(
    device_id="a" * 32, name="MacBook", version="0.6.0", os=DeviceOs.macos, activity=DeviceActivity.idle
)


def test__observe__first_signal_is_persisted() -> None:
    assert PresenceRegistry().observe("u1", REPORT, T0, 120) is True


def test__observe__same_state_inside_interval_is_kept_in_memory_only() -> None:
    registry = PresenceRegistry()
    registry.observe("u1", REPORT, T0, 120)

    assert registry.observe("u1", REPORT, T0 + timedelta(seconds=60), 120) is False
    assert registry.last_seen("u1", REPORT.device_id) == T0 + timedelta(seconds=60)


def test__observe__same_state_after_interval_is_persisted_again() -> None:
    registry = PresenceRegistry()
    registry.observe("u1", REPORT, T0, 120)

    assert registry.observe("u1", REPORT, T0 + timedelta(seconds=120), 120) is True


def test__observe__changed_state_is_persisted_at_once() -> None:
    registry = PresenceRegistry()
    registry.observe("u1", REPORT, T0, 120)

    busy = replace(REPORT, activity=DeviceActivity.building)

    assert registry.observe("u1", busy, T0 + timedelta(seconds=10), 120) is True


def test__observe__persist_clock_does_not_slide_with_memory_only_signals() -> None:
    registry = PresenceRegistry()
    registry.observe("u1", REPORT, T0, 120)
    registry.observe("u1", REPORT, T0 + timedelta(seconds=60), 120)

    assert registry.observe("u1", REPORT, T0 + timedelta(seconds=130), 120) is True


def test__observe__devices_of_different_people_do_not_share_state() -> None:
    registry = PresenceRegistry()
    registry.observe("u1", REPORT, T0, 120)

    assert registry.observe("u2", REPORT, T0 + timedelta(seconds=5), 120) is True


def test__forget_and_prune__drop_entries() -> None:
    registry = PresenceRegistry()
    registry.observe("u1", REPORT, T0, 120)
    registry.observe("u2", REPORT, T0 + timedelta(hours=2), 120)

    registry.prune(T0 + timedelta(hours=1))
    registry.forget("u2", REPORT.device_id)

    assert registry.last_seen("u1", REPORT.device_id) is None
    assert registry.last_seen("u2", REPORT.device_id) is None
