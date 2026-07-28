from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.infra.vcs.edit_throttle import VcsEditThrottle

pytestmark = pytest.mark.unit


def test__first_call_allows_commit(tmp_path: Path) -> None:
    throttle = VcsEditThrottle(min_interval_seconds=60.0)
    assert throttle.should_commit(tmp_path) is True


def test__second_call_within_window_is_throttled(tmp_path: Path) -> None:
    throttle = VcsEditThrottle(min_interval_seconds=60.0)
    assert throttle.should_commit(tmp_path) is True
    assert throttle.should_commit(tmp_path) is False


def test__different_folders_are_independent(tmp_path: Path) -> None:
    throttle = VcsEditThrottle(min_interval_seconds=60.0)
    other = tmp_path / "other"
    assert throttle.should_commit(tmp_path) is True
    assert throttle.should_commit(other) is True


def test__zero_interval_always_allows(tmp_path: Path) -> None:
    throttle = VcsEditThrottle(min_interval_seconds=0.0)
    assert throttle.should_commit(tmp_path) is True
    assert throttle.should_commit(tmp_path) is True
