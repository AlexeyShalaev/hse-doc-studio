from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

from hse_doc_studio.core.repositories import ISettingsRepository
from hse_doc_studio.core.settings_scope import SETTING_SCOPES, SettingScope
from hse_doc_studio.core.system_capacity import ISystemCapacityProbe
from hse_doc_studio.use_cases.settings.get_settings import _DEFAULTS, MACHINE_LOCAL_SETTING_KEYS, GetSettingsUC

logger = structlog.get_logger()

_ALLOWED_KEYS = frozenset(_DEFAULTS.keys()) - MACHINE_LOCAL_SETTING_KEYS


@dataclass
class UpdateSettingsInput:
    patch: dict[str, Any]


@dataclass
class UpdateSettingsOutput:
    settings: dict[str, Any]


class UpdateSettingsUC:
    def __init__(
        self,
        settings_repo: ISettingsRepository,
        capacity_probe: ISystemCapacityProbe | None = None,
    ) -> None:
        self._settings_repo = settings_repo
        # Правка ЛЮБОЙ настройки сохраняет весь склеенный набор, поэтому зонд нужен
        # и здесь: иначе первое же сохранение вморозило бы в config.json запасные
        # константы вместо посчитанных по машине значений.
        self._get_uc = GetSettingsUC(settings_repo, capacity_probe)

    async def execute(self, inp: UpdateSettingsInput) -> UpdateSettingsOutput:
        current_result = await self._get_uc.execute()
        current = current_result.settings

        # Only update known/allowed keys
        unknown_keys = set(inp.patch.keys()) - _ALLOWED_KEYS
        if unknown_keys:
            logger.warning("update_settings: unknown keys ignored", keys=list(unknown_keys))

        allowed_patch = {k: v for k, v in inp.patch.items() if k in _ALLOWED_KEYS}
        merged = {**current, **allowed_patch}
        # Ключ установки, которого нет в хранилище и который не правили, остаётся умолчанием:
        # записывать его нельзя, иначе обычный пользователь упрётся в запрет, а админ зафиксирует умолчания.
        stored = await self._settings_repo.get()
        to_save = {
            k: v
            for k, v in merged.items()
            if k in stored or k in allowed_patch or SETTING_SCOPES.get(k) is not SettingScope.instance
        }
        await self._settings_repo.save(to_save)

        logger.info("settings updated")
        return UpdateSettingsOutput(settings=merged)
