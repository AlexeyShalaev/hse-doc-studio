#!/usr/bin/env python3
"""Линтер контента сайта — три гейта против «немого» протухания.

1. Allowlist CSS-классов: каждый `hds-*`, использованный в docs/{ru,en}/**/*.md,
   обязан существовать в docs/ru/stylesheets/*.css. Ловит опечатки вида `hds-doccrd__title`,
   которые иначе молча рендерятся без стилей.
2. Запрет конкретных дат на всех страницах, кроме «Что нового»: дедлайны меняются
   каждый год — на сайте допустимы только сезоны («обычно — осень»).
3. Запрет захардкоженных чисел пака: «33 документа» и «125 правил» пишутся только
   макросом pack_stats_strip на лендинге — руками их писать нельзя.

Только stdlib — запускается в CI без venv.

Использование:
    python scripts/docs/lint_docs.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DOC_TREES = (ROOT / "docs" / "ru", ROOT / "docs" / "en")
CSS_DIR = ROOT / "docs" / "ru" / "stylesheets"
OVERRIDES_DIR = ROOT / "docs" / "overrides"

_CLASS_USE_RE = re.compile(r'class="([^"]*)"')
_HDS_TOKEN_RE = re.compile(r"\bhds-[a-z0-9_-]+")
_CSS_CLASS_RE = re.compile(r"\.(hds-[a-z0-9_-]+)")

# Конкретные даты: «15 мая», «15.05.2026», «2026-05-15».
_DATE_WORD_RE = re.compile(
    r"\b\d{1,2}\s+(январ|феврал|март|апрел|ма[йя]|июн|июл|август|сентябр|октябр|ноябр|декабр)",
    re.IGNORECASE,
)
_DATE_NUM_RE = re.compile(r"\b\d{2}\.\d{2}\.\d{4}\b|\b\d{4}-\d{2}-\d{2}\b")
_DATE_EN_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}\b"
)

# Числа пака, которые обязаны приходить из макросов.
_PACK_NUMBER_RE = re.compile(
    r"\b\d+\s+(документ\w*|правил\w*|профил\w*|движк\w*|documents?|rules?|profiles?|engines?)",
    re.IGNORECASE,
)
# Файлы, где числам можно жить: генерируемые страницы и страницы с макросами.
_PACK_NUMBER_ALLOW = {"whatsnew"}

# Генерируемая страница «Что нового» — единственная, где даты релизов легальны.
_DATES_ALLOW = {"whatsnew"}


def known_css_classes() -> set[str]:
    classes: set[str] = set()
    for css in CSS_DIR.glob("*.css"):
        classes.update(_CSS_CLASS_RE.findall(css.read_text(encoding="utf-8")))
    # Классы, которые задаются только из шаблонов/JS, но валидны.
    classes.update({"hds-done", "hds-hot"})
    return classes


def md_files() -> list[Path]:
    files: list[Path] = []
    for tree in DOC_TREES:
        if tree.is_dir():
            files.extend(sorted(tree.rglob("*.md")))
    return files


def lint_classes(files: list[Path], known: set[str]) -> list[str]:
    problems: list[str] = []
    sources = list(files)
    if OVERRIDES_DIR.is_dir():
        sources.extend(sorted(OVERRIDES_DIR.rglob("*.html")))
    for path in sources:
        text = path.read_text(encoding="utf-8")
        for match in _CLASS_USE_RE.finditer(text):
            for token in _HDS_TOKEN_RE.findall(match.group(1)):
                if token not in known:
                    rel = path.relative_to(ROOT)
                    line = text[: match.start()].count("\n") + 1
                    problems.append(f"{rel}:{line}: unknown class `{token}` (not in docs/stylesheets/*.css)")
    return problems


def lint_dates(files: list[Path]) -> list[str]:
    problems: list[str] = []
    for path in files:
        rel = path.relative_to(ROOT)
        parts = rel.parts
        if len(parts) >= 4 and parts[2] in _DATES_ALLOW:
            continue
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if _DATE_WORD_RE.search(line) or _DATE_NUM_RE.search(line) or _DATE_EN_RE.search(line):
                problems.append(
                    f"{rel}:{line_no}: concrete date — deadlines change every year, "
                    f"use seasons («обычно — осень») and point to LMS"
                )
    return problems


def lint_pack_numbers(files: list[Path]) -> list[str]:
    problems: list[str] = []
    for path in files:
        rel = path.relative_to(ROOT)
        if len(rel.parts) >= 4 and rel.parts[2] in _PACK_NUMBER_ALLOW:
            continue
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            match = _PACK_NUMBER_RE.search(line)
            if match:
                problems.append(
                    f"{rel}:{line_no}: hardcoded pack number `{match.group(0)}` — "
                    f"use the pack_stats_strip macro instead"
                )
    return problems


def main() -> int:
    files = md_files()
    if not files:
        print("error: no markdown files found", file=sys.stderr)  # noqa: T201 — CLI-скрипт
        return 1
    problems = lint_classes(files, known_css_classes())
    problems += lint_dates(files)
    problems += lint_pack_numbers(files)
    for problem in problems:
        print(f"error: {problem}", file=sys.stderr)  # noqa: T201 — CLI-скрипт
    if not problems:
        print(f"docs lint OK ({len(files)} markdown files)")  # noqa: T201 — CLI-скрипт
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
