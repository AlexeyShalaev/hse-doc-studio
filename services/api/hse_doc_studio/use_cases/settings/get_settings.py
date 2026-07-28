from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

from hse_doc_studio.core.repositories import ISettingsRepository
from hse_doc_studio.core.system_capacity import (
    FALLBACK_CONCURRENT_COMPILES,
    FALLBACK_DISK_WARN_GB,
    ISystemCapacityProbe,
    capacity_scaled_defaults,
)

logger = structlog.get_logger()

_DEFAULTS: dict[str, Any] = {
    # "system" follows the OS colour scheme; the web app resolves it to a
    # concrete dark/light theme at paint time. Mirrors the frontend default.
    "theme": "system",
    # Interface (UI) language for chrome, response messages and the agent
    # conversation — INDEPENDENT from a project's document language
    # (`project.lang` / the `set_language` chat tool). One of {"ru", "en"}.
    "interface_language": "ru",
    "default_engine": "xelatex",
    "latex_passes": 3,
    # Максимум ОДНОВРЕМЕННЫХ docker-сборок (texlive-контейнеров). «Собрать
    # всё» ставит лишние сборки в очередь, а не запускает 15 контейнеров разом.
    # Значение здесь — только запасное: реальный дефолт считается от ядер и
    # памяти машины (core/system_capacity.py), см. `capacity_scaled_defaults`.
    "max_concurrent_compiles": FALLBACK_CONCURRENT_COMPILES,
    "latex_flags": None,
    # null = fall back to api.config.settings.compile.image at build time;
    # set by Settings → Образы → "Сделать активным".
    "compile_image": None,
    # Default AI provider+model future agents use. The provider record itself
    # lives in ai_providers.json; here we only store the chosen pair. null =
    # nothing picked yet. `default_ai_model` is scoped to `default_ai_provider_id`.
    "default_ai_provider_id": None,
    "default_ai_model": None,
    # When True, the agent's write/exec tools run without a per-call approval
    # prompt. Defaults to off (safe) — read live by the approval gate.
    "agent_auto_approve_writes": False,
    # Tool names the agent may use. null = all available tools (default); a list
    # restricts the catalog advertised to the model (Configure-Tools UI).
    "agent_enabled_tools": None,
    # Sticky default agent role for new chats: a persona id (+ free-form text for
    # "custom"). null = neutral. Each chat stores its own persona; this is only the
    # value new chats inherit.
    "default_agent_persona": None,
    "default_agent_persona_instructions": None,
    # Ставить вышедшие обновления самостоятельно (фоновая проверка раз в несколько
    # часов). По умолчанию включено: инструмент локальный, и свежая версия здесь
    # выгоднее, чем контроль над моментом. Обновление не начинается, пока идёт
    # сборка или ход агента, а неудачная установка откатывается сама.
    "auto_update": True,
    # Порог (ГБ) для стартового предупреждения «Docker занял много места —
    # почистить?»: баннер показывается, когда освобождаемый объём (cleanable)
    # превышает порог. 0 = предупреждение выключено. Как и лимит сборок, реальный
    # дефолт — доля от объёма диска машины; здесь запасное значение.
    "disk_usage_warn_gb": FALLBACK_DISK_WARN_GB,
}


@dataclass
class GetSettingsOutput:
    settings: dict[str, Any]


class GetSettingsUC:
    def __init__(
        self,
        settings_repo: ISettingsRepository,
        capacity_probe: ISystemCapacityProbe | None = None,
    ) -> None:
        self._settings_repo = settings_repo
        self._capacity_probe = capacity_probe

    async def execute(self) -> GetSettingsOutput:
        stored = self._settings_repo.get()
        # Порядок склейки: статические дефолты → дефолты «по железу» → выбор
        # пользователя. Сохранённое значение всегда сильнее подсчитанного.
        merged = {**_DEFAULTS, **self._capacity_defaults(), **stored}
        return GetSettingsOutput(settings=merged)

    def _capacity_defaults(self) -> dict[str, int]:
        if self._capacity_probe is None:
            return {}
        return capacity_scaled_defaults(self._capacity_probe.detect())
