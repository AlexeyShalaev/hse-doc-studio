"""Выборка, которой помешала другая выборка в ту же ссылку, повторяется, а не заканчивается общей ошибкой."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.api.config import GitConfig
from hse_doc_studio.core.git_sync.entities import RemoteTarget
from hse_doc_studio.core.git_sync.error_messages import git_error
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.url import parse_remote_url
from hse_doc_studio.infra.git_sync import git_transport
from hse_doc_studio.infra.git_sync.git_transport import GitTransport

pytestmark = pytest.mark.unit

_LOCKED = "error: cannot lock ref 'refs/remotes/origin/main': is at aaaa but expected bbbb"


class _Runner:
    def __init__(self, failures: list[GitSyncError]) -> None:
        self.failures = failures
        self.calls = 0

    async def run(self, *_args: Any, **_kwargs: Any) -> Any:
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        return None


def _target() -> RemoteTarget:
    return RemoteTarget(parse_remote_url("https://git.example.com/a/b.git"), None, insecure_http=False)


@pytest.fixture(autouse=True)
def _no_pause(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(git_transport, "_REF_LOCK_PAUSE_S", 0)


async def test__fetch__ref_is_locked_once__retried_and_succeeds(tmp_path: Path) -> None:
    runner = _Runner([git_error(GitErrorCode.git_error, tail=_LOCKED)])

    await GitTransport(runner, GitConfig()).fetch(tmp_path, _target(), branch="main")  # type: ignore[arg-type]

    assert runner.calls == 2


async def test__fetch__ref_stays_locked__fails_after_the_attempts_are_used(tmp_path: Path) -> None:
    runner = _Runner([git_error(GitErrorCode.git_error, tail=_LOCKED) for _ in range(5)])

    with pytest.raises(GitSyncError):
        await GitTransport(runner, GitConfig()).fetch(tmp_path, _target(), branch="main")  # type: ignore[arg-type]

    assert runner.calls == git_transport._REF_LOCK_ATTEMPTS


async def test__fetch__other_failure__is_not_retried(tmp_path: Path) -> None:
    runner = _Runner([git_error(GitErrorCode.git_error, tail="fatal: something else")])

    with pytest.raises(GitSyncError):
        await GitTransport(runner, GitConfig()).fetch(tmp_path, _target(), branch="main")  # type: ignore[arg-type]

    assert runner.calls == 1
