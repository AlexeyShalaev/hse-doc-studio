"""Ревизия источника каталога во временной папке (порт IRevisionStager, template-studio.md, 10.3 и раздел 9).

- git: пустое хранилище с той же закалкой, что клоны Студии шаблонов (`core.symlinks=false`, без подмодулей и
  фоновой сборки мусора; хуки, fsmonitor и помощники учётных данных выключает запускатель), неглубокая выборка без
  блобов одной ревизии (тег, ветка или sha; по умолчанию HEAD сервера), разреженное дерево только с папкой паков.
  Сеть, токены, egress и доверие к хостам идут через `IGitRemoteRunner` синхронизации проектов.
- архив (.zip, .tar.gz): распаковка вручную по записям, без `extractall`. Ссылки, устройства, абсолютные пути,
  `..` и обратные косые отвергаются целиком (`archive_unsafe`); число файлов и байты считаются по факту чтения,
  а не по заявленным в архиве размерам.
- папка (локально): снимок копией, ссылки отвергаются, `.git` пропускается.

После раскладки дерево паков ещё раз проверяется: ссылок нет, файлов и байт не больше предела.
"""

from __future__ import annotations

import asyncio
import hashlib
import shutil
import stat
import tarfile
import zipfile
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import IO

from hse_doc_studio.api.config import GitConfig
from hse_doc_studio.core.git_sync.entities import RemoteTarget
from hse_doc_studio.core.git_sync.error_classifier import GitOp
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.policy import GitSyncPolicy
from hse_doc_studio.core.git_sync.protocols import IGitRemoteRunner
from hse_doc_studio.core.git_sync.url import RemoteKind, parse_remote_url
from hse_doc_studio.core.pack_catalog.entities import CatalogSource, SourceKind
from hse_doc_studio.core.pack_catalog.errors import CatalogError, CatalogErrorCode
from hse_doc_studio.core.pack_catalog.protocols import IArchiveStore, StagedRevision, StageLimits

_LOCAL_TIMEOUT_S = 60.0
_REMOTE = "origin"
_HEAD_REF = "refs/catalog/head"
_CHUNK = 1 << 20
_KIB = 1024
_SHA_RE_LEN = (7, 40, 64)
_SKIP_DIRS = frozenset({".git", "__pycache__", "node_modules"})
_JUNK = frozenset({".DS_Store", "Thumbs.db", "desktop.ini"})
_PACK_MANIFEST = "pack.yaml"
# Обёрточные папки архива (`repo-main/`, `packs/`): сколько уровней снимается в поисках паков.
_UNWRAP_DEPTH = 2


def target_of(source: CatalogSource, policy: GitSyncPolicy) -> RemoteTarget:
    url = parse_remote_url(
        source.url or "", allow_http=policy.allow_insecure_http, allow_local=policy.allow_local_remotes
    )
    return RemoteTarget(
        url=url, credential_id=source.credential_id or source.service_access_id, insecure_http=source.insecure_http
    )


def _is_sha(ref: str) -> bool:
    return len(ref) in range(_SHA_RE_LEN[0], _SHA_RE_LEN[2] + 1) and all(c in "0123456789abcdef" for c in ref.lower())


def ref_candidates(ref: str | None) -> list[str]:
    """Как искать ревизию: тег, потом ветка, потом sha (полный: сервер отдаёт коммит по sha только целиком)."""
    if not ref:
        return [f"+HEAD:{_HEAD_REF}"]
    found = [f"+refs/tags/{ref}:{_HEAD_REF}", f"+refs/heads/{ref}:{_HEAD_REF}"]
    if _is_sha(ref) and len(ref) in _SHA_RE_LEN[1:]:
        found.append(f"+{ref.lower()}:{_HEAD_REF}")
    return found


def _config_url(target: RemoteTarget) -> str:
    url = target.url.display_url
    if target.url.kind in (RemoteKind.https, RemoteKind.http) and not url.endswith(".git"):
        return f"{url}.git"
    return url


def _fresh(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)


def _safe_member(name: str) -> PurePosixPath | None:
    """Путь записи архива внутри папки распаковки; None: запись выходит за неё или неприлична."""
    if not name or "\\" in name or "\0" in name or name.startswith("/") or (len(name) > 1 and name[1] == ":"):
        return None
    path = PurePosixPath(name)
    parts = [p for p in path.parts if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts):
        return None
    return PurePosixPath(*parts)


class _Budget:
    def __init__(self, limits: StageLimits) -> None:
        self._limits = limits
        self.files = 0
        self.bytes = 0

    def file(self) -> None:
        self.files += 1
        if self.files > self._limits.max_files:
            raise CatalogError(CatalogErrorCode.tree_too_large, files=self.files)

    def add(self, size: int) -> None:
        self.bytes += size
        if self.bytes > self._limits.max_bytes:
            raise CatalogError(CatalogErrorCode.tree_too_large, bytes=self.bytes)


def _copy_stream(src: IO[bytes], dest: Path, budget: _Budget) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as out:
        while chunk := src.read(_CHUNK):
            budget.add(len(chunk))
            out.write(chunk)


def extract_zip(archive: Path, dest: Path, limits: StageLimits) -> None:
    budget = _Budget(limits)
    try:
        with zipfile.ZipFile(archive) as zf:
            members = zf.infolist()
            for info in members:
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode) or _safe_member(info.filename) is None:
                    raise CatalogError(CatalogErrorCode.archive_unsafe, member=info.filename[:200])
            for info in members:
                rel = _safe_member(info.filename)
                if rel is None:
                    continue
                target = dest / rel
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                budget.file()
                with zf.open(info) as src:
                    _copy_stream(src, target, budget)
    except (zipfile.BadZipFile, zipfile.LargeZipFile, NotImplementedError, OSError, EOFError) as exc:
        raise CatalogError(CatalogErrorCode.archive_invalid, reason=str(exc)[:200]) from exc


def extract_tar(archive: Path, dest: Path, limits: StageLimits) -> None:
    budget = _Budget(limits)
    try:
        with tarfile.open(archive, mode="r:*") as tf:
            members = tf.getmembers()
            for member in members:
                if not (member.isfile() or member.isdir()) or _safe_member(member.name) is None:
                    raise CatalogError(CatalogErrorCode.archive_unsafe, member=member.name[:200])
            for member in members:
                _extract_member(tf, member, dest, budget)
    except (tarfile.TarError, OSError, EOFError) as exc:
        raise CatalogError(CatalogErrorCode.archive_invalid, reason=str(exc)[:200]) from exc


def _extract_member(tf: tarfile.TarFile, member: tarfile.TarInfo, dest: Path, budget: _Budget) -> None:
    rel = _safe_member(member.name)
    if rel is None:
        return
    target = dest / rel
    if member.isdir():
        target.mkdir(parents=True, exist_ok=True)
        return
    budget.file()
    src = tf.extractfile(member)
    if src is None:
        raise CatalogError(CatalogErrorCode.archive_invalid, member=member.name[:200])
    with src:
        _copy_stream(src, target, budget)


def _walk(root: Path) -> Iterator[Path]:
    for path in sorted(root.iterdir()):
        if path.name in _SKIP_DIRS and path.is_dir() and not path.is_symlink():
            continue
        yield path
        if path.is_dir() and not path.is_symlink():
            yield from _walk(path)


def check_tree(root: Path, limits: StageLimits) -> None:
    """Дерево паков ревизии: ни одной ссылки, файлов и байт не больше предела."""
    budget = _Budget(limits)
    for path in _walk(root):
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise CatalogError(CatalogErrorCode.tree_unsafe, path=path.relative_to(root).as_posix()[:200])
        if stat.S_ISREG(mode):
            budget.file()
            budget.add(path.lstat().st_size)


def tree_digest(root: Path) -> str:
    """Хеш снимка папки: пути и содержимое файлов. Ревизия источника-папки."""
    outer = hashlib.sha256()
    for path in _walk(root):
        if path.is_file() and not path.is_symlink() and path.name not in _JUNK:
            inner = hashlib.sha256(path.read_bytes()).hexdigest()
            outer.update(f"{path.relative_to(root).as_posix()}\0{inner}\n".encode())
    return outer.hexdigest()


def _copy_folder(src: Path, dest: Path, limits: StageLimits) -> None:
    budget = _Budget(limits)
    for path in _walk(src):
        rel = path.relative_to(src)
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise CatalogError(CatalogErrorCode.tree_unsafe, path=rel.as_posix()[:200])
        target = dest / rel
        if stat.S_ISDIR(mode):
            target.mkdir(parents=True, exist_ok=True)
        elif stat.S_ISREG(mode):
            budget.file()
            budget.add(path.lstat().st_size)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target, follow_symlinks=False)


def _has_packs(root: Path) -> bool:
    return any(child.is_dir() and (child / _PACK_MANIFEST).is_file() for child in root.iterdir())


def packs_root(base: Path, packs_path: str) -> Path:
    """Корень паков в разложенной ревизии. `.`: сам корень, а у архива с обёрточной папкой (`repo-main/`) или с
    папкой `packs/` внутри она сама находится."""
    if packs_path != ".":
        root = base / packs_path
        if not root.is_dir() or root.is_symlink():
            raise CatalogError(CatalogErrorCode.packs_path_missing, packs_path=packs_path)
        return root
    root = base
    for _ in range(_UNWRAP_DEPTH + 1):
        if _has_packs(root):
            return root
        if (root / "packs").is_dir() and _has_packs(root / "packs"):
            return root / "packs"
        children = [c for c in root.iterdir() if c.name not in _JUNK]
        if len(children) != 1 or not children[0].is_dir():
            break
        root = children[0]
    return base


class RevisionStager:
    def __init__(
        self,
        runner: IGitRemoteRunner,
        config: GitConfig,
        policy: GitSyncPolicy,
        archives: IArchiveStore,
    ) -> None:
        self._runner = runner
        self._config = config
        self._policy = policy
        self._archives = archives

    async def stage(self, source: CatalogSource, dest: Path, limits: StageLimits) -> StagedRevision:
        await asyncio.to_thread(_fresh, dest)
        if source.kind is SourceKind.git:
            revision, root = await self._stage_git(source, dest, limits)
        elif source.kind is SourceKind.archive:
            revision, root = await asyncio.to_thread(self._stage_archive, source, dest, limits)
        else:
            revision, root = await asyncio.to_thread(self._stage_folder, source, dest, limits)
        await asyncio.to_thread(check_tree, root, limits)
        return StagedRevision(revision=revision, root=root)

    # ── git ──────────────────────────────────────────────────────────────────

    async def _stage_git(self, source: CatalogSource, dest: Path, limits: StageLimits) -> tuple[str, Path]:
        target = target_of(source, self._policy)
        git_dir, tree = dest / "git", dest / "tree"
        tree.mkdir()
        await self._runner.run_local(
            ["init", "--bare", "--quiet", str(git_dir)], git_dir=None, timeout_s=_LOCAL_TIMEOUT_S
        )
        for key, value in self._store_config(target, source.packs_path):
            await self._local(git_dir, ["config", key, value])
        if source.packs_path != ".":
            info = git_dir / "info"
            info.mkdir(exist_ok=True)
            (info / "sparse-checkout").write_text(f"/{source.packs_path}/\n", encoding="utf-8")
        await self._fetch_ref(git_dir, target, source.ref)
        await self._check_size(git_dir, limits)
        await self._runner.run(
            ["--work-tree", str(tree), "checkout", "--quiet", "--detach", "--no-recurse-submodules", _HEAD_REF],
            op=GitOp.clone,
            git_dir=git_dir,
            target=target,
            timeout_s=self._config.clone_timeout_s,
        )
        sha = (await self._local(git_dir, ["rev-parse", "--verify", f"{_HEAD_REF}^{{commit}}"])).decode().strip()
        return sha, await asyncio.to_thread(packs_root, tree, source.packs_path)

    async def _fetch_ref(self, git_dir: Path, target: RemoteTarget, ref: str | None) -> None:
        last: GitSyncError | None = None
        for refspec in ref_candidates(ref):
            try:
                await self._runner.run(
                    [
                        "fetch",
                        "--depth=1",
                        "--filter=blob:none",
                        "--no-tags",
                        "--no-recurse-submodules",
                        "--no-write-fetch-head",
                        "--",
                        _REMOTE,
                        refspec,
                    ],
                    op=GitOp.fetch,
                    git_dir=git_dir,
                    target=target,
                    timeout_s=self._config.fetch_timeout_s,
                )
            except GitSyncError as exc:
                last = exc
                if exc.code not in (GitErrorCode.branch_missing, GitErrorCode.git_error) and ref is not None:
                    raise
                continue
            return
        if ref is not None:
            raise CatalogError(CatalogErrorCode.ref_not_found, ref=ref)
        assert last is not None  # noqa: S101 — без ref кандидат один, и он упал
        raise last

    @staticmethod
    def _store_config(target: RemoteTarget, packs_path: str) -> list[tuple[str, str]]:
        entries = [
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
            ("core.repositoryformatversion", "1"),
            ("extensions.partialClone", _REMOTE),
        ]
        if packs_path != ".":
            entries += [("core.sparseCheckout", "true"), ("core.sparseCheckoutCone", "false")]
        return entries

    async def _check_size(self, git_dir: Path, limits: StageLimits) -> None:
        out = (await self._local(git_dir, ["count-objects", "-v"])).decode("ascii", errors="replace")
        kib = sum(
            int(value.strip() or 0)
            for key, _, value in (line.partition(":") for line in out.splitlines())
            if key.strip() in {"size", "size-pack"}
        )
        if kib * _KIB > limits.max_archive_bytes:
            raise CatalogError(CatalogErrorCode.tree_too_large, bytes=kib * _KIB)

    async def _local(self, git_dir: Path, args: list[str]) -> bytes:
        return (await self._runner.run_local(args, git_dir=git_dir, timeout_s=_LOCAL_TIMEOUT_S)).stdout

    # ── архив и папка ────────────────────────────────────────────────────────

    def _stage_archive(self, source: CatalogSource, dest: Path, limits: StageLimits) -> tuple[str, Path]:
        archive = self._archives.path(source.archive_digest or "") if source.archive_digest else None
        if archive is None:
            raise CatalogError(CatalogErrorCode.archive_missing)
        unpacked = dest / "unpacked"
        unpacked.mkdir()
        if zipfile.is_zipfile(archive):
            extract_zip(archive, unpacked, limits)
        else:
            extract_tar(archive, unpacked, limits)
        return source.archive_digest or "", packs_root(unpacked, source.packs_path)

    def _stage_folder(self, source: CatalogSource, dest: Path, limits: StageLimits) -> tuple[str, Path]:
        folder = Path(source.folder or "")
        src = folder if source.packs_path == "." else folder / source.packs_path
        if not folder.is_absolute() or not src.is_dir() or src.is_symlink():
            raise CatalogError(CatalogErrorCode.folder_unavailable)
        tree = dest / "tree"
        tree.mkdir()
        _copy_folder(src, tree, limits)
        return tree_digest(tree), tree
