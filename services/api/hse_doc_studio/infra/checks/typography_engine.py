"""Typography check engine — deterministic Russian-typography fixes.

Dispatches on `params.check` to one sub-rule. Every finding carries a
:class:`CheckFix` (literal search → replace at a file:line) so the UI can offer
a one-click quick-fix with NO LLM involved. Sub-rules:

  - quotes    — straight ``"…"`` → «ёлочки»
  - dash      — space-hyphen-space ``" - "`` → em dash ``" — "``
  - ellipsis  — ``...`` → ``…``
  - initials  — ``И. И. Иванов`` → ``И.~И.~Иванов`` (non-breaking spaces)
  - percent   — ``10 %`` → ``10~%`` (non-breaking space before percent)

All operate per occurrence on the raw source line, so the student reviews and
applies each fix individually (or all at once from the panel).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import structlog

from hse_doc_studio.core.catalog import CheckRule
from hse_doc_studio.core.enums import CheckSeverity
from hse_doc_studio.core.value_objects import CheckFix, CheckLocation, CheckResult
from hse_doc_studio.infra.checks.base import BaseCheckEngine
from hse_doc_studio.infra.checks.utils import localized_message, match_files, read_text_safe

logger = structlog.get_logger()


@dataclass(frozen=True)
class _SubRule:
    pattern: re.Pattern[str]
    replace: Callable[[re.Match[str]], str]
    message: dict[str, str]
    title: dict[str, str]


# Code renders literally — straight quotes, three dots and hyphens inside
# listings/verbatim/`\verb` spans/comments are NOT typography violations.
_ENV_BEGIN_RE = re.compile(r"\\begin\s*\{(?:lstlisting|verbatim|Verbatim|minted|alltt)\}")
_ENV_END_RE = re.compile(r"\\end\s*\{(?:lstlisting|verbatim|Verbatim|minted|alltt)\}")
_VERB_SPAN_RE = re.compile(r"\\verb\*?(?P<d>[^A-Za-z\s*])(?:(?!(?P=d)).)*(?P=d)")
_COMMENT_SPAN_RE = re.compile(r"(?<!\\)%.*")


def _mask_spans(line: str) -> str:
    """Blank `\\verb` spans and `%` comments, preserving character positions."""

    def _blank(m: re.Match[str]) -> str:
        return " " * len(m.group(0))

    return _COMMENT_SPAN_RE.sub(_blank, _VERB_SPAN_RE.sub(_blank, line))


_SUB_RULES: dict[str, _SubRule] = {
    "quotes": _SubRule(
        pattern=re.compile(r'"([^"\n]*)"'),
        replace=lambda m: f"«{m.group(1)}»",
        message={
            "ru": "Прямые кавычки — по ГОСТ используйте «ёлочки».",
            "en": "Straight quotes — per GOST use «guillemets».",
        },
        title={"ru": "Заменить на «ёлочки»", "en": "Replace with «guillemets»"},
    ),
    "dash": _SubRule(
        pattern=re.compile(r" - "),
        replace=lambda _m: " — ",
        message={
            "ru": "Дефис между словами — замените на тире «—».",
            "en": "Hyphen between words — replace with an em dash «—».",
        },
        title={"ru": "Заменить на тире «—»", "en": "Replace with an em dash «—»"},
    ),
    "ellipsis": _SubRule(
        pattern=re.compile(r"\.\.\."),
        replace=lambda _m: "…",
        message={
            "ru": "Три точки — замените на символ многоточия «…».",
            "en": "Three dots — replace with the ellipsis character «…».",
        },
        title={"ru": "Заменить на «…»", "en": "Replace with «…»"},
    ),
    "initials": _SubRule(
        pattern=re.compile(r"([А-ЯЁ]\.)\s+([А-ЯЁ]\.)"),
        replace=lambda m: f"{m.group(1)}~{m.group(2)}",
        message={
            "ru": "Инициалы рвутся переносом — поставьте неразрывный пробел «~».",
            "en": "Initials may break across lines — insert a non-breaking space «~».",
        },
        title={"ru": "Поставить неразрывный пробел", "en": "Insert a non-breaking space"},
    ),
    "percent": _SubRule(
        # Only the escaped `\%` is a rendered percent sign — a raw `%` after a
        # number starts a LaTeX comment and is masked out before matching.
        pattern=re.compile(r"(\d+(?:[.,]\d+)?)\s+(\\%)"),
        replace=lambda m: f"{m.group(1)}~{m.group(2)}",
        message={
            "ru": "Число и знак процента — соедините неразрывным пробелом «~».",
            "en": "Number and percent sign — join them with a non-breaking space «~».",
        },
        title={"ru": "Поставить неразрывный пробел", "en": "Insert a non-breaking space"},
    ),
}


class TypographyCheckEngine(BaseCheckEngine):
    def run(
        self,
        rule: CheckRule,
        severity: CheckSeverity,
        project_folder: Path,
        doc_id: str,  # noqa: ARG002
        source_file: str,  # noqa: ARG002
        log_content: str | None,  # noqa: ARG002
        base_dir: str = "",
    ) -> list[CheckResult]:
        check = str(rule.params.get("check", "")).lower()
        sub = _SUB_RULES.get(check)
        if sub is None:
            logger.warning("typography_engine: unknown check", rule_id=rule.id, check=check)
            return []

        message = localized_message(rule.params.get("message"), sub.message)
        title = localized_message(None, sub.title)
        results: list[CheckResult] = []
        for path in match_files(project_folder, rule.params, base_dir):
            rel = str(path.relative_to(project_folder))
            results.extend(self._scan_file(rule, severity, sub, read_text_safe(path), rel, message, title))
        return results

    @staticmethod
    def _scan_file(  # noqa: PLR0913 — flat data plumbing for one file scan
        rule: CheckRule,
        severity: CheckSeverity,
        sub: _SubRule,
        text: str,
        rel: str,
        message: str,
        title: str,
    ) -> list[CheckResult]:
        results: list[CheckResult] = []
        in_code = False
        for lineno, line in enumerate(text.splitlines(), start=1):
            if in_code:
                if _ENV_END_RE.search(line):
                    in_code = False
                continue
            if _ENV_BEGIN_RE.search(line):
                in_code = _ENV_END_RE.search(line) is None
                continue
            # Masking keeps positions/length, so a match on the masked
            # line is byte-identical to the raw line at the same span.
            for match in sub.pattern.finditer(_mask_spans(line)):
                search = match.group(0)
                replace = sub.replace(match)
                if search == replace:
                    continue
                results.append(
                    CheckResult(
                        rule_id=rule.id,
                        severity=severity,
                        message=message,
                        location=CheckLocation(file=rel, line=lineno),
                        fix=CheckFix(
                            file=rel,
                            search=search,
                            replace=replace,
                            line=lineno,
                            title=title,
                        ),
                    )
                )
        return results
