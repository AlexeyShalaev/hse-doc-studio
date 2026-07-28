#!/usr/bin/env python3
"""Сгенерировать корневой CHANGELOG.md (англ., для GitHub) из курируемых заметок.

Единственный источник правды — `release-notes.json` в корне репозитория (двуязычный,
его же читает приложение при старте). CHANGELOG.md производный: не правьте его руками —
правьте JSON и запускайте `make changelog`.

release-please продолжает бампить версию и ставить тег; заметки ведём в JSON. Поскольку
release-please тоже пишет в CHANGELOG.md (из сообщений коммитов), порядок такой: в
релизном PR добавить запись в `release-notes.json` и прогнать `make changelog` — тогда
в тег уезжает уже курируемый файл. Забыть об этом не даёт `make changelog-check`
(тот же шаг есть в CI).

Зависимостей нет — только stdlib, поэтому `--notes-for` работает в CI без venv.

Использование:
    python scripts/gen_changelog.py                  # перезаписать CHANGELOG.md
    python scripts/gen_changelog.py --check           # ничего не писать, только проверить
    python scripts/gen_changelog.py --new             # завести пустую запись под текущую версию
    python scripts/gen_changelog.py --notes-for 0.2.0 # заметки одной версии в stdout
    python scripts/gen_changelog.py --site ru --out docs/whatsnew/index.md   # страница сайта
    python scripts/gen_changelog.py --site en --out docs-en/whatsnew/index.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
NOTES_PATH = ROOT / "release-notes.json"
OUT_PATH = ROOT / "CHANGELOG.md"
VERSION_PATH = ROOT / "services" / "api" / "hse_doc_studio" / "__init__.py"
# Версия в баннере сайта (docs/overrides/main.html включает этот партиал).
# Пишется вместе с CHANGELOG — то есть обновляется тем же `make changelog`
# в релизном PR, и сайт всегда объявляет актуальный выпуск.
VERSION_PARTIAL_PATH = ROOT / "docs" / "overrides" / "partials" / "latest-version.html"

# Ссылки «сравнить версии» ведут туда же, куда `settings.source_url` в приложении.
REPO_URL = "https://github.com/AlexeyShalaev/hse-doc-studio"

_LANGS = ("ru", "en")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


def current_version() -> str:
    """Версия из `__init__.py` (её бампит release-please) — читаем текстом, без импорта."""
    match = re.search(r'__version__\s*=\s*"([^"]+)"', VERSION_PATH.read_text(encoding="utf-8"))
    return match.group(1) if match else ""


def load_releases() -> list[dict[str, Any]]:
    data = json.loads(NOTES_PATH.read_text(encoding="utf-8"))
    releases = data.get("releases") if isinstance(data, dict) else None
    return releases if isinstance(releases, list) else []


def _header(version: str, date: str, prev: str | None) -> str:
    if prev:
        return f"## [{version}]({REPO_URL}/compare/v{prev}...v{version}) - {date}"
    return f"## {version} - {date}"


def build(releases: list[dict[str, Any]]) -> str:
    lines = [
        "# Changelog",
        "",
        "All notable changes to this project are documented here.",
        "",
        "Generated from `release-notes.json` via `make changelog` — do not edit by hand.",
        "Release notes are hand-written and bilingual (RU/EN); the app shows them in the",
        "selected interface language.",
        "",
    ]
    versions = [str(release["version"]) for release in releases]
    for index, release in enumerate(releases):
        prev = versions[index + 1] if index + 1 < len(versions) else None
        lines.append(_header(versions[index], str(release.get("date") or ""), prev))
        lines.append("")
        lines.extend(f"- {note['en']}" for note in release["notes"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def validate(releases: list[dict[str, Any]]) -> list[str]:
    """Проверить форму JSON. Файл правят руками, и тайпчекера над ним нет."""
    problems: list[str] = []
    seen: set[str] = set()
    order: list[tuple[int, ...]] = []

    for index, release in enumerate(releases):
        where = f"releases[{index}]"
        if not isinstance(release, dict):
            problems.append(f"{where}: expected an object")
            continue
        version = release.get("version")
        if not isinstance(version, str) or not _VERSION_RE.match(version):
            problems.append(f"{where}: `version` must be X.Y.Z, got {version!r}")
            continue
        if version in seen:
            problems.append(f"{where}: duplicate version {version}")
        seen.add(version)
        order.append(tuple(int(part) for part in version.split(".")))

        date = release.get("date")
        if not isinstance(date, str) or not _DATE_RE.match(date):
            problems.append(f"{where} ({version}): `date` must be YYYY-MM-DD, got {date!r}")

        notes = release.get("notes")
        if not isinstance(notes, list) or not notes:
            problems.append(f"{where} ({version}): `notes` must be a non-empty list")
            continue
        for note_index, note in enumerate(notes):
            if not isinstance(note, dict):
                problems.append(f"{where} ({version}) notes[{note_index}]: expected an object")
                continue
            # Пропущенный язык виден только в другой локали интерфейса, где его уже
            # никто не проверяет — ловим здесь.
            for lang in _LANGS:
                if not str(note.get(lang, "")).strip():
                    problems.append(f"{where} ({version}) notes[{note_index}]: missing `{lang}`")

    if order != sorted(order, reverse=True):
        problems.append("releases must be ordered newest-first — the app and CHANGELOG.md rely on it")
    return problems


def check() -> int:
    """Гейт релиза: файл корректен, у текущей версии есть заметки, CHANGELOG.md совпадает."""
    # Сообщения по-английски намеренно: их читают и в CI, и в консоли Windows с
    # кодовой страницей 1251, где кириллица из stderr превращается в мусор.
    releases = load_releases()
    problems = validate(releases)

    version = current_version()
    if version and not any(str(r.get("version")) == version for r in releases):
        problems.append(
            f"no release notes for version {version}: add an entry (ru + en) to "
            f"release-notes.json, then run `make changelog`"
        )
    if not problems:
        # Сверять CHANGELOG.md имеет смысл только на валидных данных — иначе
        # build() упадёт на первой же битой записи.
        expected = build(releases)
        actual = OUT_PATH.read_text(encoding="utf-8") if OUT_PATH.exists() else ""
        if actual != expected:
            problems.append("CHANGELOG.md is out of sync with release-notes.json — run `make changelog`")
        if releases:
            partial = VERSION_PARTIAL_PATH.read_text(encoding="utf-8") if VERSION_PARTIAL_PATH.exists() else ""
            if partial.strip() != str(releases[0]["version"]):
                problems.append(
                    "docs/overrides/partials/latest-version.html is out of sync — run `make changelog`"
                )

    for problem in problems:
        print(f"error: {problem}", file=sys.stderr)  # noqa: T201 — CLI-скрипт
    return 1 if problems else 0


def new_entry() -> int:
    """Завести пустую запись под текущую версию — заготовка для релизного PR.

    Версию берём из `__init__.py`: её уже бампнул release-please в том же PR, где
    заметки и заполняются руками. Пустые `ru`/`en` намеренно не проходят `--check`,
    пока их не написали.
    """
    version = current_version()
    if not version:
        print("error: could not read the current version", file=sys.stderr)  # noqa: T201 — CLI-скрипт
        return 1

    data = json.loads(NOTES_PATH.read_text(encoding="utf-8"))
    releases = data.get("releases") if isinstance(data.get("releases"), list) else []
    if any(str(item.get("version")) == version for item in releases):
        print(f"release-notes.json already has an entry for {version}")  # noqa: T201 — CLI-скрипт
        return 0

    data["releases"] = [
        {
            "version": version,
            "date": datetime.now(UTC).date().isoformat(),
            "notes": [{"ru": "", "en": ""}],
        },
        *releases,
    ]
    NOTES_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(  # noqa: T201 — CLI-скрипт
        f"added an empty entry for {version} to {NOTES_PATH.name} — "
        f"write the notes (ru + en), then run `make changelog`"
    )
    return 0


def notes_for(version: str) -> int:
    """Английские заметки одной версии в stdout — тело GitHub-релиза (см. publish.yml).

    Именно этот текст читает приложение, когда сообщает о ДОСТУПНОМ обновлении: свои
    заметки едут внутри сборки и про новую версию знать не могут.
    """
    release = next((item for item in load_releases() if str(item.get("version")) == version), None)
    if release is None:
        print(f"error: no release notes for version {version}", file=sys.stderr)  # noqa: T201 — CLI-скрипт
        return 1
    for note in release["notes"]:
        print(f"- {note['en']}")  # noqa: T201 — это и есть вывод команды
    return 0


_SITE_TEXT = {
    "ru": {
        "title": "Что нового",
        "description": "Изменения по версиям — курируемые заметки к каждому релизу.",
        "lede": (
            # Лид вставляется в HTML-блок <p class="hds-lede">, где markdown не
            # обрабатывается — ссылка обязана быть готовым тегом <a>.
            "Заметки к релизам пишутся руками и двуязычны — те же тексты приложение "
            "показывает в «О программе». Обновиться одной кнопкой: "
            '<a href="../start/update/">Обновление и удаление</a>.'
        ),
        "compare": "сравнить с предыдущей версией",
    },
    "en": {
        "title": "What's new",
        "description": "Release-by-release changes — curated notes for every version.",
        "lede": (
            "Release notes are hand-written and bilingual — the app shows the same texts "
            'in About. One-click updates: <a href="../start/update/">Updating and uninstalling</a>.'
        ),
        "compare": "compare with the previous version",
    },
}


def build_site(releases: list[dict[str, Any]], lang: str) -> str:
    """Страница «Что нового» для сайта: русская или английская ветка заметок."""
    text = _SITE_TEXT[lang]
    lines = [
        "---",
        f"title: {text['title']}",
        f"description: {text['description']}",
        "---",
        "",
        "<!-- Файл сгенерирован scripts/gen_changelog.py --site — не правьте руками. -->",
        "",
        f"# {text['title']}",
        "",
        f"<p class=\"hds-lede\">{text['lede']}</p>",
        "",
    ]
    versions = [str(release["version"]) for release in releases]
    for index, release in enumerate(releases):
        version = versions[index]
        date = str(release.get("date") or "")
        lines.append(f"## {version} — {date}")
        lines.append("")
        lines.extend(f"- {note[lang]}" for note in release["notes"])
        prev = versions[index + 1] if index + 1 < len(versions) else None
        if prev:
            lines.append("")
            lines.append(f"[{text['compare']} →]({REPO_URL}/compare/v{prev}...v{version})")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def site(lang: str, out: str) -> int:
    releases = load_releases()
    problems = validate(releases)
    if problems:
        for problem in problems:
            print(f"error: {problem}", file=sys.stderr)  # noqa: T201 — CLI-скрипт
        return 1
    out_path = (ROOT / out) if not Path(out).is_absolute() else Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(build_site(releases, lang), encoding="utf-8")
    print(f"wrote {out} ({len(releases)} releases, {lang})")  # noqa: T201 — CLI-скрипт
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="только проверить, ничего не записывая")
    parser.add_argument("--new", action="store_true", help="завести пустую запись под текущую версию")
    parser.add_argument("--notes-for", metavar="VERSION", help="вывести заметки одной версии в stdout")
    parser.add_argument("--site", choices=("ru", "en"), help="сгенерировать страницу «Что нового» для сайта")
    parser.add_argument("--out", metavar="PATH", help="куда писать страницу сайта (вместе с --site)")
    args = parser.parse_args()

    if args.site:
        if not args.out:
            print("error: --site requires --out", file=sys.stderr)  # noqa: T201 — CLI-скрипт
            return 1
        return site(args.site, args.out)
    if args.notes_for:
        return notes_for(args.notes_for)
    if args.new:
        return new_entry()
    if args.check:
        return check()

    releases = load_releases()
    problems = validate(releases)
    if problems:
        for problem in problems:
            print(f"error: {problem}", file=sys.stderr)  # noqa: T201 — CLI-скрипт
        return 1
    OUT_PATH.write_text(build(releases), encoding="utf-8")
    print(f"wrote {OUT_PATH.relative_to(ROOT)} ({len(releases)} releases)")  # noqa: T201 — CLI-скрипт
    if releases:
        VERSION_PARTIAL_PATH.parent.mkdir(parents=True, exist_ok=True)
        VERSION_PARTIAL_PATH.write_text(f"{releases[0]['version']}\n", encoding="utf-8")
        print(f"wrote {VERSION_PARTIAL_PATH.relative_to(ROOT)}")  # noqa: T201 — CLI-скрипт
    return 0


if __name__ == "__main__":
    sys.exit(main())
