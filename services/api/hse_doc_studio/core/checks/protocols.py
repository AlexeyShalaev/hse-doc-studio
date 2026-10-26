from __future__ import annotations

from pathlib import Path
from typing import Protocol

from hse_doc_studio.core.catalog import CheckRule
from hse_doc_studio.core.enums import CheckSeverity
from hse_doc_studio.core.value_objects import CheckResult


class ICheckRunner(Protocol):
    # Синхронный прогон правил по исходникам и логу: вызывается через
    # asyncio.to_thread, поэтому имена параметров часть контракта.
    def run_all(
        self,
        rules_with_severity: list[tuple[CheckRule, CheckSeverity]],
        project_folder: Path,
        doc_id: str,
        source_file: str,
        log_content: str | None = None,
        base_dir: str = "",
        custom_mode: bool = False,
    ) -> list[CheckResult]: ...
