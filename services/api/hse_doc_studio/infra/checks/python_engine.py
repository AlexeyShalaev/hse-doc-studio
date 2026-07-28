"""Python snippet check engine.

Lets a pack author embed an arbitrary Python check directly into a YAML rule.
Inspired by Authentik's custom policy expressions: the rule provides a small
snippet that receives a `ctx` object exposing a curated mini-API (read files,
glob, count, report violations) and registers findings via `ctx.violation(...)`.

Two ways to supply the code:
  - `params.code`   — inline string (preferred for short rules)
  - `params.script` — path to a `.py` file under the project, relative to the
                       project folder (for longer rules)

Safety model: this is NOT a security sandbox. The pack is user-owned; a rule
author can already drop arbitrary `.tex` into the project. We restrict the
builtins to a reasonable subset and impose a wall-clock timeout so a buggy
rule cannot hang the compile UI, but we do not pretend to defend against a
malicious pack. Treat the snippet like any other code you ship.
"""

from __future__ import annotations

import builtins
import re
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

from hse_doc_studio.core.catalog import CheckRule
from hse_doc_studio.core.enums import CheckSeverity
from hse_doc_studio.core.value_objects import CheckLocation, CheckResult
from hse_doc_studio.infra.checks.base import BaseCheckEngine
from hse_doc_studio.infra.checks.utils import expand_inputs, localized_message, read_text_safe

logger = structlog.get_logger()

_DEFAULT_TIMEOUT_S = 5.0

# Служебные каталоги проекта: артефакты latexmk и внутреннее хранилище студии
# (git-репозиторий «Версий», архив PDF, кэш компиляций). Авторских исходников
# там нет, зато обход у них дорогой — на bind-mount к диску хоста рекурсивный
# `**/*.tex` по ним съедал почти весь таймаут правила ещё до первого чтения.
_SKIP_DIR_NAMES: frozenset[str] = frozenset({".build", ".hse-studio", ".git", "__pycache__"})

# Whitelist of builtins exposed to user snippets. Excludes `open`, `exec`,
# `eval`, `compile`, `__import__`, `globals`, `locals`, `input`, `exit`, etc.
_SAFE_BUILTIN_NAMES: tuple[str, ...] = (
    "abs",
    "all",
    "any",
    "ascii",
    "bin",
    "bool",
    "bytes",
    "callable",
    "chr",
    "complex",
    "dict",
    "divmod",
    "enumerate",
    "filter",
    "float",
    "format",
    "frozenset",
    "hash",
    "hex",
    "id",
    "int",
    "isinstance",
    "issubclass",
    "iter",
    "len",
    "list",
    "map",
    "max",
    "min",
    "next",
    "object",
    "oct",
    "ord",
    "pow",
    "print",
    "range",
    "repr",
    "reversed",
    "round",
    "set",
    "slice",
    "sorted",
    "str",
    "sum",
    "tuple",
    "type",
    "zip",
    "True",
    "False",
    "None",
)


def _compile_glob(pattern: str) -> re.Pattern[str] | None:
    """Транслирует glob (`**/*.tex`, `thesis/*.tex`) в регулярку по posix-пути.

    Своя трансляция, а не `fnmatch`: там `*` перепрыгивает через `/`, и
    `thesis/*.tex` поймал бы `thesis/sub/x.tex`. Здесь семантика как у
    `Path.glob`: `*` — внутри одного сегмента, `**/` — любое их число.
    """
    parts: list[str] = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            parts.append("(?:[^/]+/)*")
            i += 3
        elif pattern.startswith("**", i):
            parts.append(".*")
            i += 2
        elif pattern[i] == "*":
            parts.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            parts.append("[^/]")
            i += 1
        else:
            parts.append(re.escape(pattern[i]))
            i += 1
    try:
        return re.compile("".join(parts) + r"\Z")
    except re.error:
        return None


def _iter_source_files(root: Path) -> Iterator[Path]:
    """Обходит дерево проекта, срезая служебные каталоги (`_SKIP_DIR_NAMES`)."""
    stack = [root]
    while stack:
        try:
            entries = sorted(stack.pop().iterdir())
        except OSError as exc:
            logger.warning("python_engine: iterdir error", exc=str(exc))
            continue
        for entry in entries:
            if entry.is_dir():
                if entry.name not in _SKIP_DIR_NAMES:
                    stack.append(entry)
            elif entry.is_file():
                yield entry


@dataclass
class _Violation:
    message: str
    location: CheckLocation


@dataclass
class CheckContext:
    """Mini-API exposed to a python-engine rule.

    The contract is intentionally tiny — anything more complex belongs in a
    dedicated engine. The snippet calls `ctx.violation(...)` zero or more
    times; whatever it appends to `self.violations` becomes the rule's diags.

    Две области поиска, и выбор между ними — часть смысла правила:
      - `files` / `find` / `count` — по каталогу базы документа: для правил
        «во всём комплекте» (омоглифы, кроссфайловые ссылки);
      - `doc_lines` / `doc_find` / `doc_count` — по графу включений одного
        документа: для правил «про этот документ». Правило запускается на
        КАЖДЫЙ документ, поэтому каталожный поиск и дублирует находки соседей,
        и платит за обход дерева столько раз, сколько документов в проекте.
    """

    params: dict[str, Any]
    project_folder: Path
    doc_id: str
    source_file: str
    log_content: str | None
    # База документа от корня проекта (solo — сам корень, team — `shared/`
    # или папка автора), как у `match_files` в regex/reference-движках.
    base_dir: str = ""
    violations: list[_Violation] = field(default_factory=list)
    # Кэши в пределах одного прогона правила: сниппет часто зовёт `find`
    # несколько раз подряд (по паттерну на вызов), и без кэша каждый вызов
    # заново обходил дерево и перечитывал все файлы.
    _read_cache: dict[str, str] = field(default_factory=dict, repr=False)
    _files_cache: dict[str, list[str]] = field(default_factory=dict, repr=False)
    _doc_lines_cache: list[tuple[str, int, str]] | None = field(default=None, repr=False)

    # ── file access ──────────────────────────────────────────────────────
    def read(self, path: str) -> str:
        """Read a UTF-8 text file relative to the project folder."""
        cached = self._read_cache.get(path)
        if cached is not None:
            return cached
        target = self.project_folder / path
        text = read_text_safe(target) if target.is_file() else ""
        self._read_cache[path] = text
        return text

    def files(self, glob: str = "**/*.tex") -> list[str]:
        """Glob files under the document's base, returning project-relative paths."""
        cached = self._files_cache.get(glob)
        if cached is not None:
            return cached
        matcher = _compile_glob(glob)
        if matcher is None:
            logger.warning("python_engine: files() invalid glob", glob=glob)
            return []
        root = self.project_folder / self.base_dir if self.base_dir else self.project_folder
        found = sorted(
            str(path.relative_to(self.project_folder))
            for path in _iter_source_files(root)
            if matcher.match(path.relative_to(root).as_posix())
        )
        self._files_cache[glob] = found
        return found

    def lines(self, path: str) -> list[str]:
        """Lines of a file (no trailing newlines)."""
        return self.read(path).splitlines()

    def count(self, pattern: str, glob: str = "**/*.tex") -> int:
        """Count regex matches across all files matching the glob."""
        try:
            r = re.compile(pattern)
        except re.error:
            return 0
        total = 0
        for rel in self.files(glob):
            total += len(r.findall(self.read(rel)))
        return total

    def find(self, pattern: str, glob: str = "**/*.tex") -> list[tuple[str, int, str]]:
        """Find lines matching `pattern`, returning (file, lineno, line) tuples."""
        try:
            r = re.compile(pattern)
        except re.error:
            return []
        hits: list[tuple[str, int, str]] = []
        for rel in self.files(glob):
            for lineno, line in enumerate(self.read(rel).splitlines(), start=1):
                if r.search(line):
                    hits.append((rel, lineno, line))
        return hits

    # ── document scope ───────────────────────────────────────────────────
    def doc_lines(self) -> list[tuple[str, int, str]]:
        """Строки ЭТОГО документа: главный .tex плюс вся его \\input-цепочка.

        Отдаёт те же тройки (файл, номер строки, текст), что и `find`, но идёт
        по графу включений, а не по каталогу: общие `common/`-инклюды в набор
        попадают, а соседние документы проекта — нет. Для правила «про один
        документ» это и есть верная область — и заодно единственный дешёвый
        способ: обходятся ~10 файлов вместо всего проекта на каждый документ.
        """
        if self._doc_lines_cache is None:
            self._doc_lines_cache = [
                (line.file, line.line, line.text) for line in expand_inputs(self.project_folder, self.source_file)
            ]
        return self._doc_lines_cache

    def doc_files(self) -> list[str]:
        """Файлы, из которых собран документ (в порядке появления)."""
        return list(dict.fromkeys(file for file, _, _ in self.doc_lines()))

    def doc_find(self, pattern: str) -> list[tuple[str, int, str]]:
        """`find`, но в пределах одного документа (см. `doc_lines`)."""
        try:
            r = re.compile(pattern)
        except re.error:
            return []
        return [(file, lineno, text) for file, lineno, text in self.doc_lines() if r.search(text)]

    def doc_count(self, pattern: str) -> int:
        """`count`, но в пределах одного документа (см. `doc_lines`)."""
        try:
            r = re.compile(pattern)
        except re.error:
            return 0
        return sum(len(r.findall(text)) for _, _, text in self.doc_lines())

    # ── reporting ────────────────────────────────────────────────────────
    def violation(
        self,
        message: str,
        file: str | None = None,
        line: int | None = None,
    ) -> None:
        """Register a violation. Location defaults to the document's source file."""
        loc = CheckLocation(file=file if file is not None else self.source_file, line=line)
        self.violations.append(_Violation(message=str(message), location=loc))

    def ok(self) -> None:
        """No-op marker — useful for readability when a rule explicitly clears."""
        return None


class PythonCheckEngine(BaseCheckEngine):
    """Runs a YAML-embedded Python snippet against the project."""

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
        code = self._load_code(rule, project_folder)
        if code is None:
            # A rule that only defines `script` and points at a missing path
            # is an expected opt-in slot; warn only when both `code` and
            # `script` are absent (real misconfiguration).
            if "code" not in rule.params and "script" not in rule.params:
                logger.warning("python_engine: no code/script in rule", rule_id=rule.id)
            return []

        ctx = CheckContext(
            params=rule.params,
            project_folder=project_folder,
            doc_id=doc_id,
            source_file=source_file,
            log_content=log_content,
            base_dir=base_dir,
        )

        timeout = float(rule.params.get("timeout", _DEFAULT_TIMEOUT_S))
        execution_error: dict[str, BaseException | None] = {"exc": None}

        def _run() -> None:
            try:
                exec(code, self._build_globals(ctx))  # noqa: S102 — opt-in user code
            except BaseException as exc:  # noqa: BLE001 — surface everything
                execution_error["exc"] = exc

        thread = threading.Thread(
            target=_run,
            name=f"python-check:{rule.id}",
            daemon=True,
        )
        thread.start()
        thread.join(timeout=timeout)

        if thread.is_alive():
            return [
                self._diag(
                    rule,
                    severity,
                    source_file,
                    localized_message(
                        rule.params.get("timeout_message"),
                        fallback={
                            "ru": f"Правило {rule.id} превысило таймаут {timeout:g}s.",
                            "en": f"Rule {rule.id} exceeded the timeout of {timeout:g}s.",
                        },
                    ),
                )
            ]

        if execution_error["exc"] is not None:
            exc = execution_error["exc"]
            return [
                self._diag(
                    rule,
                    severity,
                    source_file,
                    localized_message(
                        rule.params.get("error_message"),
                        fallback={
                            "ru": f"Ошибка выполнения правила {rule.id}: {exc}",
                            "en": f"Error while executing rule {rule.id}: {exc}",
                        },
                    ),
                )
            ]

        return [
            CheckResult(
                rule_id=rule.id,
                severity=severity,
                message=v.message,
                location=v.location,
            )
            for v in ctx.violations
        ]

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _load_code(rule: CheckRule, project_folder: Path) -> str | None:
        code = rule.params.get("code")
        if isinstance(code, str) and code.strip():
            return code

        script = rule.params.get("script")
        if isinstance(script, str) and script.strip():
            target = project_folder / script
            if target.is_file():
                return read_text_safe(target)
            # Missing script is an expected state for opt-in user-script slots
            # (e.g. .hse-studio/custom-check.py); debug-log instead of warning.
            logger.debug(
                "python_engine: script not found",
                rule_id=rule.id,
                script=script,
            )
        return None

    @staticmethod
    def _build_globals(ctx: CheckContext) -> dict[str, Any]:
        safe_builtins: dict[str, Any] = {
            name: getattr(builtins, name) for name in _SAFE_BUILTIN_NAMES if hasattr(builtins, name)
        }
        return {
            "__builtins__": safe_builtins,
            "ctx": ctx,
            "re": re,
        }

    @staticmethod
    def _diag(
        rule: CheckRule,
        severity: CheckSeverity,
        source_file: str,
        message: str,
    ) -> CheckResult:
        return CheckResult(
            rule_id=rule.id,
            severity=severity,
            message=message,
            location=CheckLocation(file=source_file, line=None),
        )
