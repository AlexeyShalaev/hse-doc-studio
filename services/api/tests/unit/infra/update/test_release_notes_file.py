from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.enums import Lang
from hse_doc_studio.infra.update.release_notes_file import JsonReleaseNotesRepository

_ONE_RELEASE: dict[str, Any] = {
    "releases": [
        {
            "version": "0.2.0",
            "date": "2026-08-01",
            "notes": [
                {"ru": "Русская заметка", "en": "English note"},
                {"ru": "Вторая", "en": "Second"},
            ],
        }
    ]
}


def _write(tmp_path: Path, payload: Any) -> Path:
    path = tmp_path / "release-notes.json"
    path.write_text(
        payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def test__list__language__returns_notes_in_that_language(tmp_path: Path) -> None:
    repo = JsonReleaseNotesRepository(_write(tmp_path, _ONE_RELEASE))

    (ru,) = repo.list(Lang.ru)
    (en,) = repo.list(Lang.en)

    assert ru.version == "0.2.0"
    assert ru.date == "2026-08-01"
    assert ru.notes == ("Русская заметка", "Вторая")
    assert en.notes == ("English note", "Second")


def test__list__note_missing_the_requested_language__falls_back_instead_of_blanking(tmp_path: Path) -> None:
    # Пустая строка в списке выглядит как баг вёрстки; вторая локаль — как
    # единственное, что вообще есть про этот пункт.
    payload = {"releases": [{"version": "0.2.0", "date": "2026-08-01", "notes": [{"ru": "Только по-русски"}]}]}
    repo = JsonReleaseNotesRepository(_write(tmp_path, payload))

    (entry,) = repo.list(Lang.en)

    assert entry.notes == ("Только по-русски",)


def test__list__file_is_missing__degrades_to_empty(tmp_path: Path) -> None:
    # В образе файл кладётся отдельным COPY. Забыли — приложение обязано
    # подняться, просто без «Что нового».
    repo = JsonReleaseNotesRepository(tmp_path / "nope.json")

    assert repo.list(Lang.ru) == ()


def test__list__broken_json__degrades_to_empty(tmp_path: Path) -> None:
    repo = JsonReleaseNotesRepository(_write(tmp_path, "{ not json"))

    assert repo.list(Lang.ru) == ()


def test__list__malformed_entries__are_skipped_and_the_rest_survive(tmp_path: Path) -> None:
    payload = {
        "releases": [
            {"version": "0.3.0", "date": "2026-09-01", "notes": [{"ru": "Живая", "en": "Alive"}]},
            {"date": "2026-08-01", "notes": [{"ru": "Без версии", "en": "No version"}]},
            {"version": "0.1.0", "notes": "не список"},
            "мусор",
        ]
    }
    repo = JsonReleaseNotesRepository(_write(tmp_path, payload))

    entries = repo.list(Lang.ru)

    assert [entry.version for entry in entries] == ["0.3.0"]


def test__list__file_is_read_once_at_construction(tmp_path: Path) -> None:
    # Провайдер в DI — Scope.APP: файл разбирается на старте приложения, а не на
    # каждый запрос «О программе».
    path = _write(tmp_path, _ONE_RELEASE)
    repo = JsonReleaseNotesRepository(path)
    path.unlink()

    assert len(repo.list(Lang.ru)) == 1


# --- реальный файл репозитория ------------------------------------------------


def test__repository_release_notes_json__is_readable_and_bilingual() -> None:
    # У JSON нет тайпчекера, а `settings.release_notes_file` — это тот путь, по
    # которому файл ищет приложение: проверяем и данные, и разрешение пути.
    repo = JsonReleaseNotesRepository(settings.release_notes_file)

    ru = repo.list(Lang.ru)
    en = repo.list(Lang.en)

    assert ru, f"release-notes.json не прочитался по пути {settings.release_notes_file}"
    assert [entry.version for entry in ru] == [entry.version for entry in en]
    for entry in (*ru, *en):
        assert entry.date, entry.version
        assert entry.notes, entry.version
        assert all(note.strip() for note in entry.notes), entry.version
