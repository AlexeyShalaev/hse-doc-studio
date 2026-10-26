"""Чтение истории и объектов хранилища проекта для синхронизации (порт IGitRepoReader).

Только объекты и ссылки: рабочее дерево, индекс и сеть не участвуют, поэтому чтение дёшево
и безопасно в любой момент, в том числе пока идёт сборка.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from hse_doc_studio.core.enums import VcsCommitKind
from hse_doc_studio.core.git_sync.entities import AuthorCount, CommitBrief, LargeBlob, PathStamp, TreeEntry
from hse_doc_studio.core.vcs.errors import VcsCommandError
from hse_doc_studio.core.vcs.refs import validate_revision
from hse_doc_studio.infra.git_sync.store_git import StoreGit

# Пути из запросов трактуются буквально, без магии pathspec (`:(...)`, `*`).
_LITERAL = {"GIT_LITERAL_PATHSPECS": "1"}
_SEP = "\x1f"
_END = "\x1e"
_BRIEF_FORMAT = _SEP.join(["%H", "%an", "%ae", "%aI", "%B"]) + _END
_KIND_TRAILER = re.compile(r"^Hse-Kind:\s*(\S+)\s*$", re.MULTILINE)
_SHORT_ID = 7


class GitRepoReader:
    def __init__(self, git: StoreGit | None = None) -> None:
        self._git = git or StoreGit()

    def rev_parse(self, project_folder: Path, ref: str) -> str | None:
        proc = self._git.run(
            project_folder, ["rev-parse", "--verify", "--quiet", f"{validate_revision(ref)}^{{commit}}"], check=False
        )
        if proc.returncode == 0:
            return proc.stdout.decode().strip()
        self._raise_unless_missing("rev-parse", proc.returncode, proc.stderr)
        return None

    def current_branch(self, project_folder: Path) -> str | None:
        proc = self._git.run(project_folder, ["symbolic-ref", "--short", "--quiet", "HEAD"], check=False)
        if proc.returncode == 0:
            return proc.stdout.decode().strip() or None
        self._raise_unless_missing("symbolic-ref", proc.returncode, proc.stderr)
        return None

    def merge_base(self, project_folder: Path, a: str, b: str) -> str | None:
        proc = self._git.run(project_folder, ["merge-base", validate_revision(a), validate_revision(b)], check=False)
        if proc.returncode == 0:
            return proc.stdout.decode().strip() or None
        self._raise_unless_missing("merge-base", proc.returncode, proc.stderr)
        return None

    def merge_bases(self, project_folder: Path, a: str, b: str) -> list[str]:
        proc = self._git.run(
            project_folder, ["merge-base", "--all", validate_revision(a), validate_revision(b)], check=False
        )
        if proc.returncode == 0:
            return proc.stdout.decode().split()
        self._raise_unless_missing("merge-base", proc.returncode, proc.stderr)
        return []

    def is_ancestor(self, project_folder: Path, ancestor: str, descendant: str) -> bool:
        proc = self._git.run(
            project_folder,
            ["merge-base", "--is-ancestor", validate_revision(ancestor), validate_revision(descendant)],
            check=False,
        )
        if proc.returncode in (0, 1):
            return proc.returncode == 0
        raise VcsCommandError("merge-base", proc.stderr.decode("utf-8", "replace"))

    def ahead_behind(self, project_folder: Path, local: str, remote: str) -> tuple[int, int]:
        out = self._git.text(
            project_folder,
            ["rev-list", "--left-right", "--count", f"{validate_revision(local)}...{validate_revision(remote)}"],
        )
        ahead, behind = out.split()
        return int(ahead), int(behind)

    def changed_paths(self, project_folder: Path, a: str, b: str) -> list[tuple[str, str]]:
        """Пары (статус, путь) между двумя коммитами: A, M, D или T; переименования не склеиваются."""
        out = self._git.text(
            project_folder,
            [
                "diff-tree",
                "-r",
                "-z",
                "--name-status",
                "--no-renames",
                "--no-ext-diff",
                validate_revision(a),
                validate_revision(b),
            ],
        )
        tokens = out.split("\0")
        return [(tokens[i], tokens[i + 1]) for i in range(0, len(tokens) - 1, 2) if tokens[i]]

    def tree_entries(self, project_folder: Path, commit: str) -> list[TreeEntry]:
        out = self._git.text(
            project_folder, ["ls-tree", "-r", "-z", "-l", "--full-tree", f"{validate_revision(commit)}^{{tree}}"]
        )
        return [_parse_tree_entry(record) for record in out.split("\0") if record]

    def read_files(self, project_folder: Path, commit: str, paths: Sequence[str]) -> Mapping[str, bytes | None]:
        """Содержимое файлов в коммите; None — файла нет, это не blob (gitlink) или путь недопустим."""
        rev = validate_revision(commit)
        result: dict[str, bytes | None] = {}
        batched: list[str] = []
        for path in dict.fromkeys(paths):
            result[path] = None
            if _is_plain_path(path):
                batched.append(path)
        if batched:
            result.update(self._cat_batch(project_folder, rev, batched))
        return result

    def path_stamp(
        self, project_folder: Path, tip: str, path: str, *, exclude_reachable_from: str | None = None
    ) -> PathStamp | None:
        revs = [validate_revision(tip)]
        if exclude_reachable_from:
            revs.append(f"^{validate_revision(exclude_reachable_from)}")
        out = self._git.run(
            project_folder,
            ["log", "-1", f"--format=%ct{_SEP}%H", *revs, "--", path],
            env=_LITERAL,
        ).stdout.decode()
        stamp, _, sha = out.strip().partition(_SEP)
        if not stamp or not sha:
            return None
        return PathStamp(committed_at=datetime.fromtimestamp(int(stamp), tz=UTC), sha=sha)

    def path_last_changed_at(self, project_folder: Path, commit: str, path: str) -> datetime | None:
        stamp = self.path_stamp(project_folder, commit, path)
        return stamp.committed_at if stamp else None

    def large_blobs(
        self, project_folder: Path, tip: str, *, min_bytes: int, exclude_reachable_from: str | None = None
    ) -> list[LargeBlob]:
        revs = [validate_revision(tip)]
        if exclude_reachable_from:
            revs.append(f"^{validate_revision(exclude_reachable_from)}")
        listed = self._git.run(project_folder, ["rev-list", "--objects", *revs]).stdout
        checked = self._git.run(
            project_folder,
            ["cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize) %(rest)"],
            input_bytes=listed,
        ).stdout.decode("utf-8", "replace")
        found: dict[str, LargeBlob] = {}
        for line in checked.splitlines():
            sha, kind, size, path = (line.split(" ", 3) + [""])[:4]
            if kind == "blob" and size.isdigit() and int(size) >= min_bytes and sha not in found:
                found[sha] = LargeBlob(path=path, sha=sha, size=int(size))
        return sorted(found.values(), key=lambda blob: (-blob.size, blob.path))

    def author_counts(self, project_folder: Path, rev: str) -> list[AuthorCount]:
        out = self._git.text(project_folder, ["log", f"--format=%an{_SEP}%ae", validate_revision(rev)], check=False)
        counts = Counter(tuple(line.split(_SEP, 1)) for line in out.splitlines() if _SEP in line)
        ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        return [AuthorCount(name=name, email=email, commits=commits) for (name, email), commits in ranked]

    def commit_briefs(self, project_folder: Path, rev: str, *, limit: int) -> list[CommitBrief]:
        out = self._git.text(
            project_folder,
            ["log", f"--format={_BRIEF_FORMAT}", f"-n{max(limit, 0)}", validate_revision(rev), "--"],
            check=False,
        )
        return [brief for record in out.split(_END) if (brief := _parse_brief(record)) is not None]

    def count_commits(self, project_folder: Path, rev: str) -> int:
        out = self._git.text(project_folder, ["rev-list", "--count", validate_revision(rev), "--"], check=False)
        return int(out) if out.strip().isdigit() else 0

    def _cat_batch(self, project_folder: Path, rev: str, paths: list[str]) -> dict[str, bytes | None]:
        """`cat-file --batch`: путь с переводом строки в строку запроса не помещается, его читаем отдельно."""
        queue = [p for p in paths if "\n" not in p]
        found: dict[str, bytes | None] = {}
        if queue:
            request = "".join(f"{rev}:{path}\n" for path in queue).encode("utf-8")
            data = self._git.run(project_folder, ["cat-file", "--batch"], input_bytes=request).stdout
            found.update(zip(queue, _parse_batch(data, len(queue)), strict=True))
        for path in (p for p in paths if "\n" in p):
            proc = self._git.run(project_folder, ["cat-file", "blob", f"{rev}:{path}"], check=False)
            found[path] = proc.stdout if proc.returncode == 0 else None
        return found

    @staticmethod
    def _raise_unless_missing(command: str, returncode: int, stderr: bytes) -> None:
        """Код 1 у этих команд значит «нет такого», всё остальное — поломка хранилища."""
        if returncode != 1:
            raise VcsCommandError(command, stderr.decode("utf-8", "replace"))


def _parse_brief(record: str) -> CommitBrief | None:
    fields = record.strip("\n").split(_SEP, 4)
    if len(fields) != 5:  # noqa: PLR2004
        return None
    sha, author, email, moment, body = fields
    try:
        created_at = datetime.fromisoformat(moment)
    except ValueError:
        return None
    kind = _KIND_TRAILER.search(body)
    return CommitBrief(
        id=sha,
        short_id=sha[:_SHORT_ID],
        message=body.strip().splitlines()[0] if body.strip() else "",
        author=author,
        author_email=email or None,
        created_at=created_at,
        kind=_kind(kind.group(1) if kind else None),
    )


def _kind(raw: str | None) -> str:
    """Вид коммита по трейлеру; незнакомый (более новой Студии) читается как manual, как в истории версий."""
    try:
        return VcsCommitKind(raw).value if raw else VcsCommitKind.manual.value
    except ValueError:
        return VcsCommitKind.manual.value


def _is_plain_path(path: str) -> bool:
    return bool(path) and not path.startswith(("/", "./", "../")) and "\0" not in path


def _parse_tree_entry(record: str) -> TreeEntry:
    meta, _, path = record.partition("\t")
    mode, kind, sha, size = meta.split()
    return TreeEntry(path=path, mode=mode, kind=kind, sha=sha, size=int(size) if size.isdigit() else None)


def _parse_batch(data: bytes, count: int) -> list[bytes | None]:
    """Разбор вывода `cat-file --batch`: «<sha> <тип> <размер>\\n<байты>\\n» или «<запрос> missing\\n»."""
    out: list[bytes | None] = []
    pos = 0
    for _ in range(count):
        end = data.index(b"\n", pos)
        header = data[pos:end].split(b" ")
        pos = end + 1
        if len(header) != 3 or not header[2].isdigit():  # noqa: PLR2004
            out.append(None)
            continue
        size = int(header[2])
        out.append(data[pos : pos + size] if header[1] == b"blob" else None)
        pos += size + 1
    return out
