r"""Reference-check engine.

Validates internal references in a LaTeX project without a recompile:

  - `mode: refs`  — every `\ref{X}` / `\eqref{X}` / `\pageref{X}` /
                    `\autoref{X}` must point at a `\label{X}` defined
                    somewhere in the project's `.tex` files.

  - `mode: cites` — every key inside `\cite{a,b}` / `\citep{...}` /
                    `\nocite{...}` must be defined either as a BibTeX entry
                    `@kind{key, ...}` in some `.bib` file, or as a
                    `\bibitem{key}` in a `thebibliography` environment (the
                    manual-bibliography workflow with no `.bib` file).

Both modes scan every `.tex` (or `.bib`) under the project — there is no
`\input{...}` expansion. For a flat or two-deep doc tree this catches the
vast majority of real-world broken refs and citations, and stays fast.
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

_LABEL_RE = re.compile(r"\\label\s*\{([^}]+)\}")
_REF_RE = re.compile(r"\\(?:ref|eqref|pageref|autoref|nameref|cref|Cref)\s*\{([^}]+)\}")
_CITE_RE = re.compile(r"\\(?:cite[a-zA-Z]*|nocite)\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}")
_BIB_ENTRY_RE = re.compile(r"@\w+\s*\{\s*([^,\s}]+)\s*,")
# `\bibitem[label]{key}` — the `thebibliography` workflow defines sources
# directly in .tex (no .bib file), so a `\cite` may resolve against these too.
_BIBITEM_RE = re.compile(r"\\bibitem\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}")
# Labels that packages define at run time — a `\pageref{LastPage}` is valid
# even though no `\label{LastPage}` exists in the sources (lastpage package).
_PACKAGE_LABELS = frozenset({"LastPage"})
# `label={key}` / `label=key` inside option groups (lstlisting, \captionsetup…)
# also defines a referencable label without a literal `\label{}` command.
_OPT_LABEL_RE = re.compile(r"(?<![\w\\])label\s*=\s*\{?\s*([^},\s\]]+)")
# Content that must not participate in the `\ref`/`\cite` scan: verbatim-like
# environment bodies, inline `\verb|…|` spans and `%` comments. All of these
# render literally — a `\ref{...}` inside them is example text, not a link.
_VERBATIM_ENV_RE = re.compile(
    r"\\begin\s*\{(?P<env>lstlisting|verbatim|Verbatim|minted|alltt)\}.*?\\end\s*\{(?P=env)\}",
    re.DOTALL,
)
_VERB_RE = re.compile(r"\\verb\*?(?P<d>[^A-Za-z\s*])(?:(?!(?P=d)).)*(?P=d)")
_COMMENT_RE = re.compile(r"(?<!\\)%.*")


def _mask_ignorable(text: str) -> str:
    """Blank out verbatim bodies, `\\verb` spans and comments.

    Newlines are preserved so line numbers of the remaining matches keep
    pointing at the original source lines.
    """

    def _blank(m: re.Match[str]) -> str:
        return "".join(ch if ch == "\n" else " " for ch in m.group(0))

    text = _VERBATIM_ENV_RE.sub(_blank, text)
    text = _VERB_RE.sub(_blank, text)
    return _COMMENT_RE.sub(_blank, text)


class ReferenceCheckEngine(BaseCheckEngine):
    """Validates `\\ref`/`\\cite` against `\\label`/`.bib` definitions."""

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
        mode = str(rule.params.get("mode", "refs")).lower()
        if mode == "refs":
            return self._check_refs(rule, severity, project_folder, source_file, base_dir)
        if mode == "cites":
            return self._check_cites(rule, severity, project_folder, source_file, base_dir)
        if mode == "unused":
            return self._check_unused_bib(rule, severity, project_folder, base_dir)
        logger.warning("reference_check_engine: unknown mode", rule_id=rule.id, mode=mode)
        return []

    # ------------------------------------------------------------------ refs

    def _check_refs(
        self,
        rule: CheckRule,
        severity: CheckSeverity,
        project_folder: Path,
        source_file: str,
        base_dir: str = "",
    ) -> list[CheckResult]:
        tex_files = match_files(project_folder, {"file_glob": rule.params.get("file_glob", "**/*.tex")}, base_dir)

        labels: set[str] = set(_PACKAGE_LABELS)
        file_texts: list[tuple[Path, str]] = []
        for path in tex_files:
            raw = read_text_safe(path)
            # Labels are collected from the RAW text (an over-collection is
            # safe), the ref scan runs over the masked text — a \ref inside a
            # \verb span, a listing or a comment is example text, not a link.
            labels.update(_LABEL_RE.findall(raw))
            labels.update(_OPT_LABEL_RE.findall(raw))
            file_texts.append((path, _mask_ignorable(raw)))

        results: list[CheckResult] = []
        reported: set[str] = set()
        for path, text in file_texts:
            rel = str(path.relative_to(project_folder))
            for lineno, line in enumerate(text.splitlines(), start=1):
                for match in _REF_RE.finditer(line):
                    key = match.group(1).strip()
                    if not key or key in labels or key in reported:
                        continue
                    reported.add(key)
                    message = self._format_message(
                        rule.params.get("message"),
                        fallback={
                            "ru": f"Ссылка \\ref{{{key}}} указывает на несуществующую метку.",
                            "en": f"Reference \\ref{{{key}}} points to an undefined label.",
                        },
                        key=key,
                    )
                    results.append(
                        CheckResult(
                            rule_id=rule.id,
                            severity=severity,
                            message=message,
                            location=CheckLocation(file=rel, line=lineno),
                        )
                    )

        if not results and not labels and not file_texts:
            # No tex files at all — silent. Otherwise we'd spam for empty projects.
            return []

        return results

    # ------------------------------------------------------------------ cites

    def _check_cites(  # noqa: C901
        self,
        rule: CheckRule,
        severity: CheckSeverity,
        project_folder: Path,
        source_file: str,
        base_dir: str = "",
    ) -> list[CheckResult]:
        tex_files = match_files(project_folder, {"file_glob": rule.params.get("file_glob", "**/*.tex")}, base_dir)
        bib_files = match_files(project_folder, {"file_glob": rule.params.get("bib_glob", "**/*.bib")}, base_dir)

        bib_keys: set[str] = set()
        for path in bib_files:
            bib_keys.update(_BIB_ENTRY_RE.findall(read_text_safe(path)))

        # Read each .tex once: collect \bibitem labels (the thebibliography
        # workflow, where there is no .bib file) and reuse the text for the
        # scan. The scan side is masked: \cite inside \verb/listings/comments
        # is example text, not a citation.
        tex_texts: list[tuple[Path, str]] = []
        bibitem_keys: set[str] = set()
        for path in tex_files:
            raw = read_text_safe(path)
            bibitem_keys.update(_BIBITEM_RE.findall(raw))
            tex_texts.append((path, _mask_ignorable(raw)))
        defined_keys = bib_keys | bibitem_keys

        results: list[CheckResult] = []
        reported: set[str] = set()
        for path, text in tex_texts:
            rel = str(path.relative_to(project_folder))
            for lineno, line in enumerate(text.splitlines(), start=1):
                for match in _CITE_RE.finditer(line):
                    for raw_key in match.group(1).split(","):
                        key = raw_key.strip()
                        if not key or key in defined_keys or key in reported:
                            continue
                        reported.add(key)
                        message = self._format_message(
                            rule.params.get("message"),
                            fallback={
                                "ru": f"Цитирование \\cite{{{key}}} не определено в .bib-файле.",
                                "en": f"Citation \\cite{{{key}}} is not defined in any .bib file.",
                            },
                            key=key,
                        )
                        results.append(
                            CheckResult(
                                rule_id=rule.id,
                                severity=severity,
                                message=message,
                                location=CheckLocation(file=rel, line=lineno),
                            )
                        )
        return results

    # ------------------------------------------------------------------ unused

    def _check_unused_bib(
        self,
        rule: CheckRule,
        severity: CheckSeverity,
        project_folder: Path,
        base_dir: str = "",
    ) -> list[CheckResult]:
        """ГОСТ 7.32-2017 §6.10.2: список использованных источников содержит
        только источники, на которые есть ссылки в тексте. Flag every BibTeX
        entry whose key is never `\\cite`-d, reported at the entry's `.bib`
        location so the student can prune it (or add the missing reference)."""
        tex_files = match_files(project_folder, {"file_glob": rule.params.get("file_glob", "**/*.tex")}, base_dir)
        bib_files = match_files(project_folder, {"file_glob": rule.params.get("bib_glob", "**/*.bib")}, base_dir)

        cited: set[str] = set()
        for path in tex_files:
            for match in _CITE_RE.finditer(read_text_safe(path)):
                cited.update(key.strip() for key in match.group(1).split(","))

        results: list[CheckResult] = []
        for path in bib_files:
            rel = str(path.relative_to(project_folder))
            for lineno, line in enumerate(read_text_safe(path).splitlines(), start=1):
                entry = _BIB_ENTRY_RE.search(line)
                if entry is None:
                    continue
                key = entry.group(1).strip()
                if key in cited:
                    continue
                message = self._format_message(
                    rule.params.get("message"),
                    fallback={
                        "ru": f"Источник `{key}` есть в .bib, но на него нет ни одной ссылки \\cite в тексте.",
                        "en": f"Source `{key}` is in the .bib file but is never cited with \\cite in the text.",
                    },
                    key=key,
                )
                results.append(
                    CheckResult(
                        rule_id=rule.id,
                        severity=severity,
                        message=message,
                        location=CheckLocation(file=rel, line=lineno),
                    )
                )
        return results

    # ------------------------------------------------------------------ utils

    @staticmethod
    def _format_message(message_param: object, fallback: str | dict[str, str], **placeholders: object) -> str:
        raw = localized_message(message_param, fallback)
        try:
            return raw.format(**placeholders)
        except (KeyError, IndexError, ValueError):
            return raw
