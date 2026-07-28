from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import structlog

from hse_doc_studio.core.repositories import ISettingsRepository
from hse_doc_studio.core.update.repositories import ISelfUpdateGateway
from hse_doc_studio.core.update.services import is_newer
from hse_doc_studio.use_cases.system.check_updates import CheckUpdatesUC

logger = structlog.get_logger()

# Ключ настройки; включено по умолчанию (см. use_cases/settings/get_settings.py).
AUTO_UPDATE_SETTING = "auto_update"


class AutoUpdateOutcome(StrEnum):
    disabled = "disabled"  # выключено пользователем
    unsupported = "unsupported"  # эта установка не умеет обновлять сама себя
    busy = "busy"  # идёт сборка или ход агента — ждём следующего тика
    up_to_date = "up_to_date"
    started = "started"
    failed = "failed"  # апдейтер не запустился


@dataclass
class AutoUpdateResult:
    outcome: AutoUpdateOutcome
    target: str = ""


class AutoUpdateUC:
    """Один тик автообновления: проверить фид и, если вышла версия новее, поставить её.

    Порядок проверок выбран так, чтобы ничего лишнего не делать: сначала бесплатные
    решения (выключено / нечем обновляться / занято), и только потом обращение к сети.

    Занятость — это не «отложить навсегда»: пересоздание контейнера убило бы идущую
    сборку или ход агента, поэтому тик просто пропускается, а следующий (через
    несколько часов) застанет систему свободной. Ручное обновление этой проверкой
    не ограничено: там пользователь сам видит, что прерывает.
    """

    def __init__(
        self,
        check_updates: CheckUpdatesUC,
        settings_repo: ISettingsRepository,
        updater: ISelfUpdateGateway,
        current_version: str,
    ) -> None:
        self._check_updates = check_updates
        self._settings_repo = settings_repo
        self._updater = updater
        self._current = current_version

    def _enabled(self) -> bool:
        stored = self._settings_repo.get()
        # Ключа нет (настройки ни разу не сохраняли) → включено, как и дефолт.
        return bool(stored.get(AUTO_UPDATE_SETTING, True))

    async def _blocked(self) -> AutoUpdateOutcome | None:
        """Причина не обновляться прямо сейчас, если она есть."""
        if not self._enabled():
            return AutoUpdateOutcome.disabled
        if not await self._updater.can_self_update():
            return AutoUpdateOutcome.unsupported
        if self._updater.is_busy():
            return AutoUpdateOutcome.busy
        return None

    async def run_once(self) -> AutoUpdateResult:
        blocked = await self._blocked()
        if blocked is not None:
            return AutoUpdateResult(blocked)

        # Ходит в сеть и заодно обновляет кэш версий, которым живут «О программе»
        # и список версий — отдельная проверка для них не нужна.
        result = await self._check_updates.execute()
        target = result.latest
        if not is_newer(target, self._current):
            return AutoUpdateResult(AutoUpdateOutcome.up_to_date)

        # Пока ждали ответ фида, настройку могли выключить, а работу — начать.
        blocked = await self._blocked()
        if blocked is not None:
            return AutoUpdateResult(blocked, target=target)

        logger.info("auto-update: installing", current=self._current, target=target)
        if not await self._updater.start(target):
            logger.warning("auto-update: updater did not start", target=target)
            return AutoUpdateResult(AutoUpdateOutcome.failed, target=target)
        return AutoUpdateResult(AutoUpdateOutcome.started, target=target)
