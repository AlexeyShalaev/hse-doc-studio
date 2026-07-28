from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from hse_doc_studio.core.update.repositories import IUpdateCheckRepository
from hse_doc_studio.core.update.services import is_newer


@dataclass
class GetUpdateStatusOutput:
    current: str
    latest: str
    available: bool
    checked_at: datetime | None
    feed_enabled: bool
    # Что нового в доступной версии — из того же кэша. Курируемый список
    # (`GET /system/release-notes`) описывает только уже установленные версии.
    latest_date: str
    latest_notes: tuple[str, ...]


class GetUpdateStatusUC:
    """Состояние обновлений по кэшу, БЕЗ обращения к сети.

    Нужен «О программе»: экран открывается на каждом заходе в настройки, и ходить
    оттуда в интернет — лишний трафик и повод для лимита запросов GitHub. Сеть
    трогает только явная кнопка «Проверить обновления» (`CheckUpdatesUC`).
    """

    def __init__(
        self,
        cache: IUpdateCheckRepository,
        current_version: str,
        feed_enabled: bool,
    ) -> None:
        self._cache = cache
        self._current = current_version
        self._feed_enabled = feed_enabled

    async def execute(self) -> GetUpdateStatusOutput:
        cached = self._cache.get()
        newest = cached.releases[0] if cached and cached.releases else None
        latest = newest.version if newest else self._current
        return GetUpdateStatusOutput(
            current=self._current,
            latest=latest,
            available=is_newer(latest, self._current),
            checked_at=cached.checked_at if cached else None,
            feed_enabled=self._feed_enabled,
            latest_date=newest.date if newest else "",
            latest_notes=newest.notes if newest else (),
        )
