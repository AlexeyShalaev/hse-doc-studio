"""Regex check engine.

Two modes, switched by `negate`:

  - `negate: false` (default) — pattern is REQUIRED. If no file in the glob
    contains a match, fire a single file-level diagnostic with the YAML
    `params.message`. This is the "обязательный раздел / команда" case.

  - `negate: true` — pattern is FORBIDDEN. Fire a per-line diagnostic for
    every match. This is the "запрещённая конструкция / TODO / FIXME" case.
"""

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

# Maps the human-readable `flags:` values authors write in pack YAML to the
# corresponding `re` module constants. Both full names and single-letter
# aliases are accepted so a rule can say `flags: [multiline]` or `flags: [m]`.
_RE_FLAG_MAP: dict[str, int] = {
    "multiline": re.MULTILINE,
    "m": re.MULTILINE,
    "ignorecase": re.IGNORECASE,
    "i": re.IGNORECASE,
    "dotall": re.DOTALL,
    "s": re.DOTALL,
    "verbose": re.VERBOSE,
    "x": re.VERBOSE,
    "unicode": re.UNICODE,
    "u": re.UNICODE,
    "ascii": re.ASCII,
    "a": re.ASCII,
}


def _parse_flags(raw: object) -> int:
    """Translate a rule's `flags` param into a combined `re` flag bitmask.

    Accepts a single string (`"multiline"`) or a list of strings. Unknown
    names are ignored with a warning rather than failing the whole rule.
    """
    if not raw:
        return 0
    names = [raw] if isinstance(raw, str) else list(raw) if isinstance(raw, (list, tuple)) else []
    flags = 0
    for name in names:
        flag = _RE_FLAG_MAP.get(str(name).strip().lower())
        if flag is None:
            logger.warning("regex_engine: unknown flag", flag=name)
            continue
        flags |= flag
    return flags


class RegexCheckEngine(BaseCheckEngine):
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
        pattern_str: str = rule.params.get("pattern", "")
        if not pattern_str:
            logger.warning("regex_engine: no pattern in rule", rule_id=rule.id)
            return []

        try:
            pattern = re.compile(pattern_str, _parse_flags(rule.params.get("flags")))
        except re.error as exc:
            logger.warning("regex_engine: invalid pattern", rule_id=rule.id, exc=str(exc))
            return []

        files = match_files(project_folder, rule.params, base_dir)
        negate = bool(rule.params.get("negate", False))
        title = rule.title.get("ru", rule.id)
        message = localized_message(
            rule.params.get("message"),
            fallback=title if negate else {"ru": f"Не найдено: {title}", "en": f"Not found: {title}"},
        )

        if negate:
            return self._fire_per_match(rule, severity, project_folder, files, pattern, message)
        return self._fire_if_missing(rule, severity, project_folder, files, pattern, message, source_file)

    def _fire_per_match(
        self,
        rule: CheckRule,
        severity: CheckSeverity,
        project_folder: Path,
        files: list[Path],
        pattern: re.Pattern[str],
        message: str,
    ) -> list[CheckResult]:
        results: list[CheckResult] = []
        for path in files:
            text = read_text_safe(path)
            rel = str(path.relative_to(project_folder))
            for lineno, line in enumerate(text.splitlines(), start=1):
                if pattern.search(line):
                    results.append(
                        CheckResult(
                            rule_id=rule.id,
                            severity=severity,
                            message=message,
                            location=CheckLocation(file=rel, line=lineno),
                        )
                    )
        return results

    def _fire_if_missing(
        self,
        rule: CheckRule,
        severity: CheckSeverity,
        project_folder: Path,
        files: list[Path],
        pattern: re.Pattern[str],
        message: str,
        source_file: str,
    ) -> list[CheckResult]:
        # Search every byte of every matched file. As soon as we find a match
        # anywhere, the requirement is satisfied — no diagnostic.
        for path in files:
            text = read_text_safe(path)
            if pattern.search(text):
                return []

        # Required pattern absent across all files. Report at the first file
        # in the glob (or the document's main source if no files matched).
        location_file = str(files[0].relative_to(project_folder)) if files else source_file
        return [
            CheckResult(
                rule_id=rule.id,
                severity=severity,
                message=message,
                location=CheckLocation(file=location_file, line=None),
            )
        ]
