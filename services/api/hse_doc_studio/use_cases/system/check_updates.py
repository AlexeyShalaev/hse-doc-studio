from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import structlog

from hse_doc_studio.core.update.entities import UpdateCheckState
from hse_doc_studio.core.update.repositories import IUpdateCheckRepository, IUpdateFeedGateway
from hse_doc_studio.core.update.services import is_newer

logger = structlog.get_logger()


@dataclass
class CheckUpdatesOutput:
    current: str
    latest: str
    available: bool
    # False — фид не ответил (выключен, недоступен, лимит запросов); тогда `latest`
    # взят из кэша прошлой удачной проверки, а `reason` объясняет, почему так.
    checked: bool
    checked_at: datetime | None
    reason: str


class CheckUpdatesUC:
    """Спросить фид релизов о последней версии и сравнить с текущей.

    Удачный ответ кэшируется (`data_dir/update-check.json`) вместе с заметками о
    найденной версии — офлайн-установка продолжает знать об обновлении и после
    перезапуска, а читает его состояние `GetUpdateStatusUC` без обращения к сети.

    Заметки про уже установленные версии сюда не попадают: они локальные и
    курируемые (release-notes.json), их отдаёт `/system/release-notes`.
    """

    def __init__(
        self,
        feed: IUpdateFeedGateway,
        cache: IUpdateCheckRepository,
        current_version: str,
    ) -> None:
        self._feed = feed
        self._cache = cache
        self._current = current_version

    async def execute(self) -> CheckUpdatesOutput:
        probe = await self._feed.probe()

        if probe.checked and probe.latest:
            checked_at = datetime.now(UTC)
            # В кэш кладём ВЕСЬ список версий с заметками: они описывают ЕЩЁ НЕ
            # поставленные версии, поэтому больше на машине их взять неоткуда — и из
            # них же собирается список «на что можно переключиться».
            self._cache.save(UpdateCheckState(checked_at=checked_at, releases=probe.releases))
            logger.info("update check", current=self._current, latest=probe.latest)
            return CheckUpdatesOutput(
                current=self._current,
                latest=probe.latest,
                available=is_newer(probe.latest, self._current),
                checked=True,
                checked_at=checked_at,
                reason="",
            )

        # Либо фид не ответил, либо ответил, но релизов в нём нет (свежий форк).
        # Кэш перезаписывать нечем — отвечаем по последнему известному.
        cached = self._cache.get()
        latest = cached.latest if cached else self._current
        return CheckUpdatesOutput(
            current=self._current,
            latest=latest,
            available=is_newer(latest, self._current),
            checked=probe.checked,
            checked_at=cached.checked_at if cached else None,
            reason=probe.reason,
        )
