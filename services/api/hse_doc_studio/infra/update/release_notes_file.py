"""Курируемый двуязычный список изменений из `release-notes.json`.

Заметки пишутся руками и на двух языках: приложение отдаёт их на языке интерфейса
(`GET /system/release-notes`), а корневой CHANGELOG.md генерируется из этого же
файла скриптом `scripts/gen_changelog.py` (`make changelog`).

Данные лежат в JSON, а не в коде: релизов со временем становятся десятки, и держать
их питоновским литералом неудобно — файл правят как текст, отдельно от логики.
Читается один раз при старте (провайдер в DI — `Scope.APP`), потому что меняется
только вместе со сборкой.

Почему не тело GitHub-релиза: его наполняет release-please из сообщений коммитов —
англоязычный `feat(checks): ...` для разработчика, а не «что нового» для студента,
который пишет ВКР. release-please по-прежнему бампит версию и ставит тег; заметки
ведём здесь, а publish.yml кладёт их и в тело релиза (`--notes-for`).

Формат:

    {"releases": [
      {"version": "0.2.0", "date": "2026-08-01",
       "notes": [{"ru": "…", "en": "…"}]}
    ]}

Первая запись — самая свежая. Новый релиз: добавьте запись СВЕРХУ с `ru` и `en` в
каждом пункте, затем `make changelog`. `make changelog-check` (и CI) не даст выпустить
версию, для которой заметок здесь нет, и поймает нарушенный формат.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog

from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.update.entities import ReleaseEntry

logger = structlog.get_logger()


def parse_releases(data: Any) -> tuple[dict[str, Any], ...]:
    """Достать корректные записи о релизах из разобранного JSON.

    Чистая функция — тот же разбор используют и приложение, и валидатор в
    `scripts/gen_changelog.py`. Битые записи отбрасываются молча: строже проверяет
    гейт `--check`, а рантайму важнее показать то, что есть.
    """
    releases = data.get("releases") if isinstance(data, dict) else None
    if not isinstance(releases, list):
        return ()

    valid: list[dict[str, Any]] = []
    for item in releases:
        if not isinstance(item, dict):
            continue
        version = item.get("version")
        notes = item.get("notes")
        if not isinstance(version, str) or not version or not isinstance(notes, list):
            continue
        valid.append(item)
    return tuple(valid)


def localize(release: dict[str, Any], lang: Lang) -> ReleaseEntry:
    """Одна запись → заметки на одном языке."""
    notes: list[str] = []
    for note in release.get("notes") or []:
        if isinstance(note, str):
            notes.append(note)
        elif isinstance(note, dict):
            # Пункт без нужного языка не выкидываем: пустая строка в UI выглядит
            # как ошибка, а вторая локаль — как единственное, что вообще есть.
            text = note.get(lang) or note.get(Lang.ru) or note.get(Lang.en) or ""
            if text:
                notes.append(str(text))
    return ReleaseEntry(
        version=str(release["version"]),
        date=str(release.get("date") or ""),
        notes=tuple(notes),
    )


class JsonReleaseNotesRepository:
    """`IReleaseNotesRepository` над `release-notes.json`.

    Файл читается в конструкторе (то есть при старте приложения) и держится в
    памяти: он неизменен в пределах сборки, а «О программе» открывают часто.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._releases = self._load()

    def _load(self) -> tuple[dict[str, Any], ...]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            # В образе файл кладётся отдельным COPY — если его забыли, приложение
            # обязано работать, просто без «Что нового».
            logger.warning("release-notes.json not found", path=str(self._path))
            return ()
        except (OSError, ValueError) as exc:
            logger.warning("release-notes.json read error", path=str(self._path), exc=str(exc))
            return ()
        releases = parse_releases(data)
        logger.debug("release notes loaded", path=str(self._path), count=len(releases))
        return releases

    def list(self, lang: Lang) -> tuple[ReleaseEntry, ...]:
        return tuple(localize(release, lang) for release in self._releases)
