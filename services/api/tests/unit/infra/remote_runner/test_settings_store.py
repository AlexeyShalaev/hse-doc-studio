from __future__ import annotations

import json
import stat
from pathlib import Path

from hse_doc_studio.core.remote_runner import RemoteAiEndpointChoice, RemoteRunnerSettings
from hse_doc_studio.infra.remote_runner.settings_store import SETTINGS_FILE, JsonRemoteRunnerSettingsStore


async def test__load__no_file__returns_defaults(tmp_path: Path) -> None:
    assert await JsonRemoteRunnerSettingsStore(tmp_path).load() == RemoteRunnerSettings()


async def test__save_then_load__round_trips_all_fields(tmp_path: Path) -> None:
    store = JsonRemoteRunnerSettingsStore(tmp_path)
    settings = RemoteRunnerSettings(
        enabled=True,
        server_url="https://studio.example.org",
        name="MacBook Анны",
        concurrency=2,
        yield_to_local=False,
        ai_endpoints=(RemoteAiEndpointChoice(name="ollama", provider_id="p1"),),
    )

    await store.save(settings)

    assert await store.load() == settings


async def test__save__file_is_private(tmp_path: Path) -> None:
    await JsonRemoteRunnerSettingsStore(tmp_path).save(RemoteRunnerSettings(enabled=True))

    mode = stat.S_IMODE((tmp_path / SETTINGS_FILE).stat().st_mode)
    assert mode == 0o600


async def test__load__broken_file__returns_defaults(tmp_path: Path) -> None:
    (tmp_path / SETTINGS_FILE).write_text("{not json", encoding="utf-8")

    assert await JsonRemoteRunnerSettingsStore(tmp_path).load() == RemoteRunnerSettings()


async def test__load__hand_edited_concurrency__is_clamped(tmp_path: Path) -> None:
    (tmp_path / SETTINGS_FILE).write_text(json.dumps({"enabled": True, "concurrency": 40}), encoding="utf-8")

    settings = await JsonRemoteRunnerSettingsStore(tmp_path).load()

    assert settings.concurrency == 4
    assert settings.enabled is True
