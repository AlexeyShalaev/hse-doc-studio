"""Чтение версии из коммита без checkout (`revision_sha`, `revision_files`, срез O2): команды локальные, блобы
частичного клона догружаются одной сетевой пачкой с доступом пространства, а не по одному на файл."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import pytest
from hse_doc_studio.api.config import GitConfig
from hse_doc_studio.core.git_sync.entities import GitResult, RemoteTarget
from hse_doc_studio.core.git_sync.url import parse_remote_url
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.infra.pack_studio.workspace_git import PackWorkspaceGit, _listed_blobs, _subcommand, workspace_dirs

_SHA = "a" * 40
_TARGET = RemoteTarget(url=parse_remote_url("https://github.com/acme/packs"))
_ENTRIES = (
    ("100644", "blob", "1" * 40, 12, "packs/p/templates/t/versions/1/version.yaml"),
    ("100755", "blob", "2" * 40, 5, "packs/p/templates/t/versions/1/run.sh"),
    ("120000", "blob", "3" * 40, 4, "packs/p/templates/t/versions/1/link"),
    ("160000", "commit", "4" * 40, 0, "packs/p/templates/t/versions/1/sub"),
)


def _ls_tree(entries: Sequence[tuple[str, str, str, int, str]] = _ENTRIES) -> bytes:
    return b"".join(
        f"{mode} {kind} {oid} {'-' if kind != 'blob' else str(size).rjust(7)}\t{path}\0".encode()
        for mode, kind, oid, size, path in entries
    )


class _Runner:
    def __init__(self, replies: dict[str, Callable[[list[str]], GitResult]]) -> None:
        self.local: list[list[str]] = []
        self.network: list[list[str]] = []
        self._replies = replies

    async def run(self, args: Sequence[str], **_kwargs: Any) -> GitResult:
        self.network.append(list(args))
        return GitResult(0, b"", "")

    async def run_local(self, args: Sequence[str], **_kwargs: Any) -> GitResult:
        self.local.append(list(args))
        reply = self._replies.get(_subcommand(args))
        return reply(list(args)) if reply else GitResult(0, b"", "")


def _git(runner: _Runner, tmp: Any) -> tuple[PackWorkspaceGit, Any]:
    return PackWorkspaceGit(runner, GitConfig()), workspace_dirs(tmp)  # type: ignore[arg-type]


def test__listed_blobs__keeps_regular_files_only() -> None:
    assert _listed_blobs(_ls_tree()) == [
        ("packs/p/templates/t/versions/1/version.yaml", "1" * 40, 12),
        ("packs/p/templates/t/versions/1/run.sh", "2" * 40, 5),
    ]
    assert _listed_blobs(b"") == []


@pytest.mark.parametrize(("name", "spec"), [("head", "HEAD"), ("base", "refs/remotes/origin/main")])
async def test__revision_sha__reads_the_commit_of_head_or_the_base_tip_without_the_network(
    name: str, spec: str, tmp_path: Any
) -> None:
    runner = _Runner({"rev-parse": lambda _a: GitResult(0, f"{_SHA}\n".encode(), "")})
    git, dirs = _git(runner, tmp_path)

    sha = await git.revision_sha(dirs, name=name, base_branch="main")  # type: ignore[arg-type]

    assert sha == _SHA
    assert runner.network == []
    assert runner.local == [["rev-parse", "--verify", "--quiet", f"{spec}^{{commit}}"]]


async def test__revision_sha__no_such_commit__none(tmp_path: Any) -> None:
    runner = _Runner({"rev-parse": lambda _a: GitResult(1, b"", "")})
    git, dirs = _git(runner, tmp_path)

    assert await git.revision_sha(dirs, name="base", base_branch="main") is None


async def test__revision_files__reads_regular_files_and_fetches_missing_blobs_in_one_batch(tmp_path: Any) -> None:
    contents = {"1" * 40: b"id: 1\n", "2" * 40: b"#!/bin/sh\n"}
    runner = _Runner(
        {
            "ls-tree": lambda _a: GitResult(0, _ls_tree(), ""),
            "rev-list": lambda _a: GitResult(0, f"?{'1' * 40}\n?{'2' * 40}\n?{'9' * 40}\n".encode(), ""),
            "cat-file": lambda a: GitResult(0, contents[a[-1]], ""),
        }
    )
    git, dirs = _git(runner, tmp_path)

    files = await git.revision_files(
        dirs, _TARGET, sha=_SHA, prefixes=["packs/p/templates/t/versions/1"], max_files=10, max_bytes=1000
    )

    assert files == {
        "packs/p/templates/t/versions/1/version.yaml": b"id: 1\n",
        "packs/p/templates/t/versions/1/run.sh": b"#!/bin/sh\n",
    }
    # Сеть только одна пачка за недостающими блобами версии, чужие (`9...`) не просятся.
    (fetch,) = runner.network
    assert fetch[fetch.index("--") + 2 :] == ["1" * 40, "2" * 40]
    assert [a for a in runner.local if _subcommand(a) == "cat-file"] == [
        ["cat-file", "blob", "1" * 40],
        ["cat-file", "blob", "2" * 40],
    ]
    (ls,) = [a for a in runner.local if _subcommand(a) == "ls-tree"]
    assert ls[-2:] == ["--", "packs/p/templates/t/versions/1"]


async def test__revision_files__nothing_missing__no_network(tmp_path: Any) -> None:
    runner = _Runner(
        {"ls-tree": lambda _a: GitResult(0, _ls_tree(), ""), "cat-file": lambda _a: GitResult(0, b"x", "")}
    )
    git, dirs = _git(runner, tmp_path)

    await git.revision_files(dirs, _TARGET, sha=_SHA, prefixes=["packs"], max_files=10, max_bytes=1000)

    assert runner.network == []


async def test__revision_files__nothing_listed__empty_and_no_reads(tmp_path: Any) -> None:
    runner = _Runner({"ls-tree": lambda _a: GitResult(0, b"", "")})
    git, dirs = _git(runner, tmp_path)

    assert await git.revision_files(dirs, _TARGET, sha=_SHA, prefixes=["packs"], max_files=10, max_bytes=1000) == {}
    assert [_subcommand(a) for a in runner.local] == ["ls-tree"]


@pytest.mark.parametrize(("max_files", "max_bytes"), [(1, 1000), (10, 16)])
async def test__revision_files__over_the_limits__workspace_too_large(
    max_files: int, max_bytes: int, tmp_path: Any
) -> None:
    runner = _Runner({"ls-tree": lambda _a: GitResult(0, _ls_tree(), "")})
    git, dirs = _git(runner, tmp_path)

    with pytest.raises(PackStudioError) as caught:
        await git.revision_files(dirs, _TARGET, sha=_SHA, prefixes=["packs"], max_files=max_files, max_bytes=max_bytes)

    assert caught.value.code is PackStudioErrorCode.workspace_too_large
    assert [_subcommand(a) for a in runner.local] == ["ls-tree"]


@pytest.mark.parametrize("sha", ["HEAD", "--upload-pack=x", "abc", "A" * 40])
async def test__revision_files__refuses_anything_but_a_commit_id(sha: str, tmp_path: Any) -> None:
    runner = _Runner({})
    git, dirs = _git(runner, tmp_path)

    with pytest.raises(PackStudioError) as caught:
        await git.revision_files(dirs, _TARGET, sha=sha, prefixes=["packs"], max_files=10, max_bytes=1000)

    assert caught.value.code is PackStudioErrorCode.workspace_git_failed
    assert runner.local == []


@pytest.mark.parametrize("prefix", [":(glob)**", ":/", "packs/*", "packs/a?b", "packs/[ab]"])
async def test__revision_files__refuses_pathspec_magic_and_wildcards_in_the_prefixes(
    prefix: str, tmp_path: Any
) -> None:
    runner = _Runner({})
    git, dirs = _git(runner, tmp_path)

    with pytest.raises(PackStudioError) as caught:
        await git.revision_files(dirs, _TARGET, sha=_SHA, prefixes=["packs", prefix], max_files=10, max_bytes=1000)

    assert caught.value.code is PackStudioErrorCode.path_not_allowed
    assert runner.local == []
