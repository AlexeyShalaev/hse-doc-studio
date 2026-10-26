from __future__ import annotations

import contextlib
import hashlib
import os
import uuid
from pathlib import Path

from hse_doc_studio.core.jobs.files import ArtifactRef, validate_relative_posix


class LocalJobOutputs:
    """Выходы задач на локальном диске: файл появляется целиком или не появляется."""

    def write_output(self, workspace: Path, rel_path: str, data: bytes) -> ArtifactRef:
        target = self._contained(workspace, rel_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        try:
            tmp.write_bytes(data)
            os.replace(tmp, target)
        except BaseException:
            with contextlib.suppress(OSError):
                tmp.unlink(missing_ok=True)
            raise
        return ArtifactRef(path=rel_path, sha256=hashlib.sha256(data).hexdigest(), size=len(data))

    def describe(self, workspace: Path, rel_path: str) -> ArtifactRef:
        target = self._contained(workspace, rel_path)
        data = target.read_bytes()
        return ArtifactRef(path=rel_path, sha256=hashlib.sha256(data).hexdigest(), size=len(data))

    @staticmethod
    def _contained(workspace: Path, rel_path: str) -> Path:
        validate_relative_posix(rel_path)
        root = workspace.resolve()
        target = (root / rel_path).resolve()
        if not target.is_relative_to(root):
            raise ValueError(f"path escapes the workspace: {rel_path!r}")
        return target
