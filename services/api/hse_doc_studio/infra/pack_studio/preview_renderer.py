"""Рендер предпросмотра в песочнице (порт IPackPreviewRenderer, docs/design/template-studio.md, 6.3 и раздел 9).

Разбор манифестов и рендер шаблонов чужого пака идут в отдельном процессе (`call_isolated`: spawn, предел времени
и памяти) над копией пака без ссылок. В процессе api остаётся только чтение байт файлов для дайджестов ключа кэша.
"""

from __future__ import annotations

import asyncio
import hashlib
import shutil
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.paths import PACK_MANIFEST, TEMPLATE_MANIFEST, VersionRef, validate_rel_path
from hse_doc_studio.core.pack_studio.preview import (
    MaterializedDoc,
    MaterializeRequest,
    PreviewInputs,
    PreviewRenderError,
    VersionDescription,
)
from hse_doc_studio.infra.pack_studio.preview_worker import (
    EXAMPLES_DIR,
    StageLimits,
    VersionDirs,
    describe_version,
    materialize_preview,
    regular_files,
)
from hse_doc_studio.infra.template.jinja_sandbox import IsolatedRenderError, IsolationLimits, call_isolated

_HASH_CHUNK = 1 << 20


@dataclass(frozen=True)
class PreviewRenderLimits:
    describe_timeout_s: float
    materialize_timeout_s: float
    memory_bytes: int
    stage: StageLimits


class PackPreviewRenderer:
    def __init__(self, tmp_dir: Path, limits: PreviewRenderLimits) -> None:
        self._tmp_dir = tmp_dir
        self._limits = limits

    async def inputs(self, root: Path, ref: VersionRef) -> PreviewInputs:
        return await asyncio.to_thread(self._inputs, _dirs(root, ref))

    async def describe(self, root: Path, ref: VersionRef) -> VersionDescription:
        dirs = _dirs(root, ref)
        limits = IsolationLimits(
            timeout_seconds=self._limits.describe_timeout_s, memory_bytes=self._limits.memory_bytes
        )
        try:
            return await asyncio.to_thread(self._isolated, describe_version, dirs, limits)
        except IsolatedRenderError as exc:
            raise PackStudioError(PackStudioErrorCode.version_unreadable, reason=str(exc)) from exc

    async def describe_files(self, files: Mapping[str, bytes], ref: VersionRef) -> VersionDescription:
        self._tmp_dir.mkdir(parents=True, exist_ok=True)
        root = Path(await asyncio.to_thread(tempfile.mkdtemp, prefix="rev-", dir=self._tmp_dir))
        try:
            await asyncio.to_thread(_write_files, root, files)
            return await self.describe(root, ref)
        finally:
            await asyncio.to_thread(shutil.rmtree, root, ignore_errors=True)

    async def materialize(
        self, root: Path, ref: VersionRef, request: MaterializeRequest, dest: Path
    ) -> MaterializedDoc:
        dirs = _dirs(root, ref)
        limits = IsolationLimits(
            timeout_seconds=self._limits.materialize_timeout_s, memory_bytes=self._limits.memory_bytes
        )
        try:
            return await asyncio.to_thread(self._isolated, materialize_preview, dirs, limits, request, str(dest))
        except IsolatedRenderError as exc:
            raise PreviewRenderError(str(exc)) from exc

    def _isolated[T](self, target: Callable[..., T], dirs: VersionDirs, limits: IsolationLimits, *extra: object) -> T:
        """Вызов в отдельном процессе со своей временной папкой копии пака, которая убирается после."""
        self._tmp_dir.mkdir(parents=True, exist_ok=True)
        stage = tempfile.mkdtemp(prefix="stage-", dir=self._tmp_dir)
        try:
            return call_isolated(target, (dirs, stage, self._limits.stage, *extra), limits=limits)
        finally:
            shutil.rmtree(stage, ignore_errors=True)

    def _inputs(self, dirs: VersionDirs) -> PreviewInputs:
        if not dirs.version_dir.is_dir() or dirs.version_dir.is_symlink():
            raise PackStudioError(PackStudioErrorCode.file_not_found, path=_ref_dir(dirs))
        budget = self._limits.stage
        files: dict[str, str] = {}
        total = 0
        for rel, full, size in regular_files(dirs.version_dir):
            total += size
            if total > budget.max_bytes or len(files) >= budget.max_files:
                raise PackStudioError(PackStudioErrorCode.workspace_too_large)
            files[rel] = _sha256(full)
        extra = tuple(
            f"{name}:{_sha256(path)}"
            for name, path in (
                (PACK_MANIFEST, dirs.pack_dir / PACK_MANIFEST),
                (TEMPLATE_MANIFEST, dirs.template_dir / TEMPLATE_MANIFEST),
            )
            if path.is_file() and not path.is_symlink()
        )
        examples = dirs.template_dir / EXAMPLES_DIR
        example_hashes = (
            [f"{rel}:{_sha256(full)}" for rel, full, _ in regular_files(examples)]
            if examples.is_dir() and not examples.is_symlink()
            else []
        )
        tree = hashlib.sha256()
        for line in (*(f"{k}:{v}" for k, v in sorted(files.items())), *extra, *example_hashes):
            tree.update(line.encode() + b"\n")
        return PreviewInputs(files=files, extra=extra, tree=tree.hexdigest())


def _write_files(root: Path, files: Mapping[str, bytes]) -> None:
    """Файлы из git (пути от папки паков) во временную папку. Имя, которое не проходит проверку путей, пропускается:
    за пределы папки файл выйти не может."""
    for rel, data in files.items():
        try:
            safe = validate_rel_path(rel)
        except PackStudioError:
            continue
        target = root / safe
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def _dirs(root: Path, ref: VersionRef) -> VersionDirs:
    return VersionDirs(str(root), ref.pack, ref.template, ref.version)


def _ref_dir(dirs: VersionDirs) -> str:
    return f"{dirs.pack}/templates/{dirs.template}/versions/{dirs.version}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_HASH_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()
