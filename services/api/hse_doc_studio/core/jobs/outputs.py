from __future__ import annotations

from pathlib import Path
from typing import Protocol

from hse_doc_studio.core.jobs.files import ArtifactRef


class IJobOutputs(Protocol):
    """Единственный порт выходов задач не-compile семейств (compile пишет через IArtifactStore)."""

    def write_output(self, workspace: Path, rel_path: str, data: bytes) -> ArtifactRef:
        """Атомарно (временный файл и os.replace) пишет файл внутрь рабочей папки."""
        ...

    def describe(self, workspace: Path, rel_path: str) -> ArtifactRef:
        """Описывает уже лежащий в рабочей папке файл."""
        ...
