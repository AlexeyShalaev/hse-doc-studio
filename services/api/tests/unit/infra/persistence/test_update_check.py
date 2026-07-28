from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from hse_doc_studio.core.update.entities import ReleaseEntry, UpdateCheckState
from hse_doc_studio.infra.persistence.update_check import (
    MAX_CACHED_RELEASES,
    JsonUpdateCheckRepository,
)

_AT = datetime(2026, 7, 26, 12, 30, tzinfo=UTC)


def test__get__no_file_yet__returns_none(tmp_path: Path) -> None:
    assert JsonUpdateCheckRepository(tmp_path).get() is None


def test__save_then_get__round_trips_every_release_with_its_notes(tmp_path: Path) -> None:
    repo = JsonUpdateCheckRepository(tmp_path)
    state = UpdateCheckState(
        checked_at=_AT,
        releases=(
            ReleaseEntry("1.2.3", "2026-07-26", ("Первая заметка", "Вторая")),
            ReleaseEntry("1.2.2", "2026-07-01", ("Старое",)),
        ),
    )

    repo.save(state)

    restored = repo.get()
    assert restored is not None
    assert restored.checked_at == _AT
    assert restored.releases == state.releases
    assert restored.latest == "1.2.3"


def test__save__long_history__is_capped(tmp_path: Path) -> None:
    # Список версий в UI и так не показывает всю историю, а файл не должен расти
    # без конца: релизов за годы накопятся сотни.
    repo = JsonUpdateCheckRepository(tmp_path)
    releases = tuple(ReleaseEntry(f"1.0.{i}", "", ()) for i in range(MAX_CACHED_RELEASES + 10))

    repo.save(UpdateCheckState(checked_at=_AT, releases=releases))

    restored = repo.get()
    assert restored is not None
    assert len(restored.releases) == MAX_CACHED_RELEASES
    # Обрезаем хвост, а не голову: свежие версии важнее древних.
    assert restored.releases[0].version == "1.0.0"


def test__save__missing_data_dir__creates_it(tmp_path: Path) -> None:
    # Первая проверка обновлений может случиться раньше, чем что-либо ещё запишет
    # в data_dir на свежей установке.
    repo = JsonUpdateCheckRepository(tmp_path / "fresh")

    repo.save(UpdateCheckState(checked_at=_AT, releases=(ReleaseEntry("0.2.0", "", ()),)))

    assert repo.get() is not None


def test__get__corrupted_file__degrades_to_none_instead_of_raising(tmp_path: Path) -> None:
    # Кэш проверки обновлений читается на каждом открытии «О программе»: битый
    # файл (обрыв записи, ручная правка) не должен ронять экран.
    (tmp_path / "update-check.json").write_text("{ not json", encoding="utf-8")

    assert JsonUpdateCheckRepository(tmp_path).get() is None


def test__get__file_without_a_timestamp__degrades_to_none(tmp_path: Path) -> None:
    (tmp_path / "update-check.json").write_text('{"releases": []}', encoding="utf-8")

    assert JsonUpdateCheckRepository(tmp_path).get() is None


def test__get__file_written_by_an_older_version__keeps_the_version_it_knew(tmp_path: Path) -> None:
    # Кэш от сборки, которая хранила только последнюю версию: номер в нём годный,
    # объявлять весь файл битым из-за смены формата — потерять его зря.
    (tmp_path / "update-check.json").write_text(
        '{"latest": "1.2.3", "checked_at": "2026-07-26T12:30:00+00:00", "date": "2026-07-26", "notes": ["Заметка"]}',
        encoding="utf-8",
    )

    restored = JsonUpdateCheckRepository(tmp_path).get()

    assert restored is not None
    assert restored.releases == (ReleaseEntry("1.2.3", "2026-07-26", ("Заметка",)),)
