from __future__ import annotations

import functools
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import structlog

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import VcsChange, VcsCommitKind, VcsRestoreMode, VcsTagKind
from hse_doc_studio.core.vcs.entities import (
    VcsBranch,
    VcsCommit,
    VcsCommitDetail,
    VcsCommitStats,
    VcsDiff,
    VcsFileChange,
    VcsFileDiff,
    VcsRef,
    VcsRestoreResult,
    VcsSettings,
    VcsStatus,
    VcsTag,
)
from hse_doc_studio.core.vcs.errors import (
    VcsCommandError,
    VcsNotInitializedError,
    VcsUnavailableError,
)

logger = structlog.get_logger()

_HSE_STUDIO = ".hse-studio"
_GIT_SUBDIR = "git"

_UNIT = "\x1f"  # field separator inside one log record
_REC = "\x1e"  # record separator between log entries
_LOG_FMT = _UNIT.join(["%H", "%h", "%P", "%an", "%aI", "%D", "%B"]) + _REC

_PDF_EXCLUDE = ":(exclude)*.pdf"
_MAX_DIFF_FILES = 80
# git's well-known empty-tree object — used to diff a root commit (no parent).
_EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
_DEFAULT_DIFF_MAX_BYTES = 256_000

_KIND_TRAILER = re.compile(r"^Hse-Kind:\s*(\S+)\s*$", re.MULTILINE)

# git's various "empty commit" phrasings. `git commit` exits non-zero in all of
# them, but for us they all mean the same thing — there's nothing to snapshot,
# which is a no-op, not an error. The "nothing added to commit but untracked
# files present" wording shows up when the only changes are untracked files we
# deliberately excluded from `add` (e.g. compiled *.pdf artifacts).
_NO_CHANGES_MARKERS = (
    "nothing to commit",
    "nothing added to commit",
    "no changes added to commit",
)


@functools.lru_cache(maxsize=1)
def _empty_global_config() -> str:
    """Path to a real, empty gitconfig used as GIT_CONFIG_GLOBAL.

    Neutralises the user's ~/.gitconfig (which may set commit.gpgsign, hooks,
    aliases, etc.) for our headless commits. Cross-platform, unlike /dev/null.
    """
    path = Path(tempfile.gettempdir()) / "hse-studio-empty.gitconfig"
    try:
        if not path.exists():
            path.write_text("", encoding="utf-8")
    except OSError:
        return ""
    return str(path)


class GitVcsService:
    """ProjectVCS over the git CLI with an isolated store at
    ``<project>/.hse-studio/git/`` and ``--work-tree`` pointed at the project root.

    Never runs ``git init`` in the project root (no raw ``.git``) and never joins
    the user's own repository — the three coexistence cases (empty folder / user
    has a ``.git`` / project nested in a user repo) all resolve the same way.
    All methods are synchronous; callers offload to a worker thread.
    """

    def __init__(
        self,
        author_name: str = "HSE Studio",
        author_email: str = "bot@hse-studio.local",
        diff_max_bytes: int = _DEFAULT_DIFF_MAX_BYTES,
        default_branch: str = "master",
    ) -> None:
        self._author_name = author_name
        self._author_email = author_email
        self._diff_max_bytes = diff_max_bytes
        self._default_branch = default_branch

    # ── paths ────────────────────────────────────────────────────────────────
    def _git_dir(self, project: Project) -> Path:
        return project.folder / _HSE_STUDIO / _GIT_SUBDIR

    # ── low-level git invocation ─────────────────────────────────────────────
    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        env["GIT_CONFIG_NOSYSTEM"] = "1"  # ignore /etc/gitconfig
        gc = _empty_global_config()
        if gc:
            env["GIT_CONFIG_GLOBAL"] = gc  # ignore ~/.gitconfig
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GIT_OPTIONAL_LOCKS"] = "0"
        if os.name == "posix":
            # The container runs as a non-root user with no $HOME; give git a
            # writable one so init/gc don't trip over HOME=/.
            env["HOME"] = tempfile.gettempdir()
        return env

    def _base(self, project: Project) -> list[str]:
        return [
            "git",
            "--git-dir",
            str(self._git_dir(project)),
            "--work-tree",
            str(project.folder),
            "-c",
            f"user.name={self._author_name}",
            "-c",
            f"user.email={self._author_email}",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "tag.gpgsign=false",
            "-c",
            "core.quotepath=false",
            "-c",
            "safe.directory=*",
        ]

    def _run(
        self,
        project: Project,
        args: Sequence[str],
        *,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        cmd = [*self._base(project), *args]
        try:
            proc = subprocess.run(  # noqa: S603
                cmd,
                cwd=str(project.folder),
                capture_output=True,
                text=True,
                check=False,
                env=self._env(),
                encoding="utf-8",
                errors="replace",
            )
        except FileNotFoundError as exc:
            raise VcsUnavailableError("git executable not found") from exc
        except OSError as exc:
            raise VcsUnavailableError(str(exc)) from exc
        if check and proc.returncode != 0:
            raise VcsCommandError(_cmd_label(args), proc.stderr or proc.stdout)
        return proc

    # ── lifecycle ────────────────────────────────────────────────────────────
    def is_available(self, project: Project) -> bool:
        try:
            return project.folder.exists() and project.folder.is_dir()
        except OSError:
            return False

    def is_initialized(self, project: Project) -> bool:
        return (self._git_dir(project) / "HEAD").exists()

    def init(self, project: Project, ignore: Sequence[str]) -> None:
        if not self.is_available(project):
            raise VcsUnavailableError(f"project folder not accessible: {project.folder}")
        git_dir = self._git_dir(project)
        git_dir.parent.mkdir(parents=True, exist_ok=True)
        if not self.is_initialized(project):
            self._run(project, ["init", f"--initial-branch={self._default_branch}"], check=True)
        self.write_ignore(project, ignore)
        # Root snapshot — capture whatever already exists (empty folders allowed).
        self.commit(project, message="Создание проекта", kind=VcsCommitKind.init, allow_empty=True)

    def write_ignore(self, project: Project, ignore: Sequence[str]) -> None:
        """(Re)write the store's ignore file. Idempotent — called at init and
        refreshed on connect so the versioning scope tracks the current policy."""
        info_dir = self._git_dir(project) / "info"
        info_dir.mkdir(parents=True, exist_ok=True)
        (info_dir / "exclude").write_text("\n".join(ignore) + "\n", encoding="utf-8")

    def destroy(self, project: Project) -> None:
        shutil.rmtree(self._git_dir(project), ignore_errors=True)

    # ── commits ──────────────────────────────────────────────────────────────
    def commit(
        self,
        project: Project,
        *,
        message: str,
        kind: VcsCommitKind,
        paths: Sequence[str] | None = None,
        include_pdf: bool = False,
        allow_empty: bool = False,
    ) -> VcsCommit | None:
        if not self.is_initialized(project):
            raise VcsNotInitializedError(str(project.folder))
        add_args = ["add", "-A", "--"]
        add_args += list(paths) if paths else ["."]
        if not include_pdf:
            add_args.append(_PDF_EXCLUDE)
        self._run(project, add_args, check=True)

        commit_args = ["commit", "-m", f"{message}\n\nHse-Kind: {kind.value}"]
        if allow_empty:
            commit_args.append("--allow-empty")
        proc = self._run(project, commit_args)
        if proc.returncode != 0:
            combined = proc.stdout + proc.stderr
            if any(marker in combined for marker in _NO_CHANGES_MARKERS):
                return None
            raise VcsCommandError("commit", proc.stderr or proc.stdout)

        head = self._run(project, ["rev-parse", "HEAD"], check=True).stdout.strip()
        return self._one(project, head)

    def log(
        self,
        project: Project,
        *,
        doc_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[VcsCommit]:
        if not self.is_initialized(project):
            return []
        args = ["log", f"--pretty=format:{_LOG_FMT}", f"--skip={offset}", f"-n{limit}"]
        if doc_id:
            args += ["--", doc_id]
        proc = self._run(project, args)
        if proc.returncode != 0:
            return []  # empty repo (no commits yet)
        return self._parse_log(proc.stdout)

    def commit_detail(self, project: Project, commit_id: str) -> VcsCommitDetail:
        if not self.is_initialized(project):
            raise VcsNotInitializedError(str(project.folder))
        proc = self._run(project, ["log", f"--pretty=format:{_LOG_FMT}", "-n1", commit_id])
        if proc.returncode != 0:
            raise VcsCommandError("log", proc.stderr or f"unknown commit {commit_id}")
        commits = self._parse_log(proc.stdout)
        if not commits:
            raise VcsCommandError("log", f"commit not found: {commit_id}")

        names = self._run(project, ["show", "--name-status", "--format=", commit_id]).stdout
        files = tuple(
            VcsFileChange(path=path, change=change, old_path=old)
            for change, path, old in self._parse_name_status(names)
        )
        numstat = self._run(project, ["show", "--numstat", "--format=", commit_id]).stdout
        insertions = deletions = 0
        for line in numstat.splitlines():
            cols = line.split("\t")
            if len(cols) >= 3 and cols[0].isdigit() and cols[1].isdigit():
                insertions += int(cols[0])
                deletions += int(cols[1])
        commit = replace(
            commits[0],
            stats=VcsCommitStats(files=len(files), insertions=insertions, deletions=deletions),
        )
        return VcsCommitDetail(commit=commit, files=files)

    # ── status / diff ────────────────────────────────────────────────────────
    def status(self, project: Project, settings: VcsSettings) -> VcsStatus:  # noqa: C901
        git_dir = self._git_dir(project)
        if not self.is_available(project):
            return _empty_status(available=False, store_path=str(git_dir), settings=settings)
        if not self.is_initialized(project):
            return _empty_status(available=True, store_path=str(git_dir), settings=settings)

        status_args = ["status", "--porcelain"]
        if not settings.track_pdf:
            status_args += ["--", ".", _PDF_EXCLUDE]
        porcelain = self._run(project, status_args).stdout
        modified = untracked = staged = 0
        for line in porcelain.splitlines():
            if len(line) < 2:  # noqa: PLR2004
                continue
            index_status, worktree_status = line[0], line[1]
            if index_status not in {" ", "?"}:
                staged += 1
            if worktree_status == "M":
                modified += 1
            elif index_status == "?" and worktree_status == "?":
                untracked += 1

        head_proc = self._run(project, ["rev-parse", "HEAD"])
        head = head_proc.stdout.strip() if head_proc.returncode == 0 else None
        branch_proc = self._run(project, ["rev-parse", "--abbrev-ref", "HEAD"])
        branch = branch_proc.stdout.strip() if branch_proc.returncode == 0 else None
        recent = self.log(project, limit=1)
        return VcsStatus(
            available=True,
            initialized=True,
            current_branch=branch,
            head=head,
            dirty=bool(porcelain.strip()),
            modified=modified,
            untracked=untracked,
            staged=staged,
            last_snapshot_at=recent[0].created_at if recent else None,
            store_path=str(git_dir),
            tracking_enabled=settings.tracking_enabled,
        )

    def diff(  # noqa: C901
        self,
        project: Project,
        *,
        from_id: str | None = None,
        to_id: str | None = None,
        path: str | None = None,
        max_bytes: int | None = None,
    ) -> VcsDiff:
        if not self.is_initialized(project):
            return VcsDiff(from_id=from_id, to_id=to_id, files=(), truncated=False)
        budget = max_bytes or self._diff_max_bytes
        range_args = self._diff_range(project, from_id, to_id)

        name_args = ["diff", "--name-status", *range_args]
        if path:
            name_args += ["--", path]
        names = self._run(project, name_args)
        if names.returncode != 0:
            return VcsDiff(from_id=from_id, to_id=to_id, files=(), truncated=False)
        entries = self._parse_name_status(names.stdout)

        files: list[VcsFileDiff] = []
        total = 0
        truncated = len(entries) > _MAX_DIFF_FILES
        for change, file_path, _old in entries[:_MAX_DIFF_FILES]:
            patch = self._run(project, ["diff", *range_args, "--", file_path]).stdout
            binary = "Binary files" in patch and "differ" in patch
            if binary:
                patch = ""
            elif total + len(patch) > budget:
                patch = patch[: max(0, budget - total)]
                truncated = True
            files.append(VcsFileDiff(path=file_path, change=change, patch=patch, binary=binary))
            total += len(patch)
            if truncated and total >= budget:
                break
        return VcsDiff(from_id=from_id, to_id=to_id, files=tuple(files), truncated=truncated)

    def _diff_range(self, project: Project, from_id: str | None, to_id: str | None) -> list[str]:
        if from_id and to_id:
            return [from_id, to_id]
        if to_id:
            parent = self._run(project, ["rev-parse", "--verify", f"{to_id}^"])
            base = f"{to_id}^" if parent.returncode == 0 else _EMPTY_TREE
            return [base, to_id]
        return ["HEAD"]  # working tree vs HEAD (uncommitted changes)

    # ── restore ──────────────────────────────────────────────────────────────
    def restore(
        self,
        project: Project,
        *,
        commit_id: str,
        paths: Sequence[str] | None = None,
        mode: VcsRestoreMode = VcsRestoreMode.snapshot,
        include_pdf: bool = False,
    ) -> VcsRestoreResult:
        if not self.is_initialized(project):
            raise VcsNotInitializedError(str(project.folder))
        verify = self._run(project, ["rev-parse", "--verify", f"{commit_id}^{{commit}}"])
        if verify.returncode != 0:
            raise VcsCommandError("rev-parse", verify.stderr or f"unknown commit {commit_id}")
        target = verify.stdout.strip()

        if mode == VcsRestoreMode.hard:
            self._run(project, ["reset", "--hard", target], check=True)
            return VcsRestoreResult(restored_from=target, new_snapshot_id=None, pre_snapshot_id=None, files_changed=0)

        # Safe snapshot restore: preserve work-in-progress, then reset the working
        # tree to the target and record it as a new commit (HEAD/history intact).
        pre_id = None
        current = self.status(project, VcsSettings(track_pdf=include_pdf))
        if current.dirty:
            pre = self.commit(
                project,
                message="автосохранение перед откатом",
                kind=VcsCommitKind.manual,
                include_pdf=include_pdf,
            )
            pre_id = pre.id if pre else None

        if paths:
            self._run(project, ["checkout", target, "--", *paths], check=True)
        else:
            self._run(project, ["read-tree", "-m", "-u", target], check=True)

        new = self.commit(
            project,
            message=f"Возврат к версии {target[:7]}",
            kind=VcsCommitKind.restore,
            include_pdf=include_pdf,
        )
        files_changed = 0
        if new is not None:
            files_changed = len(self.commit_detail(project, new.id).files)
        return VcsRestoreResult(
            restored_from=target,
            new_snapshot_id=new.id if new else None,
            pre_snapshot_id=pre_id,
            files_changed=files_changed,
        )

    # ── branches ─────────────────────────────────────────────────────────────
    def list_branches(self, project: Project) -> list[VcsBranch]:
        if not self.is_initialized(project):
            return []
        fmt = _UNIT.join(["%(refname:short)", "%(objectname)", "%(HEAD)"])
        proc = self._run(project, ["branch", f"--format={fmt}"])
        if proc.returncode != 0:
            return []
        branches: list[VcsBranch] = []
        for line in proc.stdout.splitlines():
            if not line.strip():
                continue
            parts = line.split(_UNIT)
            if len(parts) < 3:  # noqa: PLR2004
                continue
            name = parts[0].strip()
            branches.append(
                VcsBranch(
                    name=name,
                    head=parts[1].strip(),
                    is_current=parts[2].strip() == "*",
                    is_protected=name == self._default_branch,
                )
            )
        return branches

    def create_branch(
        self,
        project: Project,
        settings: VcsSettings,
        *,
        name: str,
        from_commit: str | None = None,
        switch: bool = True,
    ) -> VcsBranch:
        if not self.is_initialized(project):
            raise VcsNotInitializedError(str(project.folder))
        args = ["branch", name]
        if from_commit:
            args.append(from_commit)
        self._run(project, args, check=True)
        if switch:
            self.switch_branch(project, settings, name=name)
        for branch in self.list_branches(project):
            if branch.name == name:
                return branch
        head = self._run(project, ["rev-parse", name]).stdout.strip()
        return VcsBranch(name=name, head=head, is_current=switch, is_protected=name == self._default_branch)

    def switch_branch(
        self,
        project: Project,
        settings: VcsSettings,
        *,
        name: str,
        autosnapshot: bool = True,
    ) -> VcsStatus:
        if not self.is_initialized(project):
            raise VcsNotInitializedError(str(project.folder))
        if autosnapshot and self.status(project, settings).dirty:
            self.commit(
                project,
                message=f"автосохранение перед переключением на {name}",
                kind=VcsCommitKind.manual,
                include_pdf=settings.track_pdf,
            )
        self._run(project, ["checkout", name], check=True)
        return self.status(project, settings)

    def delete_branch(self, project: Project, *, name: str) -> None:
        if not self.is_initialized(project):
            raise VcsNotInitializedError(str(project.folder))
        self._run(project, ["branch", "-D", name], check=True)

    # ── tags ─────────────────────────────────────────────────────────────────
    def list_tags(self, project: Project) -> list[VcsTag]:
        if not self.is_initialized(project):
            return []
        fmt = _UNIT.join(
            [
                "%(refname:short)",
                "%(objectname)",
                "%(*objectname)",
                "%(creatordate:iso-strict)",
                "%(objecttype)",
                "%(contents:subject)",
            ]
        )
        proc = self._run(project, ["for-each-ref", "refs/tags", f"--format={fmt}"])
        if proc.returncode != 0:
            return []
        tags: list[VcsTag] = []
        for line in proc.stdout.splitlines():
            if not line.strip():
                continue
            parts = line.split(_UNIT)
            if len(parts) < 6:  # noqa: PLR2004
                continue
            short, obj, deref, date_raw, objtype, subject = parts[:6]
            annotated = objtype.strip() == "tag"
            tags.append(
                VcsTag(
                    name=short.strip(),
                    commit_id=deref.strip() or obj.strip(),
                    kind=VcsTagKind.release if annotated else VcsTagKind.tag,
                    message=subject.strip() if annotated and subject.strip() else None,
                    created_at=_parse_date_opt(date_raw.strip()),
                )
            )
        return tags

    def create_tag(
        self,
        project: Project,
        *,
        name: str,
        commit_id: str | None = None,
        message: str | None = None,
        kind: VcsTagKind = VcsTagKind.tag,
    ) -> VcsTag:
        if not self.is_initialized(project):
            raise VcsNotInitializedError(str(project.folder))
        args = ["tag", "-a", name, "-m", message or name] if kind == VcsTagKind.release else ["tag", name]
        if commit_id:
            args.append(commit_id)
        self._run(project, args, check=True)
        for tag in self.list_tags(project):
            if tag.name == name:
                return tag
        resolved = commit_id or self._run(project, ["rev-parse", "HEAD"]).stdout.strip()
        return VcsTag(name=name, commit_id=resolved, kind=kind, message=message, created_at=None)

    def delete_tag(self, project: Project, *, name: str) -> None:
        if not self.is_initialized(project):
            raise VcsNotInitializedError(str(project.folder))
        self._run(project, ["tag", "-d", name], check=True)

    # ── parsing helpers ──────────────────────────────────────────────────────
    def _one(self, project: Project, commit_id: str) -> VcsCommit | None:
        proc = self._run(project, ["log", f"--pretty=format:{_LOG_FMT}", "-n1", commit_id])
        commits = self._parse_log(proc.stdout) if proc.returncode == 0 else []
        return commits[0] if commits else None

    def _parse_log(self, raw: str) -> list[VcsCommit]:
        commits: list[VcsCommit] = []
        for record in raw.split(_REC):
            rec = record.strip("\n")
            if not rec.strip():
                continue
            fields = rec.split(_UNIT)
            if len(fields) < 7:  # noqa: PLR2004
                continue
            full, short, parents_raw, author, date_raw, refs_raw, body = fields[:7]
            commits.append(
                VcsCommit(
                    id=full.strip(),
                    short_id=short.strip(),
                    kind=_kind_from_body(body),
                    message=_subject(body),
                    author=author.strip(),
                    created_at=_parse_date(date_raw.strip()),
                    parents=tuple(p for p in parents_raw.split() if p),
                    refs=_parse_refs(refs_raw),
                )
            )
        return commits

    def _parse_name_status(self, raw: str) -> list[tuple[VcsChange, str, str | None]]:
        out: list[tuple[VcsChange, str, str | None]] = []
        for line in raw.splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            change = _map_change(parts[0][0])
            if parts[0][0] in {"R", "C"} and len(parts) >= 3:  # noqa: PLR2004
                out.append((change, parts[2], parts[1]))
            elif len(parts) >= 2:  # noqa: PLR2004
                out.append((change, parts[1], None))
        return out


def _cmd_label(args: Sequence[str]) -> str:
    return " ".join(args[:2])


def _map_change(letter: str) -> VcsChange:
    return {
        "A": VcsChange.added,
        "M": VcsChange.modified,
        "D": VcsChange.deleted,
        "R": VcsChange.renamed,
        "C": VcsChange.copied,
    }.get(letter, VcsChange.modified)


def _kind_from_body(body: str) -> VcsCommitKind:
    match = _KIND_TRAILER.search(body)
    if match:
        try:
            return VcsCommitKind(match.group(1))
        except ValueError:
            pass
    return VcsCommitKind.manual


def _subject(body: str) -> str:
    for line in body.splitlines():
        if line.strip():
            return line.strip()
    return ""


def _parse_date(raw: str) -> datetime:
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return datetime.now().astimezone()


def _parse_date_opt(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _parse_refs(raw: str) -> tuple[VcsRef, ...]:
    refs: list[VcsRef] = []
    for token in (t.strip() for t in raw.split(",")):
        if not token:
            continue
        if token.startswith("tag:"):
            refs.append(VcsRef(name=token[4:].strip(), kind="tag"))
        elif "->" in token:
            refs.append(VcsRef(name=token.split("->")[-1].strip(), kind="head"))
        else:
            refs.append(VcsRef(name=token, kind="branch"))
    return tuple(refs)


def _empty_status(*, available: bool, store_path: str, settings: VcsSettings) -> VcsStatus:
    return VcsStatus(
        available=available,
        initialized=False,
        current_branch=None,
        head=None,
        dirty=False,
        modified=0,
        untracked=0,
        staged=0,
        last_snapshot_at=None,
        store_path=store_path,
        tracking_enabled=settings.tracking_enabled,
    )
