from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from hse_doc_studio.core.catalog import CheckRule
from hse_doc_studio.core.enums import CheckSeverity
from hse_doc_studio.core.value_objects import CheckResult


class BaseCheckEngine(ABC):
    @abstractmethod
    def run(
        self,
        rule: CheckRule,
        severity: CheckSeverity,
        project_folder: Path,
        doc_id: str,
        source_file: str,
        log_content: str | None,
        base_dir: str = "",
    ) -> list[CheckResult]: ...
