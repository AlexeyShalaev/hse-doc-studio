from __future__ import annotations

from pathlib import Path

import httpx
import structlog

from hse_doc_studio.core.catalog import CheckRule
from hse_doc_studio.core.enums import CheckEngine, CheckSeverity, Lang
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.core.value_objects import CheckResult
from hse_doc_studio.infra.checks.base import BaseCheckEngine
from hse_doc_studio.infra.checks.external_engine import ExternalCheckEngine
from hse_doc_studio.infra.checks.file_exists_engine import FileExistsCheckEngine
from hse_doc_studio.infra.checks.log_parse_engine import LogParseCheckEngine
from hse_doc_studio.infra.checks.python_engine import PythonCheckEngine
from hse_doc_studio.infra.checks.reference_check_engine import ReferenceCheckEngine
from hse_doc_studio.infra.checks.regex_engine import RegexCheckEngine
from hse_doc_studio.infra.checks.structural_engine import StructuralCheckEngine
from hse_doc_studio.infra.checks.tex_command_count_engine import TexCommandCountEngine
from hse_doc_studio.infra.checks.typography_engine import TypographyCheckEngine
from hse_doc_studio.infra.languagetool.container_manager import LanguageToolContainerManager

logger = structlog.get_logger()

# Engines that require a readable .tex source or a LaTeX compile log — for a
# custom (non-template) document neither exists, so these are force-skipped
# rather than run against nonsense input. `file_exists` is NOT suppressed:
# "does this file exist" stays meaningful regardless of format.
_CUSTOM_MODE_SUPPRESSED: frozenset[CheckEngine] = frozenset(
    {
        CheckEngine.regex,
        CheckEngine.structural,
        CheckEngine.tex_command_count,
        CheckEngine.reference_check,
        CheckEngine.log_parse,
        CheckEngine.python,
        CheckEngine.external,
        CheckEngine.typography,
    }
)


class CheckRunner:
    """Dispatches check rules to the appropriate engine and collects results."""

    def __init__(self, lt_manager: LanguageToolContainerManager, lt_client: httpx.Client) -> None:
        # The external (LanguageTool) engine reads its live endpoint from the
        # container manager (auto-started on demand). No enable flag / URL —
        # installing the image is the opt-in; when the container isn't up the
        # engine simply returns no results.
        self._engines: dict[CheckEngine, BaseCheckEngine] = {
            CheckEngine.regex: RegexCheckEngine(),
            CheckEngine.file_exists: FileExistsCheckEngine(),
            CheckEngine.tex_command_count: TexCommandCountEngine(),
            CheckEngine.log_parse: LogParseCheckEngine(),
            CheckEngine.structural: StructuralCheckEngine(),
            CheckEngine.python: PythonCheckEngine(),
            CheckEngine.reference_check: ReferenceCheckEngine(),
            CheckEngine.typography: TypographyCheckEngine(),
            CheckEngine.external: ExternalCheckEngine(container_manager=lt_manager, client=lt_client),
        }

    def run_all(
        self,
        rules_with_severity: list[tuple[CheckRule, CheckSeverity]],
        project_folder: Path,
        doc_id: str,
        source_file: str,
        log_content: str | None = None,
        base_dir: str = "",
        custom_mode: bool = False,
    ) -> list[CheckResult]:
        results: list[CheckResult] = []

        for rule, severity in rules_with_severity:
            if custom_mode and rule.engine in _CUSTOM_MODE_SUPPRESSED:
                results.append(self._skipped_result(rule))
                continue
            engine = self._engines.get(rule.engine)
            if engine is None:
                logger.warning(
                    "check_runner: no engine for check type",
                    engine=rule.engine,
                    rule_id=rule.id,
                )
                continue
            try:
                rule_results = engine.run(
                    rule=rule,
                    severity=severity,
                    project_folder=project_folder,
                    doc_id=doc_id,
                    source_file=source_file,
                    log_content=log_content,
                    base_dir=base_dir,
                )
                results.extend(rule_results)
            except Exception as exc:
                logger.warning(
                    "check_runner: engine error",
                    rule_id=rule.id,
                    engine=rule.engine,
                    exc=str(exc),
                )

        return results

    @staticmethod
    def _skipped_result(rule: CheckRule) -> CheckResult:
        en = current_interface_language() is Lang.en
        message = (
            "This check is not applicable to a custom document"
            if en
            else "Проверка недоступна для кастомных документов"
        )
        return CheckResult(rule_id=rule.id, severity=CheckSeverity.skipped, message=message)
