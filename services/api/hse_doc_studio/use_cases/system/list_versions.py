from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from hse_doc_studio.core.update.entities import ReleaseEntry
from hse_doc_studio.core.update.repositories import IUpdateCheckRepository
from hse_doc_studio.core.update.services import is_newer, parse_version


@dataclass
class VersionOption:
    version: str
    date: str
    notes: tuple[str, ...]
    installed: bool
    # Новее установленной. Переключение «назад» — это откат, и UI помечает его
    # иначе, чем обновление.
    newer: bool


@dataclass
class ListVersionsOutput:
    current: str
    checked_at: datetime | None
    versions: tuple[VersionOption, ...]


class ListVersionsUC:
    """Версии, на которые можно переключиться, — по кэшу последней проверки.

    Сети здесь нет: список приходит из `POST /system/check-updates` и живёт в
    `data_dir/update-check.json`, поэтому экран версий открывается мгновенно и
    работает офлайн.

    Установленная версия попадает в список всегда, даже если фида ещё не было или
    в нём этого релиза нет (собственная сборка, удалённый релиз): пользователь
    должен видеть, где он находится.
    """

    def __init__(self, cache: IUpdateCheckRepository, current_version: str) -> None:
        self._cache = cache
        self._current = current_version

    async def execute(self) -> ListVersionsOutput:
        cached = self._cache.get()
        releases: list[ReleaseEntry] = list(cached.releases) if cached else []
        if all(release.version != self._current for release in releases):
            releases.append(ReleaseEntry(version=self._current, date="", notes=()))
        releases.sort(key=lambda release: parse_version(release.version), reverse=True)

        return ListVersionsOutput(
            current=self._current,
            checked_at=cached.checked_at if cached else None,
            versions=tuple(
                VersionOption(
                    version=release.version,
                    date=release.date,
                    notes=release.notes,
                    installed=release.version == self._current,
                    newer=is_newer(release.version, self._current),
                )
                for release in releases
            ),
        )
