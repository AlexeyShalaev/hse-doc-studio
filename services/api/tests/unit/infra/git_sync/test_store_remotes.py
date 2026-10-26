from __future__ import annotations

import subprocess
from pathlib import Path
from uuid import UUID

import pytest
from hse_doc_studio.core.git_sync.entities import StoreRemoteConfig
from hse_doc_studio.infra.git_sync.store_remotes import GitStoreRemotes

from tests.unit.infra.git_sync.conftest import Repo

pytestmark = pytest.mark.unit

_CRED = UUID("11111111-2222-3333-4444-555555555555")


def _remotes(repo: Repo) -> GitStoreRemotes:
    return GitStoreRemotes(repo.svc, repo.git)


def _config() -> StoreRemoteConfig:
    return StoreRemoteConfig(
        url="https://github.com/hse-team/course-paper.git",
        credential_id=_CRED,
        local_branch="master",
        remote_branch="main",
    )


def test__read__not_connected__is_none(repo: Repo) -> None:
    assert _remotes(repo).read(repo.project) is None


def test__read__not_connected__does_not_start_git(repo: Repo, monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[object] = []
    original = subprocess.run

    def spy(*args: object, **kwargs: object) -> object:
        started.append(args[0] if args else kwargs.get("args"))
        return original(*args, **kwargs)  # type: ignore[call-overload]

    monkeypatch.setattr(subprocess, "run", spy)

    assert _remotes(repo).read(repo.project) is None
    assert started == []


def test__read__missing_store__is_none(tmp_path: Path) -> None:
    folder = tmp_path / "bare-project"
    folder.mkdir()
    repo = Repo(folder)

    assert _remotes(repo).read(repo.project) is None


def test__write_read__round_trips_url_credential_and_branches(repo: Repo) -> None:
    remotes = _remotes(repo)

    remotes.write(repo.project, _config())

    assert remotes.read(repo.project) == _config()
    assert repo.git.text(repo.folder, ["config", "--get", "hse.credential"]).strip() == str(_CRED)


def test__clear__removes_connection_and_tracking_refs_but_keeps_local_branches(repo: Repo) -> None:
    remotes = _remotes(repo)
    remotes.write(repo.project, _config())
    head = repo.head()
    repo.git.run(repo.folder, ["update-ref", "refs/remotes/origin/main", head])
    repo.git.run(repo.folder, ["update-ref", "refs/remotes/origin/draft", head])

    remotes.clear(repo.project)

    assert remotes.read(repo.project) is None
    assert repo.git.text(repo.folder, ["for-each-ref", "refs/remotes/"]).strip() == ""
    assert repo.git.text(repo.folder, ["rev-parse", "refs/heads/master"]).strip() == head
    assert repo.git.run(repo.folder, ["config", "--get", "hse.credential"], check=False).returncode != 0


def test__drop_tracking_refs__leaves_connection_in_place(repo: Repo) -> None:
    remotes = _remotes(repo)
    remotes.write(repo.project, _config())
    repo.git.run(repo.folder, ["update-ref", "refs/remotes/origin/main", repo.head()])

    remotes.drop_tracking_refs(repo.project)

    assert remotes.read(repo.project) == _config()
    assert repo.git.text(repo.folder, ["for-each-ref", "refs/remotes/"]).strip() == ""


def test__git_dir__is_the_isolated_store(repo: Repo) -> None:
    assert _remotes(repo).git_dir(repo.project) == repo.folder / ".hse-studio" / "git"
