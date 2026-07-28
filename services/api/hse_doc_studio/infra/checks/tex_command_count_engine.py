from __future__ import annotations

import re
from pathlib import Path

import structlog

from hse_doc_studio.core.catalog import CheckRule
from hse_doc_studio.core.enums import CheckSeverity
from hse_doc_studio.core.value_objects import CheckLocation, CheckResult
from hse_doc_studio.infra.checks.base import BaseCheckEngine
from hse_doc_studio.infra.checks.utils import (
    localized_message,
    match_files,
    read_text_safe,
)

logger = structlog.get_logger()


class TexCommandCountEngine(BaseCheckEngine):
    r"""Counts \command occurrences in matched files vs params['min']/['max'].

    Supports `params.message` as a custom diagnostic. The message can include
    placeholders `{count}`, `{min}`, `{max}`, `{command}` for templating.
    """

    def run(
        self,
        rule: CheckRule,
        severity: CheckSeverity,
        project_folder: Path,
        doc_id: str,  # noqa: ARG002
        source_file: str,
        log_content: str | None,  # noqa: ARG002
        base_dir: str = "",
    ) -> list[CheckResult]:
        command: str = rule.params.get("command", "")
        min_count = rule.params.get("min")
        max_count = rule.params.get("max")

        if not command:
            logger.warning("tex_command_count_engine: no command in rule", rule_id=rule.id)
            return []

        cmd_clean = command.lstrip("\\")
        cmd_pattern = re.compile(r"\\" + re.escape(cmd_clean) + r"(?![a-zA-Z])")

        total = 0
        for path in match_files(project_folder, rule.params, base_dir):
            total += len(cmd_pattern.findall(read_text_safe(path)))

        results: list[CheckResult] = []
        message_param = rule.params.get("message")

        if min_count is not None and total < int(min_count):
            message = self._format(
                message_param,
                {
                    "ru": f"Команда \\{cmd_clean} встречается {total} раз, ожидалось не менее {min_count}.",
                    "en": f"Command \\{cmd_clean} occurs {total} time(s), expected at least {min_count}.",
                },
                count=total,
                min=min_count,
                max=max_count,
                command=cmd_clean,
            )
            results.append(
                CheckResult(
                    rule_id=rule.id,
                    severity=severity,
                    message=message,
                    location=CheckLocation(file=source_file, line=None),
                )
            )

        if max_count is not None and total > int(max_count):
            message = self._format(
                message_param,
                {
                    "ru": f"Команда \\{cmd_clean} встречается {total} раз, ожидалось не более {max_count}.",
                    "en": f"Command \\{cmd_clean} occurs {total} time(s), expected at most {max_count}.",
                },
                count=total,
                min=min_count,
                max=max_count,
                command=cmd_clean,
            )
            results.append(
                CheckResult(
                    rule_id=rule.id,
                    severity=severity,
                    message=message,
                    location=CheckLocation(file=source_file, line=None),
                )
            )

        return results

    @staticmethod
    def _format(value: object, fallback: str | dict[str, str], **placeholders: object) -> str:
        raw = localized_message(value, fallback)
        try:
            return raw.format(**placeholders)
        except (KeyError, IndexError, ValueError):
            return raw
