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
from pathlib import Path

import yaml

from hse_doc_studio.api.config import GitConfig
from hse_doc_studio.core.git_sync.entities import RemoteTarget
from hse_doc_studio.core.git_sync.error_classifier import GitOp
from hse_doc_studio.core.git_sync.error_messages import git_error
from hse_doc_studio.core.git_sync.errors import GitErrorCode
from hse_doc_studio.core.git_sync.protocols import IGitRemoteRunner
from hse_doc_studio.core.git_sync.url import RemoteKind
from hse_doc_studio.core.pack_studio.entities import ReleasedVersions
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.paths import is_registry_path, template_key
from hse_doc_studio.core.pack_studio.protocols import WorkspaceDirs, WorkspaceLimits
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
