from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest
from hse_doc_studio.core.git_sync.entities import StoreRemoteConfig
from hse_doc_studio.core.vcs.constants import DEFAULT_VCS_EXCLUDE
from hse_doc_studio.core.vcs.errors import VcsInvalidRefError, VcsNotInitializedError
from hse_doc_studio.infra.vcs.git_vcs_service import GitVcsService, store_git_dir

from tests.factories import make_project

pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(shutil.which("git") is None, reason="git binary not available"),
]


def _git(args: list[str], folder: Path) -> str:
    return subprocess.run(  # noqa: S603
        ["git", "--git-dir", str(store_git_dir(folder)), *args],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def test__git_dir__is_public_and_inside_the_project(tmp_path: Path) -> None:
    project = make_project(folder=tmp_path)
    assert GitVcsService().git_dir(project) == tmp_path / ".hse-studio" / "git"


def test__init_bare_store__creates_a_store_without_commits(tmp_path: Path) -> None:
    svc = GitVcsService()
    project = make_project(folder=tmp_path)

    svc.init_bare_store(tmp_path, "main")

    assert svc.is_initialized(project)
    assert _git(["symbolic-ref", "--short", "HEAD"], tmp_path).strip() == "main"
    assert _git(["rev-list", "--all", "--count"], tmp_path).strip() == "0"
    assert svc.log(project) == []
    assert not (tmp_path / ".git").exists()


def test__init_bare_store__is_idempotent_and_keeps_existing_history(tmp_path: Path) -> None:
    svc = GitVcsService()
    project = make_project(folder=tmp_path)
    (tmp_path / "a.tex").write_text("a\n", encoding="utf-8")
    svc.init(project, list(DEFAULT_VCS_EXCLUDE))
    head = _git(["rev-parse", "HEAD"], tmp_path)

    svc.init_bare_store(tmp_path, "other")

    assert _git(["rev-parse", "HEAD"], tmp_path) == head


@pytest.mark.parametrize("branch", ["-x", "a b", "a..b", ""])
def test__init_bare_store__invalid_branch__is_rejected(tmp_path: Path, branch: str) -> None:
    with pytest.raises(VcsInvalidRefError):
        GitVcsService().init_bare_store(tmp_path, branch)
    assert not store_git_dir(tmp_path).exists()


def test__remote_config__round_trip(tmp_path: Path) -> None:
    svc = GitVcsService()
    project = make_project(folder=tmp_path)
    svc.init(project, list(DEFAULT_VCS_EXCLUDE))
    config = StoreRemoteConfig(
        url="https://github.com/o/r.git", credential_id=uuid4(), local_branch="master", remote_branch="main"
    )

    assert svc.read_remote_config(project) is None
    svc.write_remote_config(project, config)

    assert svc.read_remote_config(project) == config
    assert _git(["config", "--get", "remote.origin.url"], tmp_path).strip() == config.url
    assert _git(["config", "--get", "hse.localbranch"], tmp_path).strip() == "master"


def test__remote_config__rewrite_replaces_and_unsets_missing_fields(tmp_path: Path) -> None:
    svc = GitVcsService()
    project = make_project(folder=tmp_path)
    svc.init(project, list(DEFAULT_VCS_EXCLUDE))
    svc.write_remote_config(
        project, StoreRemoteConfig(url="https://a/x.git", credential_id=uuid4(), local_branch="m", remote_branch="r")
    )

    svc.write_remote_config(project, StoreRemoteConfig(url="https://b/y.git"))

    assert svc.read_remote_config(project) == StoreRemoteConfig(url="https://b/y.git")


def test__remote_config__bad_credential_id_in_config__reads_as_none(tmp_path: Path) -> None:
    svc = GitVcsService()
    project = make_project(folder=tmp_path)
    svc.init(project, list(DEFAULT_VCS_EXCLUDE))
    svc.write_remote_config(project, StoreRemoteConfig(url="https://a/x.git"))
    _git(["config", "hse.credential", "oops"], tmp_path)

    remote = svc.read_remote_config(project)

    assert remote is not None
    assert remote.credential_id is None


def test__remote_config__clear_removes_remote_and_binding(tmp_path: Path) -> None:
    svc = GitVcsService()
    project = make_project(folder=tmp_path)
    svc.init(project, list(DEFAULT_VCS_EXCLUDE))
    svc.write_remote_config(project, StoreRemoteConfig(url="https://a/x.git", local_branch="m", remote_branch="r"))

    svc.clear_remote_config(project)
    svc.clear_remote_config(project)

    assert svc.read_remote_config(project) is None
    text = (store_git_dir(tmp_path) / "config").read_text(encoding="utf-8")
    assert "[hse" not in text
    assert "[remote" not in text


def test__remote_config__no_store__reads_none_and_refuses_to_write(tmp_path: Path) -> None:
    svc = GitVcsService()
    project = make_project(folder=tmp_path)
    assert svc.read_remote_config(project) is None
    with pytest.raises(VcsNotInitializedError):
        svc.write_remote_config(project, StoreRemoteConfig(url="https://a/x.git"))


def test__default_exclude__covers_the_store_with_and_without_a_trailing_slash() -> None:
    assert ".hse-studio/git/" in DEFAULT_VCS_EXCLUDE
    assert ".hse-studio/git" in DEFAULT_VCS_EXCLUDE
