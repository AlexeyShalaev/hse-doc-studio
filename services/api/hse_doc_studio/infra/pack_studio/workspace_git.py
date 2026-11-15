"""Git рабочего пространства Студии шаблонов: частичный закалённый клон репозитория паков (порт IPackWorkspaceGit).

Своего сетевого git здесь нет: каждая команда идёт через `IGitRemoteRunner` синхронизации проектов (окружение по
белому списку, защитные `-c`, токен только в окружении процесса через `http.<адрес>.extraheader`, egress, доверие
к хостам, очистка вывода от секретов). Отсюда только раскладка и аргументы:

- хранилище `git/` лежит вне рабочего дерева `tree/`, поэтому файлы `.git` в дереве не появляются, а пути API до
  хранилища не дотягиваются;
- выборка без блобов (`--filter=blob:none`, D6) и разреженное дерево только с папкой паков: блобы приходят лениво,
  ровно для неё. История коммитов и деревьев целая: ветке и слиянию с базой (T6) нужна общая история;
- `core.symlinks=false`, `core.protectNTFS`, `core.protectHFS`, без подмодулей и без фоновой сборки мусора; хуки,
  fsmonitor и помощники учётных данных выключает сам запускатель на каждой команде;
- адрес в конфиге без секретов: он нужен ленивой подгрузке блобов (promisor remote `origin`).
"""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import Sequence
from pathlib import Path

import yaml

from hse_doc_studio.api.config import GitConfig
from hse_doc_studio.core.git_sync.entities import RemoteTarget
from hse_doc_studio.core.git_sync.error_classifier import GitOp
from hse_doc_studio.core.git_sync.error_messages import git_error
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.protocols import IGitRemoteRunner
from hse_doc_studio.core.git_sync.url import RemoteKind
from hse_doc_studio.core.pack_studio.entities import ReleasedVersions
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.git_flow import (
    ChangeStatus,
    FileChange,
    MergeOutcome,
    PushOutcome,
    WorkGitStatus,
)
from hse_doc_studio.core.pack_studio.paths import is_registry_path, template_key
from hse_doc_studio.core.pack_studio.protocols import WorkspaceDirs, WorkspaceLimits
from hse_doc_studio.core.vcs.entities import VcsAuthor
from hse_doc_studio.core.vcs.errors import VcsInvalidRefError
from hse_doc_studio.core.vcs.refs import validate_ref_name
from hse_doc_studio.infra.template.releases import parse_releases

_LOCAL_TIMEOUT_S = 60.0
_REMOTE = "origin"
# Реестр выпусков крупнее этого не читается: это не реестр, а попытка занять память api.
_REGISTRY_MAX_BYTES = 1_048_576
_KIB = 1024


def remote_ref(branch: str) -> str:
    return f"refs/remotes/{_REMOTE}/{branch}"


def _author_config(author: VcsAuthor) -> list[str]:
    """Подпись коммита из профиля человека (автор и коммиттер); подпись GPG и хуки выключены."""
    return ["-c", f"user.name={author.name}", "-c", f"user.email={author.email}", "-c", "commit.gpgsign=false"]


def _scope(packs_path: str) -> list[str]:
    return ["--", "." if packs_path == "." else packs_path]


def _rel(name: str, packs_path: str) -> str | None:
    if packs_path == ".":
        return name
    prefix = f"{packs_path}/"
    return name[len(prefix) :] if name.startswith(prefix) else None


def _status_of(code: str) -> ChangeStatus:
    if "D" in code:
        return ChangeStatus.deleted
    if "A" in code or code == "??":
        return ChangeStatus.added
    return ChangeStatus.modified


def _parse_porcelain(raw: bytes, packs_path: str) -> list[FileChange]:
    """`status --porcelain=v1 -z --no-renames`: `XY path\0`."""
    changes: list[FileChange] = []
    for entry in raw.decode("utf-8", errors="replace").split("\0"):
        if len(entry) < 4:  # noqa: PLR2004
            continue
        rel = _rel(entry[3:], packs_path)
        if rel:
            changes.append(FileChange(rel, _status_of(entry[:2])))
    return changes


def _parse_name_status(raw: bytes, packs_path: str) -> list[FileChange]:
    """`diff --name-status -z --no-renames`: `S\0path\0`."""
    parts = raw.decode("utf-8", errors="replace").split("\0")
    changes: list[FileChange] = []
    for code, name in zip(parts[::2], parts[1::2], strict=False):
        rel = _rel(name, packs_path)
        if code and rel:
            changes.append(FileChange(rel, _status_of(code)))
    return changes


def _branch(name: str) -> str:
    try:
        return validate_ref_name(name)
    except VcsInvalidRefError:
        raise git_error(GitErrorCode.branch_missing) from None


def _config_url(target: RemoteTarget) -> str:
    """Адрес для ленивой подгрузки блобов. https без `.git` получает суффикс, как в запускателе: с токеном редиректы
    выключены, а GitLab перенаправляет `<repo>/info/refs` на `<repo>.git/info/refs`."""
    url = target.url.display_url
    if target.url.kind in (RemoteKind.https, RemoteKind.http) and not url.endswith(".git"):
        return f"{url}.git"
    return url


def _store_config(target: RemoteTarget, packs_path: str) -> list[tuple[str, str]]:
    entries = [
        ("core.repositoryformatversion", "1"),
        ("core.symlinks", "false"),
        ("core.protectNTFS", "true"),
        ("core.protectHFS", "true"),
        ("core.fsmonitor", "false"),
        ("core.quotepath", "false"),
        ("gc.auto", "0"),
        ("maintenance.auto", "false"),
        ("fetch.recurseSubmodules", "false"),
        ("submodule.recurse", "false"),
        ("remote.origin.url", _config_url(target)),
        ("remote.origin.promisor", "true"),
        ("remote.origin.partialclonefilter", "blob:none"),
        ("extensions.partialClone", _REMOTE),
    ]
    if packs_path != ".":
        entries += [("core.sparseCheckout", "true"), ("core.sparseCheckoutCone", "false")]
    return entries


class PackWorkspaceGit:
    def __init__(self, runner: IGitRemoteRunner, config: GitConfig) -> None:
        self._runner = runner
        self._config = config

    async def clone(
        self, dirs: WorkspaceDirs, target: RemoteTarget, *, branch: str, packs_path: str, limits: WorkspaceLimits
    ) -> str:
        branch = _branch(branch)
        await asyncio.to_thread(self._fresh_dirs, dirs)
        await self._runner.run_local(
            ["init", "--bare", "--quiet", f"--initial-branch={branch}", str(dirs.git)],
            git_dir=None,
            timeout_s=_LOCAL_TIMEOUT_S,
        )
        for key, value in _store_config(target, packs_path):
            await self._local(dirs, ["config", key, value])
        if packs_path != ".":
            # Шаблон разреженной выборки без конуса: только папка паков, без файлов корня репозитория.
            info = dirs.git / "info"
            info.mkdir(exist_ok=True)
            (info / "sparse-checkout").write_text(f"/{packs_path}/\n", encoding="utf-8")
        await self._fetch(dirs, target, branch, timeout_s=self._config.clone_timeout_s)
        await self._check_store_size(dirs, limits)
        # Блобы папки паков приходят здесь, одной пачкой: checkout в частичном клоне подгружает недостающее сам.
        await self._runner.run(
            [
                "--work-tree",
                str(dirs.tree),
                "checkout",
                "--quiet",
                "--detach",
                "--no-recurse-submodules",
                remote_ref(branch),
            ],
            op=GitOp.clone,
            git_dir=dirs.git,
            target=target,
            timeout_s=self._config.clone_timeout_s,
        )
        return await self._tip(dirs, branch)

    async def fetch(self, dirs: WorkspaceDirs, target: RemoteTarget, *, branch: str, limits: WorkspaceLimits) -> str:
        branch = _branch(branch)
        await self._fetch(dirs, target, branch, timeout_s=self._config.fetch_timeout_s)
        await self._check_store_size(dirs, limits)
        return await self._tip(dirs, branch)

    async def released(
        self, dirs: WorkspaceDirs, target: RemoteTarget, *, branch: str, packs_path: str
    ) -> ReleasedVersions:
        branch = _branch(branch)
        ref = remote_ref(branch)
        listing = await self._local(
            dirs, ["ls-tree", "-r", "--name-only", "-z", ref, *(["--", packs_path] if packs_path != "." else [])]
        )
        prefix = "" if packs_path == "." else f"{packs_path}/"
        templates: dict[str, dict[str, str]] = {}
        for name in listing.decode("utf-8", errors="replace").split("\0"):
            rel = name[len(prefix) :] if name.startswith(prefix) else None
            if not rel or not is_registry_path(rel):
                continue
            text = await self._registry_text(dirs, target, f"{ref}:{name}")
            if text is None:
                continue
            pack, _, template, _ = rel.split("/")
            try:
                entries = parse_releases(text)
            except yaml.YAMLError:
                entries = {}  # битый реестр базы: как отсутствующий, линтер ветки покажет ошибку
            templates[template_key(pack, template)] = {v: e.digest for v, e in entries.items()}
        return ReleasedVersions(templates=templates, sha=await self._tip(dirs, branch))

    # ── срез T6: ветка, коммит, отправка, слияние базы ──

    async def status(self, dirs: WorkspaceDirs, *, base_branch: str, packs_path: str) -> WorkGitStatus:
        base = remote_ref(_branch(base_branch))
        head = (await self._local(dirs, ["rev-parse", "--verify", "HEAD^{commit}"])).decode("ascii").strip()
        branch_out = await self._runner.run_local(
            ["symbolic-ref", "--quiet", "--short", "HEAD"], git_dir=dirs.git, timeout_s=_LOCAL_TIMEOUT_S, check=False
        )
        branch = branch_out.stdout.decode("utf-8", errors="replace").strip() if branch_out.returncode == 0 else None
        porcelain = await self._local(
            dirs,
            [
                *self._tree(dirs),
                "status",
                "--porcelain=v1",
                "-z",
                "--untracked-files=all",
                "--no-renames",
                *_scope(packs_path),
            ],
        )
        uncommitted = _parse_porcelain(porcelain, packs_path)
        against_base = await self._local(
            dirs, [*self._tree(dirs), "diff", "--name-status", "-z", "--no-renames", base, *_scope(packs_path)]
        )
        changed = {c.path: c for c in _parse_name_status(against_base, packs_path)}
        for change in uncommitted:
            if change.status is ChangeStatus.added:
                changed.setdefault(change.path, change)
        counts = (await self._local(dirs, ["rev-list", "--left-right", "--count", f"{base}...HEAD"])).decode().split()
        behind, ahead = (int(counts[0]), int(counts[1])) if len(counts) == 2 else (0, 0)  # noqa: PLR2004
        return WorkGitStatus(
            head_sha=head,
            branch=branch,
            uncommitted=tuple(sorted(uncommitted, key=lambda c: c.path)),
            changed=tuple(sorted(changed.values(), key=lambda c: c.path)),
            ahead=ahead,
            behind=behind,
        )

    async def local_branches(self, dirs: WorkspaceDirs) -> tuple[str, ...]:
        out = await self._local(dirs, ["for-each-ref", "--format=%(refname:short)", "refs/heads/"])
        return tuple(line for line in out.decode("utf-8", errors="replace").splitlines() if line)

    async def create_branch(self, dirs: WorkspaceDirs, *, name: str) -> None:
        name = _branch(name)
        # Пустое старое значение: ветка создаётся, только если её ещё нет. Дерево и индекс не трогаются.
        await self._local(dirs, ["update-ref", f"refs/heads/{name}", "HEAD", ""])
        await self._local(dirs, ["symbolic-ref", "HEAD", f"refs/heads/{name}"])

    async def switch_branch(self, dirs: WorkspaceDirs, target: RemoteTarget, *, name: str, fetch: bool) -> str:
        name = _branch(name)
        if fetch:
            await self._fetch(dirs, target, name, timeout_s=self._config.fetch_timeout_s)
            await self._local(dirs, ["update-ref", f"refs/heads/{name}", remote_ref(name), ""])
        # Блобы ветки внутри папки паков подгружаются здесь же: команда с сетью.
        await self._runner.run(
            [*self._tree(dirs), "checkout", "--quiet", "--no-recurse-submodules", name],
            op=GitOp.fetch,
            git_dir=dirs.git,
            target=target,
            timeout_s=self._config.fetch_timeout_s,
        )
        return await self._head(dirs)

    async def commit(self, dirs: WorkspaceDirs, *, packs_path: str, message: str, author: VcsAuthor) -> str | None:
        await self._local(dirs, [*self._tree(dirs), "add", "-A", *_scope(packs_path)])
        staged = await self._runner.run_local(
            [*self._tree(dirs), "diff", "--cached", "--quiet"],
            git_dir=dirs.git,
            timeout_s=_LOCAL_TIMEOUT_S,
            check=False,
        )
        if staged.returncode == 0:
            return None
        await self._local(
            dirs, [*_author_config(author), *self._tree(dirs), "commit", "--quiet", "--no-verify", "-m", message]
        )
        return await self._head(dirs)

    async def push(
        self,
        dirs: WorkspaceDirs,
        target: RemoteTarget,
        *,
        branch: str,
        push_options: Sequence[str] = (),
    ) -> PushOutcome:
        branch = _branch(branch)
        options = [part for option in push_options for part in ("-o", option)]
        result = await self._runner.run(
            [
                "push",
                "--porcelain",
                "--no-recurse-submodules",
                *options,
                "--",
                target.url.display_url,
                f"HEAD:refs/heads/{branch}",
            ],
            op=GitOp.push,
            git_dir=dirs.git,
            target=target,
            timeout_s=self._config.push_timeout_s,
        )
        return PushOutcome(sha=await self._head(dirs), remote_output=result.stderr)

    async def merge_base(
        self, dirs: WorkspaceDirs, target: RemoteTarget, *, base_branch: str, author: VcsAuthor, message: str
    ) -> MergeOutcome:
        base = remote_ref(_branch(base_branch))
        contained = await self._runner.run_local(
            ["merge-base", "--is-ancestor", base, "HEAD"], git_dir=dirs.git, timeout_s=_LOCAL_TIMEOUT_S, check=False
        )
        if contained.returncode == 0:
            return MergeOutcome(sha=await self._head(dirs), merged=False)
        try:
            await self._runner.run(
                [*_author_config(author), *self._tree(dirs), "merge", "--no-edit", "--no-verify", "-m", message, base],
                op=GitOp.fetch,
                git_dir=dirs.git,
                target=target,
                timeout_s=self._config.fetch_timeout_s,
            )
        except GitSyncError:
            unmerged = await self._runner.run_local(
                [*self._tree(dirs), "diff", "--name-only", "-z", "--diff-filter=U"],
                git_dir=dirs.git,
                timeout_s=_LOCAL_TIMEOUT_S,
                check=False,
            )
            conflicts = tuple(name for name in unmerged.stdout.decode("utf-8", errors="replace").split("\0") if name)
            await self._runner.run_local(
                [*self._tree(dirs), "merge", "--abort"], git_dir=dirs.git, timeout_s=_LOCAL_TIMEOUT_S, check=False
            )
            if not conflicts:
                raise
            return MergeOutcome(sha=await self._head(dirs), merged=False, conflicts=conflicts)
        return MergeOutcome(sha=await self._head(dirs), merged=True)

    async def reset_to_base(self, dirs: WorkspaceDirs, target: RemoteTarget, *, base_branch: str) -> str:
        base = remote_ref(_branch(base_branch))
        await self._runner.run(
            [*self._tree(dirs), "checkout", "--quiet", "--force", "--detach", "--no-recurse-submodules", base],
            op=GitOp.fetch,
            git_dir=dirs.git,
            target=target,
            timeout_s=self._config.fetch_timeout_s,
        )
        # Новые файлы, которых нет в базе, checkout не убирает.
        await self._local(dirs, [*self._tree(dirs), "clean", "-fdq", "--", "."])
        return await self._head(dirs)

    async def base_registries(
        self, dirs: WorkspaceDirs, target: RemoteTarget, *, base_branch: str, paths: Sequence[str]
    ) -> dict[str, str]:
        ref = remote_ref(_branch(base_branch))
        texts: dict[str, str] = {}
        for path in paths:
            listed = await self._local(dirs, ["ls-tree", "-z", "--name-only", ref, "--", path])
            if not listed.strip(b"\0"):
                continue
            text = await self._registry_text(dirs, target, f"{ref}:{path}")
            if text is not None:
                texts[path] = text
        return texts

    async def diff(
        self, dirs: WorkspaceDirs, target: RemoteTarget, *, base_branch: str, packs_path: str, max_bytes: int
    ) -> tuple[str, bool]:
        base = remote_ref(_branch(base_branch))
        # Новые файлы попадают в diff как «намерение добавить»: следующий коммит всё равно берёт их целиком.
        untracked = await self._local(
            dirs, [*self._tree(dirs), "ls-files", "-z", "--others", "--exclude-standard", *_scope(packs_path)]
        )
        names = [name for name in untracked.decode("utf-8", errors="replace").split("\0") if name]
        if names:
            await self._local(dirs, [*self._tree(dirs), "add", "--intent-to-add", "--", *names])
        result = await self._runner.run(
            [*self._tree(dirs), "diff", "--no-color", "--no-ext-diff", "--no-textconv", base, *_scope(packs_path)],
            op=GitOp.fetch,
            git_dir=dirs.git,
            target=target,
            timeout_s=self._config.fetch_timeout_s,
        )
        raw = result.stdout
        truncated = len(raw) > max_bytes
        return raw[:max_bytes].decode("utf-8", errors="replace"), truncated

    async def branch_paths(self, dirs: WorkspaceDirs, *, base_branch: str) -> tuple[str, ...]:
        base = remote_ref(_branch(base_branch))
        # Три точки: от точки расхождения с базой, поэтому слитая в ветку база (merge-base) сюда не попадает.
        # Нужны только деревья, блобы частичного клона не подгружаются.
        raw = await self._local(dirs, ["diff", "--name-only", "-z", "--no-renames", f"{base}...HEAD"])
        return tuple(name for name in raw.decode("utf-8", errors="replace").split("\0") if name)

    @staticmethod
    def _tree(dirs: WorkspaceDirs) -> list[str]:
        return ["--work-tree", str(dirs.tree)]

    async def _head(self, dirs: WorkspaceDirs) -> str:
        return (await self._local(dirs, ["rev-parse", "--verify", "HEAD^{commit}"])).decode("ascii").strip()

    async def _registry_text(self, dirs: WorkspaceDirs, target: RemoteTarget, spec: str) -> str | None:
        # Размер спрашивается с сетью: блоба новой вершины базы в частичном клоне может ещё не быть.
        sized = await self._runner.run(
            ["cat-file", "-s", spec], op=GitOp.fetch, git_dir=dirs.git, target=target, timeout_s=_LOCAL_TIMEOUT_S
        )
        try:
            size = int(sized.stdout.decode("ascii", errors="replace").strip())
        except ValueError:
            return None
        if size > _REGISTRY_MAX_BYTES:
            return None
        blob = await self._local(dirs, ["cat-file", "blob", spec])
        return blob.decode("utf-8", errors="replace")

    async def _fetch(self, dirs: WorkspaceDirs, target: RemoteTarget, branch: str, *, timeout_s: float) -> None:
        await self._runner.run(
            [
                "fetch",
                "--filter=blob:none",
                "--no-tags",
                "--no-recurse-submodules",
                "--no-write-fetch-head",
                "--progress",
                "--",
                _REMOTE,
                f"+refs/heads/{branch}:{remote_ref(branch)}",
            ],
            op=GitOp.fetch,
            git_dir=dirs.git,
            target=target,
            timeout_s=timeout_s,
        )

    async def _check_store_size(self, dirs: WorkspaceDirs, limits: WorkspaceLimits) -> None:
        out = (await self._local(dirs, ["count-objects", "-v"])).decode("ascii", errors="replace")
        kib = 0
        for line in out.splitlines():
            key, _, value = line.partition(":")
            if key.strip() in {"size", "size-pack"}:
                kib += int(value.strip() or 0)
        if kib * _KIB > limits.max_clone_bytes:
            raise PackStudioError(PackStudioErrorCode.workspace_too_large)

    async def _tip(self, dirs: WorkspaceDirs, branch: str) -> str:
        out = await self._local(dirs, ["rev-parse", "--verify", "--quiet", f"{remote_ref(branch)}^{{commit}}"])
        return out.decode("ascii", errors="replace").strip()

    async def _local(self, dirs: WorkspaceDirs, args: list[str]) -> bytes:
        result = await self._runner.run_local(args, git_dir=dirs.git, timeout_s=_LOCAL_TIMEOUT_S)
        return result.stdout

    @staticmethod
    def _fresh_dirs(dirs: WorkspaceDirs) -> None:
        """Клон с нуля: прежнее хранилище и дерево (неудачная попытка) убираются, папка самого пространства остаётся."""
        dirs.root.mkdir(parents=True, exist_ok=True)
        for folder in (dirs.git, dirs.tree):
            if folder.is_symlink() or folder.is_file():
                folder.unlink()
            elif folder.exists():
                shutil.rmtree(folder)
        dirs.tree.mkdir()


def workspace_dirs(root: Path) -> WorkspaceDirs:
    return WorkspaceDirs(root=root, git=root / "git", tree=root / "tree")
