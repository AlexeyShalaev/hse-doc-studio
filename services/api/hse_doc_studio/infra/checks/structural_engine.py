"""Structural check engine.

Dispatches on `params.check` to one of several handlers. Preamble properties
(line spacing, font size, geometry, paragraph indent) are parsed from the
document as it is actually compiled — the instance's main .tex with its
`\\input` chain inlined — so a sibling .tex the document doesn't include
(an alternative variant with its own preamble) can't be measured by mistake.
All best-effort regex parsing of the source, no LaTeX-aware AST.

Supported check types (all from YAML pack):
  - line_spacing       — parses \\linespread / \\setstretch
  - font_size          — parses \\fontsize{N}{...} or document class option
  - page_geometry      — parses \\geometry{left=Nmm, right=Nmm, top=Nmm, bottom=Nmm}
  - paragraph_indent   — parses \\setlength{\\parindent}{N}
  - page_count         — reads xelatex log for "Output written ... (N pages,"
  - figure_numbering   — counts figures vs \\caption{...} occurrences

Legacy (back-compat with the very first version of this engine):
  - required_commands  — checks that every command in a list is present
  - min_sections/max_sections — counts \\section{...} occurrences
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Any

import structlog

from hse_doc_studio.core.catalog import CheckRule
from hse_doc_studio.core.enums import CheckSeverity
from hse_doc_studio.core.value_objects import CheckLocation, CheckResult
from hse_doc_studio.infra.checks.base import BaseCheckEngine
from hse_doc_studio.infra.checks.utils import (
    expand_inputs,
    localized_message,
    match_files,
    read_text_safe,
)

logger = structlog.get_logger()

_LINESPREAD_RE = re.compile(r"\\linespread\s*\{\s*([\d.]+)\s*\}")
_SETSTRETCH_RE = re.compile(r"\\setstretch\s*\{\s*([\d.]+)\s*\}")
# Semantic spacing macros from the `setspace` package map to a stretch factor.
_SETSPACE_MACROS = {
    r"\singlespacing": 1.0,
    r"\onehalfspacing": 1.5,
    r"\doublespacing": 2.0,
}
_FONTSIZE_PT_RE = re.compile(r"\\fontsize\s*\{\s*(\d+)(?:pt)?\s*\}")
_DOCCLASS_FONT_RE = re.compile(r"\\documentclass\s*\[([^\]]*)\]")
_DOCCLASS_FONT_OPT_RE = re.compile(r"(\d+)pt")
_PARINDENT_RE = re.compile(r"\\setlength\s*\{\s*\\parindent\s*\}\s*\{\s*([\d.]+)\s*(cm|mm)\s*\}")
# Accept both `\geometry{...}` (multiline curly braces, the common form) and
# the legacy `\usepackage[...]{geometry}` package-option form.
_GEOMETRY_CURLY_RE = re.compile(r"\\geometry\s*\{([^}]+)\}", re.DOTALL)
_GEOMETRY_OPT_RE = re.compile(r"\\usepackage\s*\[([^\]]+)\]\s*\{geometry\}", re.DOTALL)
_GEOMETRY_KV_RE = re.compile(r"(left|right|top|bottom)\s*=\s*([\d.]+)\s*mm")
_SECTION_RE = re.compile(r"\\section\s*\{")
_FIGURE_BEGIN_RE = re.compile(r"\\begin\s*\{\s*figure\b")
_CAPTION_RE = re.compile(r"\\caption\s*\{")
# TeX hard-wraps log lines at max_print_line (79) — for long .build/<doc_id>/
# paths the wrap can land inside "(N pages", even mid-number. `\s+` tolerates a
# wrap before "page"; the caller retries on an unwrapped log for the rest.
_LOG_PAGE_COUNT_RE = re.compile(r"Output written on [^()]+\((\d+)\s+page")
# Float orphan detection: a figure/table must carry a \label and be referenced.
_FLOAT_BEGIN_RE = re.compile(r"\\begin\s*\{\s*(figure|table)\*?\s*\}")
_FLOAT_END_RE = re.compile(r"\\end\s*\{\s*(?:figure|table)\*?\s*\}")
_LABEL_INLINE_RE = re.compile(r"\\label\s*\{([^}]+)\}")
_REF_ANY_RE = re.compile(r"\\(?:ref|pageref|autoref|nameref|cref|Cref|vref)\s*\{([^}]+)\}")


class StructuralCheckEngine(BaseCheckEngine):
    def run(
        self,
        rule: CheckRule,
        severity: CheckSeverity,
        project_folder: Path,
        doc_id: str,
        source_file: str,
        log_content: str | None,
        base_dir: str = "",
    ) -> list[CheckResult]:
        check = rule.params.get("check")

        # Legacy-shape rules (no `check` key) fall back to the original
        # required_commands / min/max_sections behavior.
        if check is None:
            return self._legacy(rule, severity, project_folder, doc_id, source_file, base_dir)

        handlers = {
            "line_spacing": self._check_line_spacing,
            "font_size": self._check_font_size,
            "page_geometry": self._check_page_geometry,
            "paragraph_indent": self._check_paragraph_indent,
            "page_count": self._check_page_count,
            "figure_numbering": self._check_figure_numbering,
            "float_orphans": self._check_float_orphans,
        }
        handler = handlers.get(check)
        if handler is None:
            logger.warning("structural_engine: unknown check type", rule_id=rule.id, check=check)
            return []

        return handler(rule, severity, project_folder, doc_id, source_file, log_content, base_dir)

    # ------------------------------------------------------------------ helpers

    def _doc_files(self, project_folder: Path, source_file: str, base_dir: str = "") -> list[Path]:
        """Files relevant to the current document: the doc's own folder plus
        its base's common/ (preamble lives there). The doc folder is derived
        from the instance's main .tex (team: "shalaev/tz/tz.tex"), NOT from
        doc_id — instance ids ("tz--shalaev") are not folder names."""
        files: list[Path] = []
        doc_dir = (project_folder / source_file).parent
        if doc_dir.is_dir():
            files.extend(sorted(p for p in doc_dir.glob("*.tex") if p.is_file()))
        common_dir = (project_folder / base_dir if base_dir else project_folder) / "common"
        if common_dir.is_dir():
            files.extend(sorted(p for p in common_dir.glob("*.tex") if p.is_file()))
        return files

    def _read_concat(self, files: list[Path]) -> str:
        return "\n".join(read_text_safe(p) for p in files)

    def _compiled_source_text(self, project_folder: Path, source_file: str) -> str:
        """The document as it is actually compiled: the instance's main .tex with
        its ``\\input``/``\\include`` chain inlined.

        Unlike :meth:`_doc_files` this never sees a sibling .tex the document
        doesn't include. That matters for preamble properties, where the folder
        may hold an alternative variant with its own geometry — e.g.
        ``srs_29148.tex`` (ISO/IEC/IEEE 29148, поля 25/15/20/20) lies next to the
        ЕСПД ``technical_specification.tex`` (20/10/25/40) and sorts first, so
        the folder-wide scan measured the wrong document."""
        return "\n".join(sl.text for sl in expand_inputs(project_folder, source_file))

    @staticmethod
    def _spacing_signals(text: str) -> list[tuple[int, float]]:
        """Every spacing signal (numeric \\linespread/\\setstretch plus
        setspace's semantic macros) with its position in the text."""
        found: list[tuple[int, float]] = []
        for regex in (_LINESPREAD_RE, _SETSTRETCH_RE):
            found.extend((m.start(), float(m.group(1))) for m in regex.finditer(text))
        for macro, value in _SETSPACE_MACROS.items():
            pos = text.find(macro)
            if pos != -1:
                found.append((pos, value))
        return found

    def _result(
        self,
        rule: CheckRule,
        severity: CheckSeverity,
        message: str,
        source_file: str,
        line: int | None = None,
    ) -> CheckResult:
        return CheckResult(
            rule_id=rule.id,
            severity=severity,
            message=message,
            location=CheckLocation(file=source_file, line=line),
        )

    # ------------------------------------------------------------------ checks

    def _check_line_spacing(
        self,
        rule: CheckRule,
        severity: CheckSeverity,
        project_folder: Path,
        doc_id: str,
        source_file: str,
        log_content: str | None,  # noqa: ARG002
        base_dir: str = "",  # noqa: ARG002
    ) -> list[CheckResult]:
        expected = float(rule.params.get("expected", 1.5))
        tolerance = float(rule.params.get("tolerance", 0.05))
        text = self._compiled_source_text(project_folder, source_file)

        # Documents legitimately switch spacing locally (title pages are
        # single-spaced), so the check passes when ANY signal matches the
        # expected body spacing; otherwise it reports the first signal by
        # position (the preamble is inlined first, ahead of the body).
        found = self._spacing_signals(text)
        actual: float | None
        if not found:
            actual = None
        elif any(abs(value - expected) <= tolerance for _pos, value in found):
            actual = expected
        else:
            actual = min(found)[1]

        if actual is None:
            return [
                self._result(
                    rule,
                    severity,
                    localized_message(
                        rule.params.get("message"),
                        {
                            "ru": f"Не задан межстрочный интервал (ожидался {expected}).",
                            "en": f"Line spacing is not set (expected {expected}).",
                        },
                    ),
                    source_file,
                )
            ]
        if abs(actual - expected) > tolerance:
            return [
                self._result(
                    rule,
                    severity,
                    localized_message(
                        rule.params.get("message"),
                        {
                            "ru": f"Межстрочный интервал {actual} вместо ожидаемого {expected}.",
                            "en": f"Line spacing is {actual} instead of the expected {expected}.",
                        },
                    ),
                    source_file,
                )
            ]
        return []

    def _check_font_size(
        self,
        rule: CheckRule,
        severity: CheckSeverity,
        project_folder: Path,
        doc_id: str,
        source_file: str,
        log_content: str | None,  # noqa: ARG002
        base_dir: str = "",  # noqa: ARG002
    ) -> list[CheckResult]:
        expected = int(rule.params.get("expected", 14))
        allowed_param = rule.params.get("allowed")
        allowed = {int(x) for x in allowed_param} if allowed_param else {expected}
        text = self._compiled_source_text(project_folder, source_file)

        size: int | None = None
        m = _FONTSIZE_PT_RE.search(text)
        if m is not None:
            size = int(m.group(1))
        else:
            class_m = _DOCCLASS_FONT_RE.search(text)
            if class_m is not None:
                opt_m = _DOCCLASS_FONT_OPT_RE.search(class_m.group(1))
                if opt_m is not None:
                    size = int(opt_m.group(1))

        if size is None:
            return [
                self._result(
                    rule,
                    severity,
                    localized_message(
                        rule.params.get("message"),
                        {
                            "ru": f"Размер шрифта не задан явно (ожидался {expected} pt).",
                            "en": f"Font size is not set explicitly (expected {expected} pt).",
                        },
                    ),
                    source_file,
                )
            ]

        if size not in allowed:
            return [
                self._result(
                    rule,
                    severity,
                    localized_message(
                        rule.params.get("message"),
                        {
                            "ru": f"Размер шрифта {size} pt не соответствует норме ({expected} pt).",
                            "en": f"Font size {size} pt does not match the norm ({expected} pt).",
                        },
                    ),
                    source_file,
                )
            ]
        return []

    def _check_page_geometry(  # noqa: C901
        self,
        rule: CheckRule,
        severity: CheckSeverity,
        project_folder: Path,
        doc_id: str,
        source_file: str,
        log_content: str | None,  # noqa: ARG002
        base_dir: str = "",  # noqa: ARG002
    ) -> list[CheckResult]:
        expected_raw = rule.params.get("expected", {})
        if not isinstance(expected_raw, dict):
            return []
        expected: dict[str, float] = {}
        for key in ("left_mm", "right_mm", "top_mm", "bottom_mm"):
            val = expected_raw.get(key)
            if val is not None:
                expected[key.removesuffix("_mm")] = float(val)
        tolerance = float(rule.params.get("tolerance_mm", 1.0))

        text = self._compiled_source_text(project_folder, source_file)
        # Prefer the imperative \geometry{...} form (most common). Fall back to
        # the package-option form \usepackage[...]{geometry}.
        block_m = _GEOMETRY_CURLY_RE.search(text) or _GEOMETRY_OPT_RE.search(text)
        if block_m is None:
            return [
                self._result(
                    rule,
                    severity,
                    localized_message(
                        rule.params.get("message"),
                        {
                            "ru": "Не задана команда \\geometry — невозможно проверить поля страницы.",
                            "en": "The \\geometry command is missing — page margins cannot be checked.",
                        },
                    ),
                    source_file,
                )
            ]

        actual: dict[str, float] = {}
        for kv in _GEOMETRY_KV_RE.finditer(block_m.group(1)):
            actual[kv.group(1)] = float(kv.group(2))

        bad_ru: list[str] = []
        bad_en: list[str] = []
        for side, exp_mm in expected.items():
            got = actual.get(side)
            if got is None or abs(got - exp_mm) > tolerance:
                got_str = got if got is not None else "—"
                bad_ru.append(f"{side}={got_str} (ожидалось {exp_mm} мм)")
                bad_en.append(f"{side}={got_str} (expected {exp_mm} mm)")

        if not bad_ru:
            return []

        return [
            self._result(
                rule,
                severity,
                localized_message(
                    rule.params.get("message"),
                    {
                        "ru": "Поля страницы не соответствуют ГОСТ: " + ", ".join(bad_ru),
                        "en": "Page margins do not match GOST: " + ", ".join(bad_en),
                    },
                ),
                source_file,
            )
        ]

    def _check_paragraph_indent(
        self,
        rule: CheckRule,
        severity: CheckSeverity,
        project_folder: Path,
        doc_id: str,
        source_file: str,
        log_content: str | None,  # noqa: ARG002
        base_dir: str = "",  # noqa: ARG002
    ) -> list[CheckResult]:
        expected_cm = float(rule.params.get("expected", 1.25))
        tolerance = float(rule.params.get("tolerance", 0.1))
        text = self._compiled_source_text(project_folder, source_file)

        m = _PARINDENT_RE.search(text)
        if m is None:
            return [
                self._result(
                    rule,
                    severity,
                    localized_message(
                        rule.params.get("message"),
                        {
                            "ru": f"Не задан абзацный отступ (ожидался {expected_cm} см).",
                            "en": f"Paragraph indent is not set (expected {expected_cm} cm).",
                        },
                    ),
                    source_file,
                )
            ]

        value = float(m.group(1))
        unit = m.group(2)
        value_cm = value / 10.0 if unit == "mm" else value
        if abs(value_cm - expected_cm) > tolerance:
            return [
                self._result(
                    rule,
                    severity,
                    localized_message(
                        rule.params.get("message"),
                        {
                            "ru": f"Абзацный отступ {value_cm:.2f} см вместо ожидаемого {expected_cm} см.",
                            "en": f"Paragraph indent is {value_cm:.2f} cm instead of the expected {expected_cm} cm.",
                        },
                    ),
                    source_file,
                )
            ]
        return []

    def _build_log_path(self, project_folder: Path, doc_id: str, source_file: str) -> Path:
        """Mirror DockerCompileExecutor's output layout: the per-engine TeX
        .log lands in `<doc_dir>/.build/<doc_id>/<stem>.log`, next to (not on
        top of) the source."""
        rel = PurePosixPath(source_file.replace("\\", "/"))
        parent = rel.parent.as_posix()
        doc_dir = project_folder if parent in ("", ".") else project_folder / parent
        return doc_dir / ".build" / doc_id / f"{rel.stem}.log"

    def _extract_page_count(
        self,
        project_folder: Path,
        doc_id: str,
        source_file: str,
        log_content: str | None,
    ) -> int | None:
        # The "Output written on ... (N pages)" line is written by the engine
        # into the per-document TeX .log under .build/<doc_id>/ — NOT next to
        # the source. `log_content` is latexmk's stdout (and is only passed on
        # failure), which usually lacks that line, so read the build log too.
        sources: list[str] = []
        if log_content:
            sources.append(log_content)
        build_log = self._build_log_path(project_folder, doc_id, source_file)
        if build_log.exists():
            sources.append(read_text_safe(build_log))
        # Legacy fallback: a .log written next to the source.
        flat_log = project_folder / source_file.replace("\\", "/").replace(".tex", ".log")
        if flat_log != build_log and flat_log.exists():
            sources.append(read_text_safe(flat_log))

        for text in sources:
            m = _LOG_PAGE_COUNT_RE.search(text) or _LOG_PAGE_COUNT_RE.search(text.replace("\n", ""))
            if m is not None:
                return int(m.group(1))
        return None

    def _check_page_count(
        self,
        rule: CheckRule,
        severity: CheckSeverity,
        project_folder: Path,
        doc_id: str,
        source_file: str,
        log_content: str | None,
        base_dir: str = "",
    ) -> list[CheckResult]:
        min_pages = rule.params.get("min")
        max_pages = rule.params.get("max")
        if min_pages is None and max_pages is None:
            return []

        pages = self._extract_page_count(project_folder, doc_id, source_file, log_content)

        if pages is None:
            return [
                self._result(
                    rule,
                    severity,
                    localized_message(
                        rule.params.get("message"),
                        {
                            "ru": "Не удалось определить количество страниц — соберите документ заново.",
                            "en": "Could not determine the page count — rebuild the document.",
                        },
                    ),
                    source_file,
                )
            ]

        if min_pages is not None and pages < int(min_pages):
            return [
                self._result(
                    rule,
                    severity,
                    localized_message(
                        rule.params.get("message"),
                        {
                            "ru": f"Документ {pages} стр. — меньше минимума {min_pages}.",
                            "en": f"Document has {pages} pages — fewer than the minimum of {min_pages}.",
                        },
                    ),
                    source_file,
                )
            ]
        if max_pages is not None and pages > int(max_pages):
            return [
                self._result(
                    rule,
                    severity,
                    localized_message(
                        rule.params.get("message"),
                        {
                            "ru": f"Документ {pages} стр. — больше максимума {max_pages}.",
                            "en": f"Document has {pages} pages — more than the maximum of {max_pages}.",
                        },
                    ),
                    source_file,
                )
            ]
        return []

    def _check_figure_numbering(
        self,
        rule: CheckRule,
        severity: CheckSeverity,
        project_folder: Path,
        doc_id: str,
        source_file: str,
        log_content: str | None,  # noqa: ARG002
        base_dir: str = "",
    ) -> list[CheckResult]:
        text = self._read_concat(self._doc_files(project_folder, source_file, base_dir))
        figures = len(_FIGURE_BEGIN_RE.findall(text))
        captions = len(_CAPTION_RE.findall(text))

        if figures == 0:
            return []
        if captions < figures:
            return [
                self._result(
                    rule,
                    severity,
                    localized_message(
                        rule.params.get("message"),
                        {
                            "ru": f"Рисунков {figures}, подписей \\caption {captions} — не все подписаны.",
                            "en": f"{figures} figures, {captions} \\caption captions — not all are captioned.",
                        },
                    ),
                    source_file,
                )
            ]
        return []

    def _check_float_orphans(  # noqa: C901
        self,
        rule: CheckRule,
        severity: CheckSeverity,
        project_folder: Path,
        doc_id: str,  # noqa: ARG002
        source_file: str,
        log_content: str | None,  # noqa: ARG002
        base_dir: str = "",
    ) -> list[CheckResult]:
        """ГОСТ 7.32-2017 §6.5.7/§6.6.4: каждый рисунок и таблицу необходимо
        упомянуть в тексте. Flag every figure/table float that either carries no
        `\\label` (cannot be referenced) or whose label is never `\\ref`-ed.

        Works across the multi-file tree via `expand_inputs`, so a `\\ref` in one
        chapter satisfies a float defined in another, and findings point at the
        real source file:line of the float."""
        lines = expand_inputs(project_folder, source_file)

        referenced: set[str] = set()
        for sl in lines:
            for match in _REF_ANY_RE.finditer(sl.text):
                referenced.update(key.strip() for key in match.group(1).split(","))

        results: list[CheckResult] = []
        in_float: tuple[str, str, int] | None = None  # (kind, file, line)
        label: str | None = None
        for sl in lines:
            text = sl.text
            if in_float is None:
                begin = _FLOAT_BEGIN_RE.search(text)
                if begin is None:
                    continue
                in_float = (begin.group(1), sl.file, sl.line)
                label = None
                text = text[begin.end() :]
            if label is None:
                label_match = _LABEL_INLINE_RE.search(text)
                if label_match is not None:
                    label = label_match.group(1).strip()
            if _FLOAT_END_RE.search(text):
                finding = self._float_finding(rule, severity, in_float, label, referenced)
                if finding is not None:
                    results.append(finding)
                in_float = None
                label = None
        return results

    def _float_finding(
        self,
        rule: CheckRule,
        severity: CheckSeverity,
        float_info: tuple[str, str, int],
        label: str | None,
        referenced: set[str],
    ) -> CheckResult | None:
        kind, file, line = float_info
        kind_ru = "Рисунок" if kind == "figure" else "Таблица"
        kind_en = "Figure" if kind == "figure" else "Table"
        if label is None:
            message = localized_message(
                rule.params.get("message"),
                {
                    "ru": f"{kind_ru} без \\label — на него нельзя сослаться в тексте (ГОСТ 7.32-2017 требует ссылку).",
                    "en": (
                        f"{kind_en} without \\label — it cannot be referenced in the text "
                        "(ГОСТ 7.32-2017 requires a reference)."
                    ),
                },
            )
        elif label not in referenced:
            message = localized_message(
                rule.params.get("message"),
                {
                    "ru": f"На {kind_ru.lower()} (\\label{{{label}}}) нет ни одной ссылки \\ref в тексте.",
                    "en": f"The {kind_en.lower()} (\\label{{{label}}}) has no \\ref reference in the text.",
                },
            )
        else:
            return None
        return CheckResult(
            rule_id=rule.id,
            severity=severity,
            message=message,
            location=CheckLocation(file=file, line=line),
        )

    # ------------------------------------------------------------------ legacy

    def _legacy(
        self,
        rule: CheckRule,
        severity: CheckSeverity,
        project_folder: Path,
        doc_id: str,  # noqa: ARG002
        source_file: str,
        base_dir: str = "",
    ) -> list[CheckResult]:
        params: dict[str, Any] = rule.params
        required_commands: list[str] = params.get("required_commands", [])
        min_sections = params.get("min_sections")
        max_sections = params.get("max_sections")

        files = match_files(project_folder, params, base_dir) or self._doc_files(project_folder, source_file, base_dir)
        all_text = self._read_concat(files)
        results: list[CheckResult] = []

        for cmd in required_commands:
            cmd_clean = cmd.lstrip("\\")
            cmd_re = re.compile(r"\\" + re.escape(cmd_clean) + r"(?![a-zA-Z])")
            if not cmd_re.search(all_text):
                results.append(
                    self._result(
                        rule,
                        severity,
                        localized_message(
                            rule.params.get("message"),
                            {
                                "ru": f"Не найдена обязательная команда \\{cmd_clean}.",
                                "en": f"Required command \\{cmd_clean} not found.",
                            },
                        ),
                        source_file,
                    )
                )

        if min_sections is not None or max_sections is not None:
            section_count = len(_SECTION_RE.findall(all_text))
            if min_sections is not None and section_count < int(min_sections):
                results.append(
                    self._result(
                        rule,
                        severity,
                        localized_message(
                            rule.params.get("message"),
                            {
                                "ru": f"Разделов {section_count}, ожидалось не менее {min_sections}.",
                                "en": f"{section_count} sections, expected at least {min_sections}.",
                            },
                        ),
                        source_file,
                    )
                )
            if max_sections is not None and section_count > int(max_sections):
                results.append(
                    self._result(
                        rule,
                        severity,
                        localized_message(
                            rule.params.get("message"),
                            {
                                "ru": f"Разделов {section_count}, ожидалось не более {max_sections}.",
                                "en": f"{section_count} sections, expected at most {max_sections}.",
                            },
                        ),
                        source_file,
                    )
                )

        return results
