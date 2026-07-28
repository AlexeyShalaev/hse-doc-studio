from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import httpx
import structlog

from hse_doc_studio.core.catalog import CheckRule
from hse_doc_studio.core.enums import CheckSeverity
from hse_doc_studio.core.value_objects import CheckLocation, CheckResult
from hse_doc_studio.infra.checks.base import BaseCheckEngine
from hse_doc_studio.infra.checks.utils import read_text_safe
from hse_doc_studio.infra.languagetool.container_manager import LanguageToolContainerManager

logger = structlog.get_logger()

_CHECK_PATH = "/v2/check"
# LaTeX-source noise rules: WHITESPACE — markup indentation; DoubleNOT /
# PREP_C_and_Noun — legitimate ГОСТ phrasing («не менее … не менее», «в
# соответствии с ГОСТ 19.x»); UPPERCASE_SENTENCE_START — list items are
# sentence fragments by design.
_DEFAULT_DISABLED_RULES = "WHITESPACE_RULE,DoubleNOT,PREP_C_and_Noun,UPPERCASE_SENTENCE_START"

# ── LaTeX → plain-text preparation ─────────────────────────────────────────
# LanguageTool receives a *prepared* version of the source: markup is removed
# or replaced so its prose rules stop misfiring on LaTeX syntax. Every
# replacement preserves the NEWLINE structure (never adds or removes a line),
# so `offset → line` mapping over the prepared text still points at the
# correct source line.

_VERBATIM_ENV_RE = re.compile(
    r"\\begin\s*\{(?P<env>lstlisting|verbatim|Verbatim|minted|alltt|thebibliography)\}"
    r".*?\\end\s*\{(?P=env)\}",
    re.DOTALL,
)
_COMMENT_RE = re.compile(r"(?<!\\)%.*")
_VERB_RE = re.compile(r"\\verb\*?(?P<d>[^A-Za-z\s*])(?:(?!(?P=d)).)*(?P=d)")
_PLACEHOLDER_RE = re.compile(r"\\hseFill\s*\{[^{}]*\}")
_HSE_OPTIONAL_RE = re.compile(r"\\hseOptional\s*")
_HSE_MACRO_RE = re.compile(r"\\hse[A-Za-z]+|\\the[a-zA-Z]+")
_REFLIKE_RE = re.compile(
    r"\\(?:ref|eqref|pageref|autoref|nameref|cref|Cref|cite[a-zA-Z]*|nocite)"
    r"\s*(?:\[[^\]\n]*\])?\s*\{[^{}]*\}"
)
_CAPTIONOF_RE = re.compile(r"\\captionof\s*\{[^{}]*\}\s*\{([^{}]*)\}")
_HEADING_RE = re.compile(r"\\(?:chapter|section|subsection|subsubsection|paragraph|caption)\*?\s*\{([^{}]*)\}")
_TABULAR_RE = re.compile(r"\\begin\s*\{(?:tabular\*?|tabularx|longtable|array)\}.*")
_DROP_CMD_RE = re.compile(
    r"\\(?:label|input|include(?:graphics|pdf)?|usepackage|documentclass|bibliographystyle|"
    r"bibliography|url|href|lstinputlisting|addcontentsline|pagestyle|thispagestyle|"
    r"vspace\*?|hspace\*?|rule|setlength|renewcommand|newcommand|providecommand|definecolor|"
    r"geometry|hypersetup|lstset|graphicspath|setlist|titlespacing\*?|titleformat|"
    r"captionsetup|counterwithout|numberwithin|setcounter|addtocounter|hyphenation|"
    # Аргументы идут в ПРОИЗВОЛЬНОМ порядке и в любом количестве:
    # `\titleformat{\chapter}[hang]{…}{…}{1ex}{}` — обязательный, затем
    # необязательный, затем ещё четыре обязательных. Прежний вид
    # `[опция]?{арг}*[опция]?` обрывался на первой же `[опция]` после `{арг}`,
    # и хвост уезжал в LanguageTool прозой: `1ex` приходил опечаткой в каждом
    # документе с приложениями.
    r"selectlanguage)(?:[ \t]*\n?[ \t]*(?:\[[^\]\n]*\]|\{[^{}]*\}))*"
)
# Окружения, у которых обязательный {…}-аргумент — разметка, а не проза:
# babel-язык (`\begin{otherlanguage}{russian}`) и ширина колонки. Без этого
# «russian» уезжает в LanguageTool как слово и стабильно ловится как опечатка
# в каждом документе с русскоязычным рефератом внутри английского текста.
_ENV_MARKUP_ARG_RE = re.compile(
    r"\\begin\s*\{(?:otherlanguage\*?|multicols\*?|minipage|column)\}[ \t]*(?:\[[^\]\n]*\])?[ \t]*\{[^{}\n]*\}"
)
_BEGIN_END_RE = re.compile(r"\\(?:begin|end)\s*\{[^}]*\}(?:\s*\[[^\]\n]*\])?")
_ITEM_LABELED_RE = re.compile(r"\\item\s*\[([^\]\n]*)\]\s*")
_ITEM_RE = re.compile(r"\\item\b")
_LINEBREAK_RE = re.compile(r"[ \t]*\\\\(?:\[[^\]\n]*\])?")
_AMP_RE = re.compile(r"[ \t]*(?<!\\)&[ \t]*")
_GENERIC_CMD_RE = re.compile(r"\\[a-zA-Z@]+\*?(?:\[[^\]\n]*\])?")
_MATH_RE = re.compile(r"\$[^$\n]*\$")
_ESCAPED_SYMBOL_RE = re.compile(r"\\(?=[^a-zA-Z\n])")
_REPEATED_DOTS_RE = re.compile(r"\.(?:[ \t]*\.)+")


def _drop(m: re.Match[str]) -> str:
    """Delete a match, keeping any newlines it contained."""
    return "\n" * m.group(0).count("\n")


def _n_token(m: re.Match[str]) -> str:
    """Replace a match with a neutral token `N` (a value placeholder).

    When the match is glued to the preceding word (e.g. `документов\\cite{x}`)
    the token is dropped entirely so it does not fuse into `документовN`.
    Newlines inside the match are preserved.
    """
    tail = "\n" * m.group(0).count("\n")
    i = m.start() - 1
    if i >= 0 and (m.string[i].isalnum() or m.string[i] in "_-"):
        return tail
    return "N" + tail


def _keep_title(m: re.Match[str]) -> str:
    """Heading/caption → its text plus a period (terminates the sentence)."""
    return m.group(1) + "."


def _sentence_sep(m: re.Match[str]) -> str:
    """Table cell / linebreak markers become sentence separators, unless the
    preceding text already ends a sentence (avoids `..`)."""
    prev = m.string[: m.start()].rstrip()
    if not prev or prev.endswith("\n") or prev[-1] in ".!?;:—…":
        return " "
    return ". "


def _prepare_text_for_lt(text: str) -> str:
    """Strip LaTeX markup for LanguageTool, preserving the line structure."""
    text = _VERBATIM_ENV_RE.sub(_drop, text)
    text = _COMMENT_RE.sub("", text)
    text = _VERB_RE.sub(_n_token, text)
    text = text.replace("\\ldots", "…")
    text = _PLACEHOLDER_RE.sub(_n_token, text)
    text = _HSE_OPTIONAL_RE.sub("", text)  # its argument is real prose — keep it
    text = text.replace("\\projectname", "Программа")
    text = _HSE_MACRO_RE.sub(_n_token, text)
    text = _REFLIKE_RE.sub(_n_token, text)
    text = _CAPTIONOF_RE.sub(_keep_title, text)
    text = _HEADING_RE.sub(_keep_title, text)
    text = _TABULAR_RE.sub("", text)
    text = _DROP_CMD_RE.sub(_drop, text)
    text = _ENV_MARKUP_ARG_RE.sub("", text)
    text = _BEGIN_END_RE.sub("", text)
    text = _ITEM_LABELED_RE.sub(lambda m: m.group(1) + ": " if m.group(1).strip() else "", text)
    text = _ITEM_RE.sub("", text)
    text = text.replace("\\&", "\x00")
    text = _LINEBREAK_RE.sub(_sentence_sep, text)
    text = _AMP_RE.sub(_sentence_sep, text)
    text = text.replace("\x00", "&")
    text = _MATH_RE.sub("", text)
    text = _GENERIC_CMD_RE.sub("", text)
    text = text.replace("{", "").replace("}", "")
    text = text.replace("~", " ")
    text = _ESCAPED_SYMBOL_RE.sub("", text)
    text = text.replace("|", " ")
    text = _REPEATED_DOTS_RE.sub(".", text)
    return text


_LETTERS_RE = re.compile(r"[^\W\d_]", re.UNICODE)


def _is_markup_artifact(flagged: str) -> bool:
    """True when the flagged fragment carries no real words — only the
    neutral ``N`` filler and/or punctuation.

    Such matches are artifacts of the LaTeX→text preparation (runs of
    placeholder tokens, table-cell separators like ``+ . -``), not findings
    about the author's prose.
    """
    letters = set(_LETTERS_RE.findall(flagged))
    return not letters or letters <= {"N", "n"}


def _ignored(flagged: str, ignore_words: list[str]) -> bool:
    """True when the flagged fragment matches the rule's ignore list.

    Entries are case-insensitive; a trailing `*` makes the entry a prefix
    (covers Russian inflection: `версионирован*` → версионирование/-ия/-ию…).
    """
    token = flagged.strip().lower()
    for entry in ignore_words:
        e = str(entry).lower()
        if e.endswith("*"):
            if token.startswith(e[:-1]):
                return True
        elif token == e:
            return True
    return False


class ExternalCheckEngine(BaseCheckEngine):
    """Runs LanguageTool checks against the document source file via HTTP.

    LanguageTool is auto-managed: the compile/check orchestrator calls
    ``LanguageToolContainerManager.ensure_running()`` before checks run, which
    lazily starts a container on a free local port (installing the image is the
    opt-in — no enable flag, no configurable URL). This engine reads the live
    endpoint from ``manager.current_base_url``; when it's ``None`` (image not
    installed / Docker down / container not up) LanguageTool checks are simply
    skipped. Invoked through a declared ``engine: external`` rule, so it honours
    the normal ``ChecksOverride`` resolution; each match is emitted as
    ``lt:<RULE_ID>`` with the rule's resolved severity and a source location.
    """

    def __init__(self, container_manager: LanguageToolContainerManager, client: httpx.Client) -> None:
        self._manager = container_manager
        self._client = client

    def run(
        self,
        rule: CheckRule,
        severity: CheckSeverity,
        project_folder: Path,
        doc_id: str,
        source_file: str,
        log_content: str | None,  # noqa: ARG002 — LanguageTool reads the source, not the log
        base_dir: str = "",  # noqa: ARG002
    ) -> list[CheckResult]:
        base_url = self._manager.current_base_url
        if not base_url:
            return []

        source_path = self._resolve_source(project_folder, doc_id, source_file)
        if source_path is None:
            logger.warning(
                "external_engine: source file not found",
                doc_id=doc_id,
                source_file=source_file,
            )
            return []
        content = read_text_safe(source_path)
        if not content:
            return []
        # LanguageTool checks the PREPARED text (markup stripped, lines kept),
        # so offsets map back to the same line numbers in the raw source.
        prepared = _prepare_text_for_lt(content)

        url = f"{base_url.rstrip('/')}{_CHECK_PATH}"
        try:
            response = self._client.post(url, data=self._build_data(prepared, rule.params or {}))
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # noqa: BLE001 — LanguageTool is optional; never fail the compile
            logger.warning("external_engine: languagetool request failed", url=url, exc=str(exc))
            return []

        rel_file = self._rel(project_folder, source_path)
        ignore_words = list(rule.params.get("ignore_words") or []) if rule.params else []
        return self._map_matches(payload, prepared, severity, rel_file, ignore_words)

    @staticmethod
    def _build_data(content: str, params: dict[str, Any]) -> dict[str, str]:
        language = str(params.get("language", "auto"))
        data: dict[str, str] = {
            "text": content,
            "language": language,
            "disabledRules": str(params.get("disabled_rules", _DEFAULT_DISABLED_RULES)),
        }
        # Автоопределение языка различает английский и русский, но НЕ различает
        # варианты внутри языка и по умолчанию берёт en-US. Правилу с одним
        # набором проверок на ru- и en-проекты `language` жёстко не задать —
        # зато `preferredVariants` действует только на языки с вариантами:
        # английский станет en-GB, а русскому этот параметр безразличен.
        # LanguageTool отвечает 400, если вариант прислан вместе с явным
        # языком, поэтому отправляем его только в паре с `auto`.
        preferred_variants = params.get("preferred_variants")
        if preferred_variants and language == "auto":
            data["preferredVariants"] = str(preferred_variants)
        level = params.get("level")
        if level:
            data["level"] = str(level)
        enabled_categories = params.get("enabled_categories")
        if enabled_categories:
            data["enabledCategories"] = str(enabled_categories)
        return data

    def _map_matches(
        self,
        payload: Any,
        content: str,
        severity: CheckSeverity,
        rel_file: str,
        ignore_words: list[str] | None = None,
    ) -> list[CheckResult]:
        matches = payload.get("matches", []) if isinstance(payload, dict) else []
        results: list[CheckResult] = []
        for match in matches:
            rule_info = match.get("rule", {}) or {}
            offset = match.get("offset")
            if isinstance(offset, int):
                length = match.get("length")
                flagged = content[offset : offset + length] if isinstance(length, int) else ""
                if flagged and _is_markup_artifact(flagged):
                    continue
                if flagged and ignore_words and _ignored(flagged, ignore_words):
                    continue
            results.append(
                CheckResult(
                    rule_id=f"lt:{rule_info.get('id', 'UNKNOWN')}",
                    severity=severity,
                    message=match.get("message", ""),
                    location=CheckLocation(file=rel_file, line=self._offset_to_line(content, offset)),
                )
            )
        return results

    @staticmethod
    def _resolve_source(project_folder: Path, doc_id: str, source_file: str) -> Path | None:
        # `source_file` is project-relative and already includes the doc subdir
        # (e.g. "vkr/vkr.tex"); fall back to "<doc_id>/<source_file>" for bare
        # names just in case a template declares them that way.
        for candidate in (project_folder / source_file, project_folder / doc_id / source_file):
            if candidate.is_file():
                return candidate
        return None

    @staticmethod
    def _rel(project_folder: Path, source_path: Path) -> str:
        try:
            return str(source_path.relative_to(project_folder))
        except ValueError:
            return source_path.name

    @staticmethod
    def _offset_to_line(content: str, offset: object) -> int | None:
        if not isinstance(offset, int) or offset < 0:
            return None
        return content[:offset].count("\n") + 1
