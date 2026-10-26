"""Запись коммита слияния низкоуровневыми командами git (порт IGitMergeCommitter).

`git merge` пишет маркеры конфликтов в живые файлы проекта и не умеет слияние JSON по полям,
поэтому слияние считает планировщик, а здесь дерево собирается во временном индексе из дерева
`ours` с поправками планировщика. Рабочее дерево и настоящий индекс при этом не задеваются:
индекс подравнивается только когда ветка сдвинута (`advance_branch`).
"""

from __future__ import annotations

import re
import tempfile
from collections.abc import Mapping
from pathlib import Path

from hse_doc_studio.core.vcs.entities import VcsAuthor
from hse_doc_studio.core.vcs.errors import VcsCommandError
from hse_doc_studio.core.vcs.protocols import ICommitAuthorProvider
from hse_doc_studio.core.vcs.refs import validate_ref_name
from hse_doc_studio.infra.git_sync.repo_reader import GitRepoReader
from hse_doc_studio.infra.git_sync.store_git import StoreGit

_ZERO_SHA = "0" * 40
_DEFAULT_MODE = "100644"
_FILE_MODES = frozenset({"100644", "100755"})
_TRAILER_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9-]*$")
_KIND_KEY = "Hse-Kind"
_KIND_SYNC = "sync"


class GitMergeCommitter:
    def __init__(
        self,
        author_provider: ICommitAuthorProvider,
        git: StoreGit | None = None,
        reader: GitRepoReader | None = None,
    ) -> None:
        self._authors = author_provider
        self._git = git or StoreGit()
        self._reader = reader or GitRepoReader(self._git)

    def commit_merge(
        self,
        project_folder: Path,
        *,
        ours: str,
        theirs: str,
        changes: Mapping[str, bytes | None],
        message: str,
        trailers: Mapping[str, str],
    ) -> str:
        parents = [self._resolve(project_folder, ours), self._resolve(project_folder, theirs)]
        for path in changes:
            _validate_path(path)
        body = _message(message, trailers)
        with tempfile.TemporaryDirectory(prefix="hse-studio-merge-") as scratch:
            env = {"GIT_INDEX_FILE": str(Path(scratch) / "index")}
            tree = self._build_tree(project_folder, parents[0], changes, env)
            author = self._author()
            args = ["commit-tree", tree, "-p", parents[0], "-p", parents[1], "-F", "-"]
            proc = self._git.run(project_folder, args, input_bytes=body.encode("utf-8"), author=author)
        return proc.stdout.decode().strip()

    def advance_branch(self, project_folder: Path, branch: str, *, expected: str, new: str) -> bool:
        validate_ref_name(branch)
        ref = f"refs/heads/{branch}"
        old_sha = self._resolve(project_folder, expected)
        new_sha = self._resolve(project_folder, new)
        proc = self._git.run(
            project_folder,
            ["update-ref", "-m", "hse-studio: sync", ref, new_sha, old_sha],
            author=self._author(),
            check=False,
        )
        if proc.returncode != 0:
            if self._reader.rev_parse(project_folder, ref) != old_sha:
                return False
            raise VcsCommandError("update-ref", proc.stderr.decode("utf-8", "replace"))
        if self._reader.current_branch(project_folder) == branch:
            self._git.run(project_folder, ["read-tree", "--reset", f"{new_sha}^{{tree}}"])
        return True

    def fast_forward(self, project_folder: Path, branch: str, *, expected: str, new: str) -> bool:
        if not self._reader.is_ancestor(project_folder, expected, new):
            raise VcsCommandError("fast-forward", f"{new} does not descend from {expected}")
        return self.advance_branch(project_folder, branch, expected=expected, new=new)

    def _build_tree(
        self, project_folder: Path, ours: str, changes: Mapping[str, bytes | None], env: Mapping[str, str]
    ) -> str:
        self._git.run(project_folder, ["read-tree", f"{ours}^{{tree}}"], env=env)
        if changes:
            modes = self._modes(project_folder, env)
            lines = [self._index_line(project_folder, path, data, modes) for path, data in changes.items()]
            self._git.run(
                project_folder, ["update-index", "-z", "--index-info"], input_bytes="".join(lines).encode(), env=env
            )
        return self._git.text(project_folder, ["write-tree"], env=env).strip()

    def _index_line(self, project_folder: Path, path: str, data: bytes | None, modes: Mapping[str, str]) -> str:
        if data is None:
            return f"0 {_ZERO_SHA}\t{path}\0"
        sha = self._git.run(project_folder, ["hash-object", "-w", "--no-filters", "--stdin"], input_bytes=data)
        mode = modes.get(path, _DEFAULT_MODE)
        return f"{mode if mode in _FILE_MODES else _DEFAULT_MODE} {sha.stdout.decode().strip()}\t{path}\0"

    def _modes(self, project_folder: Path, env: Mapping[str, str]) -> dict[str, str]:
        listing = self._git.text(project_folder, ["ls-files", "-s", "-z"], env=env)
        modes: dict[str, str] = {}
        for record in listing.split("\0"):
            meta, _, path = record.partition("\t")
            if path:
                modes[path] = meta.split(" ", 1)[0]
        return modes

    def _resolve(self, project_folder: Path, rev: str) -> str:
        sha = self._reader.rev_parse(project_folder, rev)
        if sha is None:
            raise VcsCommandError("rev-parse", f"unknown commit {rev}")
        return sha

    def _author(self) -> tuple[str, str]:
        author: VcsAuthor = self._authors.author()
        return author.name, author.email


def _validate_path(path: str) -> None:
    parts = path.split("/")
    if any(p in ("", ".", "..") or p.casefold() == ".git" for p in parts) or any(c in path for c in "\0\n\\"):
        raise ValueError(f"unsafe path in merge changes: {path!r}")


def _message(message: str, trailers: Mapping[str, str]) -> str:
    if _KIND_KEY in trailers:
        raise ValueError("Hse-Kind trailer is set by the committer")
    lines = [f"{_KIND_KEY}: {_KIND_SYNC}"]
    for key, value in trailers.items():
        if not _TRAILER_KEY.match(key) or "\n" in value or "\0" in value:
            raise ValueError(f"invalid trailer: {key!r}")
        lines.append(f"{key}: {value}")
    return f"{message.rstrip()}\n\n" + "\n".join(lines) + "\n"
