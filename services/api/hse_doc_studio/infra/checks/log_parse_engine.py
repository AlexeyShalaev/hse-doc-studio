"""Log-parse check engine.

Scans the xelatex .log for patterns. Two modes:

  - Custom (preferred, used by all current YAML rules):
      params.pattern         — regex with capture groups
      params.message_template — formatted with the captures as {0}, {1}, ...

  - Legacy:
      params.check: "errors" | "overfull" | "all" — built-in patterns

For every match the engine tries to extract the source line by looking for
the `l.NNN` marker that xelatex emits after errors.
"""

from __future__ import annotations

import re
from pathlib import Path

import structlog

from hse_doc_studio.core.catalog import CheckRule
from hse_doc_studio.core.enums import CheckSeverity
from hse_doc_studio.core.value_objects import CheckLocation, CheckResult
from hse_doc_studio.infra.checks.base import BaseCheckEngine
from hse_doc_studio.infra.checks.utils import localized_message, read_text_safe

logger = structlog.get_logger()

_LATEX_ERROR_RE = re.compile(r"^! (.+)$", re.MULTILINE)
_OVERFULL_RE = re.compile(r"Overfull \\hbox.*?l\.(\d+)", re.IGNORECASE)
_LINE_NUM_RE = re.compile(r"l\.(\d+)")


class LogParseCheckEngine(BaseCheckEngine):
    def run(
        self,
        rule: CheckRule,
        severity: CheckSeverity,
        project_folder: Path,
        doc_id: str,  # noqa: ARG002
        source_file: str,
        log_content: str | None,
        base_dir: str = "",  # noqa: ARG002
    ) -> list[CheckResult]:
        # Lazy-load the log if the caller didn't pass it in.
        log = log_content
        if log is None:
            log_path = project_folder / source_file.replace(".tex", ".log")
            if log_path.exists():
                log = read_text_safe(log_path)
        if not log:
            return []

        pattern_str: str = rule.params.get("pattern", "")
        if pattern_str:
            return self._run_custom(rule, severity, source_file, log)

        check_type: str = rule.params.get("check", "errors")
        results: list[CheckResult] = []
        if check_type in ("errors", "all"):
            results.extend(self._collect_errors(rule, severity, source_file, log))
        if check_type in ("overfull", "all"):
            results.extend(self._collect_overfull(rule, severity, source_file, log))
        return results

    def _run_custom(
        self,
        rule: CheckRule,
        severity: CheckSeverity,
        source_file: str,
        log_content: str,
    ) -> list[CheckResult]:
        pattern_str: str = rule.params["pattern"]
        template_param = rule.params.get("message_template") or rule.params.get("message")

        try:
            pattern = re.compile(pattern_str)
        except re.error as exc:
            logger.warning("log_parse_engine: invalid pattern", rule_id=rule.id, exc=str(exc))
            return []

        fallback = rule.title if rule.title else rule.id
        template = localized_message(template_param, fallback=fallback)

        results: list[CheckResult] = []
        for match in pattern.finditer(log_content):
            groups = match.groups()
            try:
                message = template.format(*groups)
            except (KeyError, IndexError, ValueError):
                message = template

            # Try to pick up a `l.NNN` marker right after the match for
            # source-line linking.
            tail = log_content[match.end() : match.end() + 200]
            line_match = _LINE_NUM_RE.search(tail)
            line_no = int(line_match.group(1)) if line_match else None

            results.append(
                CheckResult(
                    rule_id=rule.id,
                    severity=severity,
                    message=message,
                    location=CheckLocation(file=source_file, line=line_no),
                )
            )
        return results

    def _collect_errors(
        self,
        rule: CheckRule,
        severity: CheckSeverity,
        source_file: str,
        log_content: str,
    ) -> list[CheckResult]:
        results: list[CheckResult] = []
        for match in _LATEX_ERROR_RE.finditer(log_content):
            error_msg = match.group(1).strip()
            context_after = log_content[match.end() : match.end() + 200]
            line_match = _LINE_NUM_RE.search(context_after)
            line_no = int(line_match.group(1)) if line_match else None
            message = localized_message(
                None,
                fallback={
                    "ru": f"Ошибка LaTeX: {error_msg}",
                    "en": f"LaTeX error: {error_msg}",
                },
            )
            results.append(
                CheckResult(
                    rule_id=rule.id,
                    severity=severity,
                    message=message,
                    location=CheckLocation(file=source_file, line=line_no),
                )
            )
        return results

    def _collect_overfull(
        self,
        rule: CheckRule,
        severity: CheckSeverity,
        source_file: str,
        log_content: str,
    ) -> list[CheckResult]:
        results: list[CheckResult] = []
        for match in _OVERFULL_RE.finditer(log_content):
            line_no = int(match.group(1))
            message = localized_message(
                None,
                fallback={
                    "ru": f"Переполнение строки (overfull hbox) на строке {line_no}.",
                    "en": f"Line overflow (overfull hbox) at line {line_no}.",
                },
            )
            results.append(
                CheckResult(
                    rule_id=rule.id,
                    severity=severity,
                    message=message,
                    location=CheckLocation(file=source_file, line=line_no),
                )
            )
        return results
