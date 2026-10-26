from __future__ import annotations

import contextlib
import hashlib
import os
import uuid
from pathlib import Path

from hse_doc_studio.core.jobs.files import ArtifactRef, validate_relative_posix

_CHUNK = 1024 * 1024


class LocalJobOutputs:
    """Выходы задач на локальном диске: файл появляется целиком или не появляется."""

    def write_output(self, workspace: Path, rel_path: str, data: bytes) -> ArtifactRef:
        target = self._contained(workspace, rel_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Короткое имя не зависит от имени цели: длинное имя PDF не должно упираться в NAME_MAX.
        tmp = target.with_name(f".tmp-{uuid.uuid4().hex[:12]}")
        try:
            tmp.write_bytes(data)
            os.replace(tmp, target)
        except OSError as exc:
            with contextlib.suppress(OSError):
                tmp.unlink(missing_ok=True)
            # Ошибка называет файл-цель, а не временный, как при прямой записи.
            if exc.errno is None:
                raise
            raise type(exc)(exc.errno, exc.strerror, str(target)) from exc
        except BaseException:
            with contextlib.suppress(OSError):
                tmp.unlink(missing_ok=True)
            raise
        return ArtifactRef(path=rel_path, sha256=hashlib.sha256(data).hexdigest(), size=len(data))

    def describe(self, workspace: Path, rel_path: str) -> ArtifactRef:
        target = self._contained(workspace, rel_path)
        digest = hashlib.sha256()
        size = 0
        with target.open("rb") as handle:
            for chunk in iter(lambda: handle.read(_CHUNK), b""):
                digest.update(chunk)
                size += len(chunk)
        return ArtifactRef(path=rel_path, sha256=digest.hexdigest(), size=size)

    @staticmethod
    def _contained(workspace: Path, rel_path: str) -> Path:
        validate_relative_posix(rel_path)
        root = workspace.resolve()
        target = (root / rel_path).resolve()
        if not target.is_relative_to(root):
            raise ValueError(f"path escapes the workspace: {rel_path!r}")
        return target
