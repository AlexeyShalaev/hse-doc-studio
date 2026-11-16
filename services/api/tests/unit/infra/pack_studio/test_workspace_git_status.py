"""Состояние ветки в частичном клоне: локальные команды без чтения блобов базы, догрузка недостающего объекта с
доступом пространства и безопасная подсказка к сбою локального git."""

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
    _blob_oids,
    _control_paths,
    _parse_raw,
    _promised_object,
    _store_config,
    _subcommand,
    git_hint,
    workspace_dirs,
)

_BASE_OID = "1" * 40
_ZERO = "0" * 40
_HEAD = "a" * 40
_PATHS = ("packs/demo/edited.tex", "packs/demo/same.tex", "packs/demo/new.tex", "packs/demo/gone.tex")
_TARGET = RemoteTarget(url=parse_remote_url("https://github.com/acme/packs"))
_IGNORE_OID = "e" * 40
_PROMISOR_MISS = f"fatal: transport 'https' not allowed\nfatal: could not fetch {_IGNORE_OID} from promisor remote\n"


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

    status = await git.status(workspace_dirs(_tree(tmp_path)), _TARGET, base_branch="main", packs_path="packs")

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

    sha = await git.commit(workspace_dirs(tmp_path), _TARGET, packs_path="packs", message="m", author=author)

    assert sha is None
    assert runner.network == []
    assert any(args[-4:] == ["--cached", "--quiet", "HEAD", "--"] for args in runner.local)


async def test__local_failure__is_a_workspace_error_with_a_safe_hint(tmp_path: Path) -> None:
    stderr = "fatal: not a git repository: '/data/pack-studio/ws/git'\n"
    runner = _Runner({"rev-parse": lambda _a: GitResult(128, b"", stderr)})
    git = PackWorkspaceGit(runner, GitConfig())  # type: ignore[arg-type]

    with pytest.raises(PackStudioError) as caught:
        await git.status(workspace_dirs(tmp_path), _TARGET, base_branch="main", packs_path="packs")

    assert caught.value.code is PackStudioErrorCode.workspace_git_failed
    assert caught.value.status == 409  # noqa: PLR2004 — не 502: хостинг тут ни при чём
    assert "repository" not in caught.value.detail
    assert caught.value.ctx == {"hint": "git rev-parse: fatal: not a git repository: '<path>'"}
    assert runner.network == []


def _ignore_rules_missing_once() -> _Runner:
    """Свежий клон: `status` читает корневой `.gitignore` из индекса, а его блоба нет, пока его не догрузили."""
    fetched: set[str] = set()

    class _Store(_Runner):
        async def run(self, args: Sequence[str], **kwargs: Any) -> GitResult:
            fetched.update(arg for arg in args if len(arg) == 40)  # noqa: PLR2004 — идентификатор объекта
            return await super().run(args, **kwargs)

    def status(_args: list[str]) -> GitResult:
        if _IGNORE_OID in fetched:
            return GitResult(0, b" M packs/demo/edited.tex\0", "")
        return GitResult(128, b"", _PROMISOR_MISS)

    def ls_tree(_args: list[str]) -> GitResult:
        return GitResult(
            0, f"100644 blob {_IGNORE_OID}\t.gitignore\0100644 blob {'b' * 40}\tpacks/x.tex\0".encode(), ""
        )

    def rev_list(args: list[str]) -> GitResult:
        if "--missing=print" in args:
            missing = "" if _IGNORE_OID in fetched else f"?{_IGNORE_OID}\n"
            return GitResult(0, f"{_HEAD}\n{missing}".encode(), "")
        return GitResult(0, b"0\t0\n", "")

    return _Store(
        {
            "rev-parse": lambda _a: GitResult(0, f"{_HEAD}\n".encode(), ""),
            "symbolic-ref": lambda _a: GitResult(1, b"", ""),
            "status": status,
            "diff-index": lambda _a: GitResult(0, b"", ""),
            "for-each-ref": lambda _a: GitResult(0, b"refs/remotes/origin/main\n", ""),
            "ls-tree": ls_tree,
            "rev-list": rev_list,
        }
    )


async def test__status__missing_ignore_rules_blob__is_fetched_with_access_and_status_repeats(tmp_path: Path) -> None:
    runner = _ignore_rules_missing_once()
    git = PackWorkspaceGit(runner, GitConfig())  # type: ignore[arg-type]
    dirs = workspace_dirs(tmp_path)
    (dirs.git / "info").mkdir(parents=True)
    (dirs.git / "info" / "sparse-checkout").write_text("/packs/\n", encoding="utf-8")

    status = await git.status(dirs, _TARGET, base_branch="main", packs_path="packs")

    assert [c.path for c in status.uncommitted] == ["demo/edited.tex"]
    # Одна выборка по идентификатору: только недостающий блоб, без согласования истории; сам status в сеть не ходил.
    (fetch,) = runner.network
    assert fetch[:3] == ["-c", "fetch.negotiationAlgorithm=noop", "fetch"]
    assert fetch[fetch.index("--") + 1 :] == ["origin", _IGNORE_OID]
    assert "--filter=blob:none" in fetch
    statuses = [args for args in runner.local if _subcommand(args) == "status"]
    assert len(statuses) == 2  # noqa: PLR2004 — упал, догрузил, повторил
    # Пути для догрузки: папка паков и файлы правил на пути к ней.
    ls_tree = next(args for args in runner.local if _subcommand(args) == "ls-tree")
    assert ls_tree[ls_tree.index("--") + 1 :][:3] == ["packs", ".gitignore", ".gitattributes"]


async def test__local_failure__object_never_arrives__stops_after_a_few_rounds(tmp_path: Path) -> None:
    runner = _Runner(
        {
            "rev-parse": lambda _a: GitResult(0, f"{_HEAD}\n".encode(), ""),
            "status": lambda _a: GitResult(128, b"", _PROMISOR_MISS),
        }
    )
    git = PackWorkspaceGit(runner, GitConfig())  # type: ignore[arg-type]

    with pytest.raises(PackStudioError) as caught:
        await git.status(workspace_dirs(tmp_path), _TARGET, base_branch="main", packs_path="packs")

    assert caught.value.code is PackStudioErrorCode.workspace_git_failed
    assert len(runner.network) == 3  # noqa: PLR2004 — _LAZY_ROUNDS
    hint = str(caught.value.ctx["hint"])
    assert hint.startswith("git status: fatal: transport 'https' not allowed | fatal: could not fetch")
    assert _IGNORE_OID in hint


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
    await git.diff(workspace_dirs(tmp_path), _TARGET, base_branch="main", packs_path="packs", max_bytes=1000)

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


@pytest.mark.parametrize(
    ("stderr", "expected"),
    [
        (
            "fatal: unable to access 'https://x-access-token:ghp_abcdefghijklmnopqrstuvwxyz0123456789@github.com/a/b.git/'",
            "git fetch: fatal: unable to access '<url>",
        ),
        ("fatal: '/srv/hse/pack-studio/1/git' does not appear to be a git repository", "git fetch: fatal: '<path>'"),
        ("error: git@github.com:acme/packs.git refused", "git fetch: error: <url> refused"),
        (
            "warning: x\nfatal: bad object refs/remotes/origin/main",
            "git fetch: fatal: bad object refs/remotes/origin/main",
        ),
        ("", "git fetch"),
    ],
)
def test__git_hint__no_addresses_tokens_or_server_paths(stderr: str, expected: str) -> None:
    hint = git_hint("fetch", stderr)

    assert hint.startswith(expected)
    assert "ghp_" not in hint
    assert "/srv" not in hint
    assert "github.com" not in hint


def test__git_hint__is_short_and_printable() -> None:
    hint = git_hint("status", "fatal: " + "x" * 1000 + "\x1b[31m")

    assert len(hint) <= 320  # noqa: PLR2004 — подсказка, а не журнал
    assert "\x1b" not in hint


def test__promised_object__oid_from_the_lazy_fetch_failure() -> None:
    assert _promised_object(_PROMISOR_MISS) == _IGNORE_OID
    assert _promised_object("fatal: could not read Username") is None


def test__control_paths__root_and_every_folder_above_the_packs() -> None:
    assert _control_paths("packs") == [".gitignore", ".gitattributes", ".gitmodules"]
    assert _control_paths("a/b") == [
        ".gitignore",
        ".gitattributes",
        ".gitmodules",
        "a/.gitignore",
        "a/.gitattributes",
        "a/.gitmodules",
    ]


def test__blob_oids__only_blobs_of_ls_tree() -> None:
    raw = f"100644 blob {'1' * 40}\tpacks/a b.tex\0160000 commit {'2' * 40}\tsub\0".encode()

    assert _blob_oids(raw) == {"1" * 40}
