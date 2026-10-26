from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from hse_doc_studio.core.vcs.entities import VcsAuthor
from hse_doc_studio.core.vcs.errors import VcsCommandError, VcsInvalidRefError
from hse_doc_studio.infra.git_sync.repo_reader import GitRepoReader
from hse_doc_studio.infra.git_sync.store_git import StoreGit
from hse_doc_studio.infra.vcs.git_vcs_service import GitVcsService

from tests.unit.infra.git_sync.conftest import Repo

pytestmark = pytest.mark.unit

_posix_only = pytest.mark.skipif(os.name != "posix", reason="имена файлов со спецсимволами")


def _reader() -> GitRepoReader:
    return GitRepoReader()


def _diverge(repo: Repo) -> tuple[str, str, str]:
    """base -> (master: +2 коммита) и (side: +1 коммит); возвращает (base, master, side)."""
    base = repo.head()
    repo.branch("side")
    side = repo.snap("side", side__only="side\n")
    repo.switch("master")
    repo.snap("m1", vkr__vkr_tex="m1\n")
    master = repo.snap("m2", vkr__more="m2\n")
    return base, master, side


# ── ссылки ───────────────────────────────────────────────────────────────────
def test__rev_parse__known_ref__returns_full_sha(repo: Repo) -> None:
    assert _reader().rev_parse(repo.folder, "HEAD") == repo.head()
    assert _reader().rev_parse(repo.folder, "master") == repo.head()


def test__rev_parse__unknown_ref__returns_none(repo: Repo) -> None:
    assert _reader().rev_parse(repo.folder, "refs/remotes/origin/main") is None


def test__rev_parse__unborn_head__returns_none(tmp_path: Path) -> None:
    folder = tmp_path / "empty"
    folder.mkdir()
    GitVcsService().init_bare_store(folder, "main")
    assert _reader().rev_parse(folder, "HEAD") is None
    assert _reader().current_branch(folder) == "main"


def test__rev_parse__option_like_ref__is_rejected(repo: Repo) -> None:
    with pytest.raises(VcsInvalidRefError):
        _reader().rev_parse(repo.folder, "--output=/tmp/x")


def test__current_branch__follows_checkout(repo: Repo) -> None:
    assert _reader().current_branch(repo.folder) == "master"
    repo.branch("draft")
    assert _reader().current_branch(repo.folder) == "draft"


def test__current_branch__detached_head__returns_none(repo: Repo) -> None:
    repo.git.run(repo.folder, ["update-ref", "--no-deref", "HEAD", repo.head()])
    assert _reader().current_branch(repo.folder) is None


# ── предки ───────────────────────────────────────────────────────────────────
def test__merge_base__diverged__returns_the_fork_point(repo: Repo) -> None:
    base, master, side = _diverge(repo)
    assert _reader().merge_base(repo.folder, master, side) == base
    assert _reader().merge_bases(repo.folder, master, side) == [base]


def test__merge_base__unrelated_histories__returns_none(repo: Repo) -> None:
    root = repo.git.text(repo.folder, ["commit-tree", "-m", "orphan", "4b825dc642cb6eb9a060e54bf8d69288fbee4904"])
    assert _reader().merge_base(repo.folder, repo.head(), root.strip()) is None
    assert _reader().merge_bases(repo.folder, repo.head(), root.strip()) == []


def test__is_ancestor__linear_and_diverged(repo: Repo) -> None:
    base, master, side = _diverge(repo)
    reader = _reader()
    assert reader.is_ancestor(repo.folder, base, master) is True
    assert reader.is_ancestor(repo.folder, master, base) is False
    assert reader.is_ancestor(repo.folder, side, master) is False


def test__is_ancestor__unknown_commit__raises(repo: Repo) -> None:
    with pytest.raises(VcsCommandError):
        _reader().is_ancestor(repo.folder, "deadbeef" * 5, repo.head())


# ── ahead / behind ───────────────────────────────────────────────────────────
def test__ahead_behind__same_commit__is_zero(repo: Repo) -> None:
    assert _reader().ahead_behind(repo.folder, "HEAD", "HEAD") == (0, 0)


def test__ahead_behind__local_has_new_commits__is_ahead(repo: Repo) -> None:
    base = repo.head()
    repo.snap("a1", a="1\n")
    repo.snap("a2", a="2\n")
    assert _reader().ahead_behind(repo.folder, "master", base) == (2, 0)


def test__ahead_behind__remote_has_new_commits__is_behind(repo: Repo) -> None:
    base = repo.head()
    repo.branch("remote")
    repo.snap("r1", r="1\n")
    repo.switch("master")
    assert _reader().ahead_behind(repo.folder, base, "remote") == (0, 1)


def test__ahead_behind__diverged__counts_both_sides(repo: Repo) -> None:
    _, master, side = _diverge(repo)
    assert _reader().ahead_behind(repo.folder, master, side) == (2, 1)


# ── разница и дерево ─────────────────────────────────────────────────────────
def test__changed_paths__reports_added_modified_deleted(repo: Repo) -> None:
    repo.snap("setup", keep="k\n", gone="g\n")
    before = repo.head()
    repo.remove("gone")
    repo.snap("edit", keep="k2\n", fresh="f\n")
    changed = {path: status for status, path in _reader().changed_paths(repo.folder, before, repo.head())}
    assert changed == {"keep": "M", "fresh": "A", "gone": "D"}


def test__changed_paths__identical_commits__is_empty(repo: Repo) -> None:
    assert _reader().changed_paths(repo.folder, "HEAD", "HEAD") == []


def test__changed_paths__renamed_file__is_delete_plus_add(repo: Repo) -> None:
    before = repo.head()
    (repo.folder / "vkr" / "vkr.tex").rename(repo.folder / "vkr" / "renamed.tex")
    repo.snap("rename")
    changed = sorted(_reader().changed_paths(repo.folder, before, repo.head()))
    assert changed == [("A", "vkr/renamed.tex"), ("D", "vkr/vkr.tex")]


def test__tree_entries__lists_blobs_with_mode_and_size(repo: Repo) -> None:
    repo.snap("files", docs__a="hello\n", docs__b=b"\x00\x01\x02")
    entries = {e.path: e for e in _reader().tree_entries(repo.folder, "HEAD")}
    assert set(entries) == {"vkr/vkr.tex", "docs/a", "docs/b"}
    assert entries["docs/a"].kind == "blob"
    assert entries["docs/a"].mode == "100644"
    assert entries["docs/a"].size == len(b"hello\n")
    assert entries["docs/b"].size == 3
    assert len(entries["docs/a"].sha) == 40


# ── содержимое ───────────────────────────────────────────────────────────────
def test__read_files__returns_bytes_and_none_for_missing(repo: Repo) -> None:
    repo.snap("bin", blob=b"\x00\xff\x10binary\r\n")
    got = _reader().read_files(repo.folder, "HEAD", ["vkr/vkr.tex", "blob", "nope.txt"])
    assert got == {"vkr/vkr.tex": b"base\n", "blob": b"\x00\xff\x10binary\r\n", "nope.txt": None}


def test__read_files__empty_file_and_trailing_newlines(repo: Repo) -> None:
    repo.snap("edge", empty=b"", nl=b"\n\n")
    got = _reader().read_files(repo.folder, "HEAD", ["empty", "nl", "vkr/vkr.tex"])
    assert got == {"empty": b"", "nl": b"\n\n", "vkr/vkr.tex": b"base\n"}


def test__read_files__reads_an_older_commit(repo: Repo) -> None:
    first = repo.head()
    repo.snap("v2", vkr__vkr_tex="two\n")
    assert _reader().read_files(repo.folder, first, ["vkr/vkr.tex"]) == {"vkr/vkr.tex": b"base\n"}


def test__read_files__directory_is_not_a_file(repo: Repo) -> None:
    assert _reader().read_files(repo.folder, "HEAD", ["vkr"]) == {"vkr": None}


@pytest.mark.parametrize("path", ["", "../x", "./vkr/vkr.tex", "/etc/passwd"])
def test__read_files__unsafe_path__is_none(repo: Repo, path: str) -> None:
    assert _reader().read_files(repo.folder, "HEAD", [path]) == {path: None}


def test__read_files__name_with_spaces_and_colons(repo: Repo) -> None:
    repo.snap("odd", **{"my file": "a\n", "a:b": "c\n"})
    got = _reader().read_files(repo.folder, "HEAD", ["my file", "a:b"])
    assert got == {"my file": b"a\n", "a:b": b"c\n"}


@_posix_only
def test__read_files__name_with_newline__is_read_separately(repo: Repo) -> None:
    repo.snap("nl", **{"weird\nname": "w\n"})
    got = _reader().read_files(repo.folder, "HEAD", ["weird\nname", "vkr/vkr.tex"])
    assert got == {"weird\nname": b"w\n", "vkr/vkr.tex": b"base\n"}


def test__read_files__many_files(repo: Repo) -> None:
    repo.snap("many", **{f"many__f{i}": f"{i}\n" * i for i in range(60)})
    paths = [f"many/f{i}" for i in range(60)]
    got = _reader().read_files(repo.folder, "HEAD", paths)
    assert all(got[f"many/f{i}"] == (f"{i}\n" * i).encode() for i in range(60))


# ── штамп изменения ──────────────────────────────────────────────────────────
def test__path_stamp__returns_the_last_commit_that_touched_the_path(repo: Repo) -> None:
    repo.snap("a", a="1\n")
    touched = repo.snap("a2", a="2\n")
    repo.snap("other", b="x\n")
    stamp = _reader().path_stamp(repo.folder, "HEAD", "a")
    assert stamp is not None
    assert stamp.sha == touched
    assert stamp.committed_at.tzinfo is not None
    assert abs((datetime.now(UTC) - stamp.committed_at).total_seconds()) < 120


def test__path_stamp__with_exclusion__ignores_what_is_already_known(repo: Repo) -> None:
    repo.snap("a", a="1\n")
    known = repo.head()
    reader = _reader()
    assert reader.path_stamp(repo.folder, "HEAD", "a", exclude_reachable_from=known) is None
    newer = repo.snap("a2", a="2\n")
    stamp = reader.path_stamp(repo.folder, "HEAD", "a", exclude_reachable_from=known)
    assert stamp is not None
    assert stamp.sha == newer


def test__path_stamp__unknown_path__is_none(repo: Repo) -> None:
    assert _reader().path_stamp(repo.folder, "HEAD", "never.txt") is None
    assert _reader().path_last_changed_at(repo.folder, "HEAD", "never.txt") is None


@_posix_only
def test__path_stamp__glob_characters_are_literal(repo: Repo) -> None:
    starred = repo.snap("star", **{"a*b.txt": "x\n"})
    repo.snap("other", ab_txt="y\n")
    reader = _reader()
    assert reader.path_stamp(repo.folder, "HEAD", "*") is None
    stamp = reader.path_stamp(repo.folder, "HEAD", "a*b.txt")
    assert stamp is not None
    assert stamp.sha == starred


def test__path_last_changed_at__matches_stamp(repo: Repo) -> None:
    stamp = _reader().path_stamp(repo.folder, "HEAD", "vkr/vkr.tex")
    assert stamp is not None
    assert _reader().path_last_changed_at(repo.folder, "HEAD", "vkr/vkr.tex") == stamp.committed_at


# ── крупные файлы ────────────────────────────────────────────────────────────
def test__large_blobs__lists_blobs_over_the_limit_biggest_first(repo: Repo) -> None:
    known = repo.head()
    repo.snap("big", media__small=b"x" * 10, media__mid=b"y" * 5000, media__huge=b"z" * 9000)
    blobs = _reader().large_blobs(repo.folder, "HEAD", min_bytes=1000, exclude_reachable_from=known)
    assert [(b.path, b.size) for b in blobs] == [("media/huge", 9000), ("media/mid", 5000)]
    assert all(len(b.sha) == 40 for b in blobs)


def test__large_blobs__only_new_objects_count(repo: Repo) -> None:
    repo.snap("big", media__mid=b"y" * 5000)
    known = repo.head()
    repo.snap("tiny", t="1\n")
    assert _reader().large_blobs(repo.folder, "HEAD", min_bytes=1000, exclude_reachable_from=known) == []
    assert len(_reader().large_blobs(repo.folder, "HEAD", min_bytes=1000)) == 1


# ── авторы ───────────────────────────────────────────────────────────────────
def test__author_counts__groups_commits_by_author(repo: Repo) -> None:
    repo.authors.current = VcsAuthor("Anna", "anna@example.org")
    repo.snap("a1", a="1\n")
    repo.snap("a2", a="2\n")
    repo.authors.current = VcsAuthor("Boris", "boris@example.org")
    repo.snap("b1", b="1\n")
    counts = _reader().author_counts(repo.folder, "HEAD")
    pairs = [(c.name, c.email, c.commits) for c in counts]
    assert pairs[0] == ("Anna", "anna@example.org", 2)
    assert ("Boris", "boris@example.org", 1) in pairs
    assert sum(c.commits for c in counts) == 4


def test__author_counts__unknown_rev__is_empty(repo: Repo) -> None:
    assert _reader().author_counts(repo.folder, "refs/remotes/origin/main") == []


def test__reader__does_not_touch_the_work_tree_or_index(repo: Repo) -> None:
    (repo.folder / "vkr" / "vkr.tex").write_text("dirty\n", encoding="utf-8")
    before = repo.git.text(repo.folder, ["status", "--porcelain"])
    reader = _reader()
    reader.rev_parse(repo.folder, "HEAD")
    reader.tree_entries(repo.folder, "HEAD")
    reader.read_files(repo.folder, "HEAD", ["vkr/vkr.tex"])
    assert repo.git.text(repo.folder, ["status", "--porcelain"]) == before
    assert (repo.folder / "vkr" / "vkr.tex").read_text(encoding="utf-8") == "dirty\n"


def test__reader__shares_the_given_git_runner(repo: Repo) -> None:
    assert GitRepoReader(StoreGit()).rev_parse(repo.folder, "HEAD") == repo.head()
