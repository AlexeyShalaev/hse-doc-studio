from __future__ import annotations

import os

import pytest
from hse_doc_studio.core.enums import VcsCommitKind
from hse_doc_studio.core.vcs.entities import VcsAuthor
from hse_doc_studio.core.vcs.errors import VcsCommandError, VcsInvalidRefError
from hse_doc_studio.infra.git_sync.merge_committer import GitMergeCommitter

from tests.unit.infra.git_sync.conftest import Repo

pytestmark = pytest.mark.unit

_posix_only = pytest.mark.skipif(os.name != "posix", reason="бит исполнения файла")


def _committer(repo: Repo) -> GitMergeCommitter:
    return GitMergeCommitter(repo.authors, repo.git)


def _fork(repo: Repo) -> tuple[str, str, str]:
    """base, ours (master), theirs (side)."""
    base = repo.head()
    repo.branch("side")
    theirs = repo.snap("side", side__file="theirs\n")
    repo.switch("master")
    ours = repo.snap("master", vkr__own="ours\n")
    return base, ours, theirs


def _merge(repo: Repo, changes: dict[str, bytes | None], trailers: dict[str, str] | None = None) -> str:
    _, ours, theirs = _fork(repo)
    return _committer(repo).commit_merge(
        repo.folder,
        ours=ours,
        theirs=theirs,
        changes=changes,
        message="Синхронизация: слияние",
        trailers=trailers or {"Hse-Sync": "abc123"},
    )


def test__commit_merge__has_two_parents_in_order(repo: Repo) -> None:
    _, ours, theirs = _fork(repo)
    sha = _committer(repo).commit_merge(repo.folder, ours=ours, theirs=theirs, changes={}, message="m", trailers={})
    parents = repo.git.text(repo.folder, ["rev-list", "--parents", "-n1", sha]).split()
    assert parents == [sha, ours, theirs]


def test__commit_merge__tree_is_ours_plus_changes(repo: Repo) -> None:
    sha = _merge(
        repo,
        {"side/file": b"theirs\n", "vkr/vkr.tex": b"merged\n", "docs/new.bin": b"\x00\x01", "vkr/own": None},
    )
    assert repo.show(sha, "side/file") == b"theirs\n"
    assert repo.show(sha, "vkr/vkr.tex") == b"merged\n"
    assert repo.show(sha, "docs/new.bin") == b"\x00\x01"
    assert repo.show(sha, "vkr/own") is None


def test__commit_merge__without_changes_keeps_the_tree_of_ours(repo: Repo) -> None:
    _, ours, theirs = _fork(repo)
    sha = _committer(repo).commit_merge(repo.folder, ours=ours, theirs=theirs, changes={}, message="m", trailers={})
    tree = repo.git.text(repo.folder, ["rev-parse", f"{sha}^{{tree}}"])
    assert tree == repo.git.text(repo.folder, ["rev-parse", f"{ours}^{{tree}}"])


def test__commit_merge__keeps_theirs_added_entry_that_the_planner_skipped_as_unsafe(repo: Repo) -> None:
    # Пропущенный как небезопасный чужой файл не должен исчезнуть из дерева слияния: отправка удалила бы его у всех.
    base = repo.head()
    repo.branch("side")
    repo.write("side/a\\b.tex", "theirs\n")
    theirs = repo.snap("side")
    repo.switch("master")
    ours = repo.snap("master", vkr__own="ours\n")
    assert base != ours

    sha = _committer(repo).commit_merge(repo.folder, ours=ours, theirs=theirs, changes={}, message="m", trailers={})

    assert repo.show(sha, "side/a\\b.tex") == b"theirs\n"


def test__commit_merge__does_not_resurrect_unsafe_entry_that_we_deleted(repo: Repo) -> None:
    repo.write("old/a\\b.tex", "x\n")
    repo.snap("base")
    repo.branch("side")
    repo.switch("master")
    repo.remove("old/a\\b.tex")
    ours = repo.snap("master")
    theirs = repo.git.text(repo.folder, ["rev-parse", "side"]).strip()

    sha = _committer(repo).commit_merge(repo.folder, ours=ours, theirs=theirs, changes={}, message="m", trailers={})

    assert repo.show(sha, "old/a\\b.tex") is None


def test__commit_merge__message_carries_kind_and_trailers(repo: Repo) -> None:
    sha = _merge(repo, {}, {"Hse-Sync": "abc123"})
    body = repo.git.text(repo.folder, ["log", "-1", "--format=%B", sha])
    assert body.startswith("Синхронизация: слияние\n\n")
    assert "Hse-Kind: sync" in body
    assert "Hse-Sync: abc123" in body
    assert (
        repo.git.text(repo.folder, ["log", "-1", "--format=%(trailers:key=Hse-Kind,valueonly)", sha]).strip() == "sync"
    )


def test__commit_merge__commit_is_read_as_sync_kind_by_the_history(repo: Repo) -> None:
    sha = _merge(repo, {})
    repo.git.run(repo.folder, ["update-ref", "refs/heads/master", sha])
    head = repo.svc.log(repo.project, limit=1)[0]
    assert head.id == sha
    assert head.kind is VcsCommitKind.sync
    assert len(head.parents) == 2


def test__commit_merge__uses_the_author_from_the_provider(repo: Repo) -> None:
    repo.authors.current = VcsAuthor("Анна Петрова", "anna@example.org")
    sha = _merge(repo, {})
    assert repo.git.text(repo.folder, ["log", "-1", "--format=%an <%ae>|%cn <%ce>", sha]).strip() == (
        "Анна Петрова <anna@example.org>|Анна Петрова <anna@example.org>"
    )


def test__commit_merge__does_not_move_the_branch_or_touch_the_work_tree(repo: Repo) -> None:
    _, ours, theirs = _fork(repo)
    (repo.folder / "dirty.txt").write_text("untracked\n", encoding="utf-8")
    before = repo.git.text(repo.folder, ["status", "--porcelain"])
    _committer(repo).commit_merge(
        repo.folder, ours=ours, theirs=theirs, changes={"side/file": b"x\n"}, message="m", trailers={}
    )
    assert repo.head() == ours
    assert repo.git.text(repo.folder, ["status", "--porcelain"]) == before
    assert not (repo.folder / "side").exists()


@_posix_only
def test__commit_merge__keeps_the_executable_bit_of_existing_files(repo: Repo) -> None:
    script = repo.folder / "run.sh"
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    script.chmod(0o755)
    repo.snap("script")
    base = repo.head()
    repo.branch("side")
    repo.snap("side", s="1\n")
    repo.switch("master")
    sha = _committer(repo).commit_merge(
        repo.folder, ours=base, theirs="side", changes={"run.sh": b"#!/bin/sh\necho\n"}, message="m", trailers={}
    )
    modes = {
        e.path: e.mode
        for e in __import__("hse_doc_studio.infra.git_sync.repo_reader", fromlist=["x"])
        .GitRepoReader(repo.git)
        .tree_entries(repo.folder, sha)
    }
    assert modes["run.sh"] == "100755"


def test__commit_merge__does_not_filter_content(repo: Repo) -> None:
    repo.write(".gitattributes", "*.txt text eol=crlf\n")
    data = b"line1\nline2\n"
    sha = _merge(repo, {"x.txt": data})
    assert repo.show(sha, "x.txt") == data


@pytest.mark.parametrize("path", ["", "/abs", "../up", "a/../b", ".git/config", "a/.GIT/x", "a//b", "a\\b", "a\nb"])
def test__commit_merge__unsafe_path__is_rejected(repo: Repo, path: str) -> None:
    _, ours, theirs = _fork(repo)
    with pytest.raises(ValueError, match="unsafe path"):
        _committer(repo).commit_merge(
            repo.folder, ours=ours, theirs=theirs, changes={path: b"x"}, message="m", trailers={}
        )


@pytest.mark.parametrize("trailers", [{"Hse-Kind": "edit"}, {"bad key": "v"}, {"Hse-Sync": "a\nb"}])
def test__commit_merge__bad_trailer__is_rejected(repo: Repo, trailers: dict[str, str]) -> None:
    _, ours, theirs = _fork(repo)
    with pytest.raises(ValueError):  # noqa: PT011
        _committer(repo).commit_merge(repo.folder, ours=ours, theirs=theirs, changes={}, message="m", trailers=trailers)


def test__commit_merge__unknown_parent__raises(repo: Repo) -> None:
    with pytest.raises(VcsCommandError):
        _committer(repo).commit_merge(
            repo.folder, ours=repo.head(), theirs="refs/remotes/origin/none", changes={}, message="m", trailers={}
        )


# ── сдвиг ветки ──────────────────────────────────────────────────────────────
def test__advance_branch__moves_the_ref_and_aligns_the_index(repo: Repo) -> None:
    _, ours, theirs = _fork(repo)
    committer = _committer(repo)
    sha = committer.commit_merge(
        repo.folder, ours=ours, theirs=theirs, changes={"side/file": b"theirs\n"}, message="m", trailers={}
    )
    repo.write("side/file", "theirs\n")

    assert committer.advance_branch(repo.folder, "master", expected=ours, new=sha) is True

    assert repo.head() == sha
    assert repo.git.text(repo.folder, ["status", "--porcelain"]).strip() == ""


def test__advance_branch__head_moved_meanwhile__returns_false_and_changes_nothing(repo: Repo) -> None:
    _, ours, theirs = _fork(repo)
    committer = _committer(repo)
    sha = committer.commit_merge(repo.folder, ours=ours, theirs=theirs, changes={}, message="m", trailers={})
    moved = repo.snap("edit during sync", late="1\n")

    assert committer.advance_branch(repo.folder, "master", expected=ours, new=sha) is False

    assert repo.head() == moved
    assert repo.git.text(repo.folder, ["status", "--porcelain"]).strip() == ""


def test__advance_branch__other_branch__leaves_the_index_alone(repo: Repo) -> None:
    _, ours, theirs = _fork(repo)
    (repo.folder / "dirty.txt").write_text("x\n", encoding="utf-8")
    repo.git.run(repo.folder, ["add", "dirty.txt"])
    committer = _committer(repo)
    assert committer.advance_branch(repo.folder, "side", expected=theirs, new=ours) is True
    assert repo.git.text(repo.folder, ["rev-parse", "side"]).strip() == ours
    assert "A  dirty.txt" in repo.git.text(repo.folder, ["status", "--porcelain"])


def test__advance_branch__invalid_branch_name__is_rejected(repo: Repo) -> None:
    with pytest.raises(VcsInvalidRefError):
        _committer(repo).advance_branch(repo.folder, "--x", expected=repo.head(), new=repo.head())


def test__fast_forward__moves_to_a_descendant(repo: Repo) -> None:
    base = repo.head()
    repo.branch("remote")
    tip = repo.snap("remote work", r__file="r\n")
    repo.switch("master")
    repo.write("r/file", "r\n")

    assert _committer(repo).fast_forward(repo.folder, "master", expected=base, new=tip) is True

    assert repo.head() == tip
    assert repo.git.text(repo.folder, ["status", "--porcelain"]).strip() == ""


def test__fast_forward__not_a_descendant__raises(repo: Repo) -> None:
    _, ours, theirs = _fork(repo)
    with pytest.raises(VcsCommandError):
        _committer(repo).fast_forward(repo.folder, "master", expected=ours, new=theirs)
    assert repo.head() == ours


def test__delete_ref__removes_a_bundle_staging_ref(repo: Repo) -> None:
    ref = "refs/hse/bundle/master"
    repo.git.run(repo.folder, ["update-ref", ref, repo.head()])

    _committer(repo).delete_ref(repo.folder, ref)

    assert repo.git.text(repo.folder, ["for-each-ref", ref]).strip() == ""


def test__delete_ref__missing_ref__is_not_an_error(repo: Repo) -> None:
    _committer(repo).delete_ref(repo.folder, "refs/hse/bundle/gone")


@pytest.mark.parametrize("ref", ["refs/heads/master", "refs/remotes/origin/main", "refs/hse/template/1", "HEAD"])
def test__delete_ref__anything_but_a_bundle_ref__is_refused(repo: Repo, ref: str) -> None:
    with pytest.raises(ValueError, match="staging"):
        _committer(repo).delete_ref(repo.folder, ref)
    assert repo.git.text(repo.folder, ["rev-parse", "master"]).strip() == repo.head()
