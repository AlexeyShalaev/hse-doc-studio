"""`stale_version_tags`: какие теги образа Студии снимаются после удачного обновления."""

from __future__ import annotations

import pytest
from hse_doc_studio.core.docker_disk.prune import stale_version_tags

TAGS = ["0.20.0", "0.21.1", "v0.22.0", "0.23.0", "0.24.0", "latest", "rollback-prev", "sha-abc", "0.25.0-rc.1"]


def test__update__keeps_current_and_previous() -> None:
    assert stale_version_tags(TAGS, current="0.24.0", previous="0.23.0") == ["0.20.0", "0.21.1", "v0.22.0"]


def test__downgrade__keeps_both_and_newer_tags() -> None:
    # Понижение 0.24.0 до 0.22.0: остаются обе версии и всё новее.
    assert stale_version_tags(TAGS, current="0.22.0", previous="0.24.0") == ["0.20.0", "0.21.1"]


@pytest.mark.parametrize("previous", [None, "", "latest", "sha256:abc"])
def test__unknown_previous__removes_nothing(previous: str | None) -> None:
    assert stale_version_tags(TAGS, current="0.24.0", previous=previous) == []


def test__unknown_current__removes_nothing() -> None:
    assert stale_version_tags(TAGS, current="latest", previous="0.23.0") == []


def test__never_touches_non_version_tags() -> None:
    removed = stale_version_tags(TAGS, current="9.0.0", previous="9.0.0")
    assert "latest" not in removed
    assert "rollback-prev" not in removed
    assert "sha-abc" not in removed
