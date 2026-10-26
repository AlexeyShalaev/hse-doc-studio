"""Общие помощники тестов слияния: git как эталон и применение записей к дереву."""

from __future__ import annotations

import subprocess
import tempfile
from collections.abc import Mapping
from pathlib import Path

from hse_doc_studio.core.git_sync.merge.text import BASE_LABEL, OURS_LABEL, THEIRS_LABEL
from hse_doc_studio.core.template_update.entities import FileWrite, FileWriteKind


def git_merge_file(ours: bytes, base: bytes, theirs: bytes, mode: str) -> bytes:
    """Эталон: `git merge-file --diff3` с режимом --ours, --theirs или --union (так же, как зовёт движок)."""
    with tempfile.TemporaryDirectory() as tmp:
        names = []
        for name, content in (("ours", ours), ("base", base), ("theirs", theirs)):
            (Path(tmp) / name).write_bytes(content)
            names.append(str(Path(tmp) / name))
        cmd = [
            "git",
            "merge-file",
            "-p",
            "--diff3",
            mode,
            "-L",
            OURS_LABEL,
            "-L",
            BASE_LABEL,
            "-L",
            THEIRS_LABEL,
            *names,
        ]
        return subprocess.run(cmd, capture_output=True, check=False).stdout  # noqa: S603


def apply_writes(tree: Mapping[str, bytes], writes: list[FileWrite]) -> dict[str, bytes]:
    result = dict(tree)
    for write in writes:
        if write.kind is FileWriteKind.delete:
            result.pop(write.path, None)
        else:
            assert write.content is not None
            result[write.path] = write.content
    return result
