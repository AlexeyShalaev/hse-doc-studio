"""Трёхстороннее слияние текста через `git merge-file` (git — уже зависимость VCS).

Маркеры конфликта — в стиле diff3: видно и «моё», и «как было в шаблоне», и
«как стало». Подписи маркеров — для студента, а не для git.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from hse_doc_studio.core.template_update.planner import MergeOutcome
from hse_doc_studio.core.vcs.errors import VcsCommandError, VcsUnavailableError

# git merge-file: код возврата — число конфликтов (не больше 127), ошибка — отрицательный.
_MAX_CONFLICT_CODE = 127


class GitMergeFileEngine:
    def __init__(
        self,
        ours_label: str = "ваш вариант",
        base_label: str = "шаблон: было",
        theirs_label: str = "шаблон: стало",
    ) -> None:
        self._labels = (ours_label, base_label, theirs_label)

    def merge(self, ours: bytes, base: bytes, theirs: bytes) -> MergeOutcome:
        with tempfile.TemporaryDirectory(prefix="hse-merge-") as tmp:
            paths = []
            for name, content in (("ours", ours), ("base", base), ("theirs", theirs)):
                path = Path(tmp) / name
                path.write_bytes(content)
                paths.append(str(path))
            ours_label, base_label, theirs_label = self._labels
            cmd = [
                "git",
                "merge-file",
                "-p",
                "--diff3",
                "-L",
                ours_label,
                "-L",
                base_label,
                "-L",
                theirs_label,
                *paths,
            ]
            env = dict(os.environ)
            env["GIT_CONFIG_NOSYSTEM"] = "1"
            try:
                proc = subprocess.run(cmd, capture_output=True, check=False, env=env)  # noqa: S603
            except FileNotFoundError as exc:
                raise VcsUnavailableError("git executable not found") from exc
        if proc.returncode < 0 or proc.returncode > _MAX_CONFLICT_CODE:
            raise VcsCommandError("merge-file", proc.stderr.decode("utf-8", "replace"))
        return MergeOutcome(content=proc.stdout, conflicts=proc.returncode)
