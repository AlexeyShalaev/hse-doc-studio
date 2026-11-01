"""Локальный режим: правка настроек не замораживает умолчания ключей установки в config.json."""

from __future__ import annotations

import json
from pathlib import Path

from hse_doc_studio.infra.persistence.settings import JsonSettingsRepository
from hse_doc_studio.use_cases.settings.get_settings import GetSettingsUC
from hse_doc_studio.use_cases.settings.update_settings import UpdateSettingsInput, UpdateSettingsUC


async def test__update_settings_uc__local_theme_patch__effective_settings_complete(tmp_path: Path) -> None:
    repo = JsonSettingsRepository(tmp_path)
    out = await UpdateSettingsUC(repo).execute(UpdateSettingsInput(patch={"theme": "dark"}))

    saved = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert saved["theme"] == "dark"
    # Умолчания установки в файл не пишутся, но видимые настройки остаются полными и теми же.
    assert "compile_image" not in saved
    assert (await GetSettingsUC(repo).execute()).settings == out.settings
    assert out.settings["compile_image"] is None


async def test__update_settings_uc__local_instance_key_patched__written(tmp_path: Path) -> None:
    repo = JsonSettingsRepository(tmp_path)
    await UpdateSettingsUC(repo).execute(UpdateSettingsInput(patch={"compile_image": "img:1"}))

    assert json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))["compile_image"] == "img:1"
