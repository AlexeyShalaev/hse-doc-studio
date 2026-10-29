from __future__ import annotations

import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from hse_doc_studio.core.access.context import set_current_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import VcsCommitKind
from hse_doc_studio.core.vcs.constants import DEFAULT_VCS_EXCLUDE
from hse_doc_studio.core.vcs.entities import VcsAuthor
from hse_doc_studio.infra.identity.user_author_profile import UserAuthorProfile
from hse_doc_studio.infra.vcs.commit_author import ActorCommitAuthorProvider
from hse_doc_studio.infra.vcs.git_vcs_service import GitVcsService

from tests.factories import make_project

_BOT = VcsAuthor("Test Bot", "bot@test.local")


@pytest.fixture(autouse=True)
def _no_actor() -> Iterator[None]:
    set_current_actor(None)
    yield
    set_current_actor(None)


def test_profile_is_filled_automatically_for_a_signed_in_user() -> None:
    set_current_actor(Actor.user("u1", "Ann", "u1@noreply.studio.test"))

    profile = UserAuthorProfile().get()

    assert profile is not None
    assert (profile.name, profile.email) == ("Ann", "u1@noreply.studio.test")


def test_two_users_have_their_own_profiles() -> None:
    set_current_actor(Actor.user("u1", "Ann", "u1@noreply.studio.test"))
    first = UserAuthorProfile().get()
    set_current_actor(Actor.user("u2", "Bob", "bob@home.example"))
    second = UserAuthorProfile().get()

    assert first is not None
    assert second is not None
    assert first != second


def test_no_actor_local_actor_or_unusable_identity_means_no_profile() -> None:
    assert UserAuthorProfile().get() is None
    set_current_actor(Actor.local())
    assert UserAuthorProfile().get() is None
    set_current_actor(Actor.user("u1", "<>", "u1@noreply.studio.test"))
    assert UserAuthorProfile().get() is None


@pytest.mark.skipif(shutil.which("git") is None, reason="git binary not available")
def test_two_users_commit_into_one_project_with_different_authors(tmp_path: Path) -> None:
    project: Project = make_project(folder=tmp_path)
    (tmp_path / "a.tex").write_text("v1\n", encoding="utf-8")
    svc = GitVcsService(
        author_name=_BOT.name,
        author_email=_BOT.email,
        author_provider=ActorCommitAuthorProvider(_BOT),
    )
    svc.init(project, list(DEFAULT_VCS_EXCLUDE))

    for text, actor in (
        ("v2\n", Actor.user("u1", "Ann Ivanova", "u1@noreply.studio.test")),
        ("v3\n", Actor.user("u2", "Bob Petrov", "bob@home.example")),
    ):
        set_current_actor(actor)
        (tmp_path / "a.tex").write_text(text, encoding="utf-8")
        assert svc.commit(project, message="snap", kind=VcsCommitKind.manual) is not None

    log = subprocess.run(  # noqa: S603
        ["git", "--git-dir", str(tmp_path / ".hse-studio" / "git"), "log", "--format=%an <%ae>"],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    assert log[:2] == ["Bob Petrov <bob@home.example>", "Ann Ivanova <u1@noreply.studio.test>"]
