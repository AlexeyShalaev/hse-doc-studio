from __future__ import annotations

import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from hse_doc_studio.core.access.context import set_current_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import VcsCommitKind, VcsRestoreMode, VcsTagKind
from hse_doc_studio.core.vcs.constants import DEFAULT_VCS_EXCLUDE
from hse_doc_studio.core.vcs.entities import VcsAuthor
from hse_doc_studio.infra.vcs.commit_author import ActorCommitAuthorProvider
from hse_doc_studio.infra.vcs.git_vcs_service import GitVcsService
from hse_doc_studio.infra.vcs.template_base_store import GitTemplateBaseStore

from tests.factories import make_project

pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(shutil.which("git") is None, reason="git binary not available"),
]

_BOT = VcsAuthor("Test Bot", "bot@test.local")
_ALICE = Actor.user("u1", name="Alice Ivanova", email="alice@example.org")


@pytest.fixture(autouse=True)
def _no_actor() -> Iterator[None]:
    set_current_actor(None)
    yield
    set_current_actor(None)


def _service() -> GitVcsService:
    return GitVcsService(
        author_name=_BOT.name,
        author_email=_BOT.email,
        author_provider=ActorCommitAuthorProvider(_BOT),
    )


def _setup(tmp_path: Path) -> tuple[GitVcsService, Project]:
    project = make_project(folder=tmp_path)
    (tmp_path / "a.tex").write_text("v1\n", encoding="utf-8")
    svc = _service()
    svc.init(project, list(DEFAULT_VCS_EXCLUDE))
    return svc, project


def _snapshot(svc: GitVcsService, project: Project, tmp_path: Path, text: str) -> None:
    (tmp_path / "a.tex").write_text(text, encoding="utf-8")
    assert svc.commit(project, message="snap", kind=VcsCommitKind.manual) is not None


def _git(project: Project, *args: str) -> str:
    out = subprocess.run(  # noqa: S603
        ["git", "--git-dir", str(project.folder / ".hse-studio" / "git"), *args],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


def _head_identity(project: Project) -> str:
    return _git(project, "log", "-1", "--format=%an,%ae,%cn,%ce")


def test__commit__no_actor__author_is_bot(tmp_path: Path) -> None:
    svc, project = _setup(tmp_path)

    _snapshot(svc, project, tmp_path, "v2\n")

    assert _head_identity(project) == "Test Bot,bot@test.local,Test Bot,bot@test.local"


def test__commit__local_actor__author_is_bot(tmp_path: Path) -> None:
    svc, project = _setup(tmp_path)
    set_current_actor(Actor.local())

    _snapshot(svc, project, tmp_path, "v2\n")

    assert _head_identity(project) == "Test Bot,bot@test.local,Test Bot,bot@test.local"


def test__commit__user_actor__author_is_actor_and_committer_follows(tmp_path: Path) -> None:
    svc, project = _setup(tmp_path)
    set_current_actor(_ALICE)

    _snapshot(svc, project, tmp_path, "v2\n")

    assert _head_identity(project) == "Alice Ivanova,alice@example.org,Alice Ivanova,alice@example.org"


def test__commit__actor_changes_between_calls__author_follows_current_actor(tmp_path: Path) -> None:
    svc, project = _setup(tmp_path)
    set_current_actor(_ALICE)
    _snapshot(svc, project, tmp_path, "v2\n")

    set_current_actor(Actor.user("u2", name="Bob", email="bob@example.org"))
    _snapshot(svc, project, tmp_path, "v3\n")

    assert _head_identity(project) == "Bob,bob@example.org,Bob,bob@example.org"


@pytest.mark.parametrize(
    ("name", "email"),
    [
        ("Eve <x>", "eve@example.org"),
        ("Eve\nEvil", "eve@example.org"),
        (".", "eve@example.org"),
        (" ,;:\"' ", "eve@example.org"),
        ("", "eve@example.org"),
        (None, "eve@example.org"),
        ("Eve", "not-an-email"),
        ("Eve", "eve@exa mple.org"),
        ("Eve", "e<v>e@example.org"),
        ("Eve", None),
        ("E" * 129, "eve@example.org"),
    ],
)
def test__commit__invalid_actor_name__falls_back_to_bot(tmp_path: Path, name: str | None, email: str | None) -> None:
    svc, project = _setup(tmp_path)
    set_current_actor(Actor.user("u3", name=name, email=email))

    _snapshot(svc, project, tmp_path, "v2\n")

    assert _head_identity(project) == "Test Bot,bot@test.local,Test Bot,bot@test.local"


def test__guest_actor_without_email__falls_back_to_bot(tmp_path: Path) -> None:
    svc, project = _setup(tmp_path)
    set_current_actor(Actor.guest("link1", name="Guest"))

    _snapshot(svc, project, tmp_path, "v2\n")

    assert _head_identity(project) == "Test Bot,bot@test.local,Test Bot,bot@test.local"


def test__annotated_tag_and_template_base_commit_tree__use_actor_identity(tmp_path: Path) -> None:
    svc, project = _setup(tmp_path)
    set_current_actor(_ALICE)

    svc.create_tag(project, name="v1", message="release", kind=VcsTagKind.release)
    tagger = _git(project, "for-each-ref", "refs/tags/v1", "--format=%(taggername),%(taggeremail)")
    assert tagger == "Alice Ivanova,<alice@example.org>"

    store = GitTemplateBaseStore(svc)
    commit = store.record_from_head(project, "1", lambda path: path == "a.tex", message="base")
    assert commit is not None
    assert _git(project, "log", "-1", "--format=%an,%ae,%cn,%ce", commit) == (
        "Alice Ivanova,alice@example.org,Alice Ivanova,alice@example.org"
    )


def test__reset_checkout__still_use_bot_identity_in_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    svc, project = _setup(tmp_path)
    first = svc.log(project)[0].id
    _snapshot(svc, project, tmp_path, "v2\n")
    set_current_actor(_ALICE)

    commands: list[list[str]] = []
    real_run = subprocess.run

    def spy(cmd: list[str], *args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(cmd)
        return real_run(cmd, *args, **kwargs)  # type: ignore[call-overload,no-any-return]

    monkeypatch.setattr("hse_doc_studio.infra.vcs.git_vcs_service.subprocess.run", spy)
    svc.restore(project, commit_id=first, mode=VcsRestoreMode.hard)
    _snapshot(svc, project, tmp_path, "v3\n")

    by_sub = {_subcommand(cmd): cmd for cmd in commands}
    assert "reset" in by_sub
    for sub in ("reset", "rev-parse"):
        assert by_sub[sub].count("user.name=Test Bot") == 1
        assert "user.name=Alice Ivanova" not in by_sub[sub]
    commit_cmds = [cmd for cmd in commands if _subcommand(cmd) == "commit"]
    assert commit_cmds
    for cmd in commit_cmds:
        # Служебная подпись в начале, подпись актора позже и потому побеждает.
        assert cmd.index("user.name=Test Bot") < cmd.index("user.name=Alice Ivanova")


def _subcommand(cmd: list[str]) -> str:
    rest = cmd[cmd.index("safe.directory=*") + 1 :]
    while rest[:1] == ["-c"]:
        rest = rest[2:]
    return rest[0] if rest else ""


def test__commit__without_provider__author_is_bot_even_with_actor(tmp_path: Path) -> None:
    project = make_project(folder=tmp_path)
    (tmp_path / "a.tex").write_text("v1\n", encoding="utf-8")
    svc = GitVcsService(author_name=_BOT.name, author_email=_BOT.email)
    svc.init(project, list(DEFAULT_VCS_EXCLUDE))
    set_current_actor(_ALICE)

    _snapshot(svc, project, tmp_path, "v2\n")

    assert _head_identity(project) == "Test Bot,bot@test.local,Test Bot,bot@test.local"
