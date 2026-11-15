"""Состояние ветки в частичном клоне: только локальные команды и без чтения блобов базы; сбой локального git."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.api.config import GitConfig
from hse_doc_studio.core.git_sync.entities import GitResult, RemoteTarget
from hse_doc_studio.core.git_sync.error_messages import git_error
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.url import parse_remote_url
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.git_flow import ChangeStatus
from hse_doc_studio.core.vcs.entities import VcsAuthor
from hse_doc_studio.infra.pack_studio.workspace_git import (
    PackWorkspaceGit,
    _parse_raw,
    _store_config,
    _subcommand,
    workspace_dirs,
)

_BASE_OID = "1" * 40
_ZERO = "0" * 40
_HEAD = "a" * 40
_PATHS = ("packs/demo/edited.tex", "packs/demo/same.tex", "packs/demo/new.tex", "packs/demo/gone.tex")


def _raw(*rows: tuple[str, str, str, str]) -> bytes:
    return b"".join(f":100644 100644 {old} {new} {st}\0{path}\0".encode() for old, new, st, path in rows)


_DIFF_INDEX = _raw(
    (_BASE_OID, _ZERO, "M", _PATHS[0]),
    ("2" * 40, _ZERO, "M", _PATHS[1]),
    (_ZERO, "3" * 40, "A", _PATHS[2]),
    ("4" * 40, _ZERO, "D", _PATHS[3]),
)


class _Runner:
    """Запускатель git: отвечает по подкоманде и помнит, какие команды шли с сетью, а какие без."""

    def __init__(self, replies: dict[str, Callable[[list[str]], GitResult]] | None = None) -> None:
        self.local: list[list[str]] = []
        self.network: list[list[str]] = []
        self._replies = replies or {}

    async def run(self, args: Sequence[str], **_kwargs: Any) -> GitResult:
        self.network.append(list(args))
        return GitResult(0, b"", "")

    async def run_local(self, args: Sequence[str], **kwargs: Any) -> GitResult:
        self.local.append(list(args))
        reply = self._replies.get(_subcommand(args))
        result = reply(list(args)) if reply else GitResult(0, b"", "")
        if kwargs.get("check", True) and result.returncode != 0:
            raise git_error(GitErrorCode.git_error, tail=result.stderr)
        return result


def _hash_object(args: list[str]) -> GitResult:
    # same.tex совпадает с базой, edited.tex нет.
    oids = {"packs/demo/edited.tex": "9" * 40, "packs/demo/same.tex": "2" * 40}
    paths = args[args.index("--") + 1 :]
    return GitResult(0, "".join(f"{oids[p]}\n" for p in paths).encode(), "")


def _status_runner() -> _Runner:
    return _Runner(
        {
            "rev-parse": lambda _a: GitResult(0, f"{_HEAD}\n".encode(), ""),
            "symbolic-ref": lambda _a: GitResult(1, b"", ""),
            "status": lambda _a: GitResult(0, b" M packs/demo/edited.tex\0", ""),
            "diff-index": lambda _a: GitResult(0, _DIFF_INDEX, ""),
            "hash-object": _hash_object,
            "rev-list": lambda _a: GitResult(0, b"2\t0\n", ""),
        }
    )


def _tree(tmp_path: Path) -> Path:
    dirs = workspace_dirs(tmp_path)
    for rel in _PATHS[:3]:
        (dirs.tree / rel).parent.mkdir(parents=True, exist_ok=True)
        (dirs.tree / rel).write_text("x", encoding="utf-8")
    return tmp_path


async def test__status__is_local_and_never_compares_file_contents_with_the_base(tmp_path: Path) -> None:
    runner = _status_runner()
    git = PackWorkspaceGit(runner, GitConfig())  # type: ignore[arg-type]

    status = await git.status(workspace_dirs(_tree(tmp_path)), base_branch="main", packs_path="packs")

    assert runner.network == []
    # Porcelain `git diff <база>` читает блоб базы для правленого файла: в частичном клоне его может не быть.
    assert not any(_subcommand(args) == "diff" for args in runner.local)
    (diff_index,) = [args for args in runner.local if _subcommand(args) == "diff-index"]
    assert "--raw" in diff_index
    assert "--no-renames" in diff_index
    assert "refs/remotes/origin/main" in diff_index
    # Хэшируются только файлы, правленые на диске; удалённый и новый файл не нужны.
    (hashed,) = [args for args in runner.local if _subcommand(args) == "hash-object"]
    assert hashed[hashed.index("--") + 1 :] == ["packs/demo/edited.tex", "packs/demo/same.tex"]
    assert {c.path: c.status for c in status.changed} == {
        "demo/edited.tex": ChangeStatus.modified,
        "demo/new.tex": ChangeStatus.added,
        "demo/gone.tex": ChangeStatus.deleted,
    }
    assert (status.behind, status.ahead) == (2, 0)


async def test__commit__staged_check_is_plumbing_without_rename_detection(tmp_path: Path) -> None:
    runner = _Runner({"diff-index": lambda _a: GitResult(0, b"", "")})
    git = PackWorkspaceGit(runner, GitConfig())  # type: ignore[arg-type]
    author = VcsAuthor(name="Анна", email="anna@example.org")

    sha = await git.commit(workspace_dirs(tmp_path), packs_path="packs", message="m", author=author)

    assert sha is None
    assert runner.network == []
    assert any(args[-4:] == ["--cached", "--quiet", "HEAD", "--"] for args in runner.local)


async def test__local_failure__is_a_workspace_error_without_git_output(tmp_path: Path) -> None:
    stderr = "fatal: transport 'https' not allowed\nfatal: could not fetch abc from promisor remote"
    runner = _Runner({"rev-parse": lambda _a: GitResult(128, b"", stderr)})
    git = PackWorkspaceGit(runner, GitConfig())  # type: ignore[arg-type]

    with pytest.raises(PackStudioError) as caught:
        await git.status(workspace_dirs(tmp_path), base_branch="main", packs_path="packs")

    assert caught.value.code is PackStudioErrorCode.workspace_git_failed
    assert caught.value.status == 409  # noqa: PLR2004 — не 502: хостинг тут ни при чём
    assert "promisor" not in caught.value.detail
    assert "transport" not in caught.value.detail


async def test__local_timeout__keeps_its_own_code(tmp_path: Path) -> None:
    class _Slow(_Runner):
        async def run_local(self, args: Sequence[str], **kwargs: Any) -> GitResult:
            raise git_error(GitErrorCode.timeout)

    git = PackWorkspaceGit(_Slow(), GitConfig())  # type: ignore[arg-type]

    with pytest.raises(GitSyncError) as caught:
        await git.local_branches(workspace_dirs(tmp_path))

    assert caught.value.code is GitErrorCode.timeout


async def test__diff__needs_base_contents_and_goes_through_the_network_runner(tmp_path: Path) -> None:
    runner = _Runner()
    git = PackWorkspaceGit(runner, GitConfig())  # type: ignore[arg-type]
    target = RemoteTarget(url=parse_remote_url("https://github.com/acme/packs"))

    await git.diff(workspace_dirs(tmp_path), target, base_branch="main", packs_path="packs", max_bytes=1000)

    (network,) = runner.network
    assert _subcommand(network) == "diff"
    assert "refs/remotes/origin/main" in network


def test__store_config__promisor_is_the_https_address_without_secrets() -> None:
    target = RemoteTarget(url=parse_remote_url("https://github.com/acme/packs"))

    config = dict(_store_config(target, "packs"))

    assert config["remote.origin.url"] == "https://github.com/acme/packs.git"
    assert config["remote.origin.promisor"] == "true"
    assert config["extensions.partialClone"] == "origin"
    assert not any("extraheader" in key or "helper" in key for key in config)
    assert "@" not in config["remote.origin.url"]


def test__parse_raw__reads_oids_status_and_paths_with_spaces() -> None:
    raw = _raw((_BASE_OID, _ZERO, "M", "packs/a b.tex"), (_ZERO, "5" * 40, "A", "packs/новый.tex"))

    changes = _parse_raw(raw)

    assert [(c.path, c.status, c.work_unknown) for c in changes] == [
        ("packs/a b.tex", "M", True),
        ("packs/новый.tex", "A", False),
    ]


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (["--work-tree", "/t", "status", "-z"], "status"),
        (["-C", "/t", "--work-tree", "/t", "hash-object", "--", "x"], "hash-object"),
        (["-c", "user.email=a@b", "--work-tree", "/t", "commit", "-m", "x"], "commit"),
        (["--"], ""),
    ],
)
def test__subcommand__skips_global_options_and_their_values(args: list[str], expected: str) -> None:
    assert _subcommand(args) == expected
