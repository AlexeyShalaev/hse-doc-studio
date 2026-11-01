"""Чтение данных пользователя из каталога локальной Студии форматами её Json-репозиториев."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hse_doc_studio.core.entities import AIProvider
from hse_doc_studio.core.export_import.local_data import LocalUserData, NotTransferred
from hse_doc_studio.core.export_import.serialization import provider_from_export_dict

_PRESENT: tuple[tuple[NotTransferred, str], ...] = (
    (NotTransferred.git_credentials, "git/credentials.json"),
    (NotTransferred.signing_identities, "signing_identities.json"),
    (NotTransferred.agent_personas, "agent_personas.json"),
)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _non_empty(path: Path) -> bool:
    data = _read_json(path)
    return bool(data)


class LocalDataReader:
    def read(self, data_dir: Path) -> LocalUserData:
        unreadable: list[str] = []
        settings: dict[str, Any] = {}
        config = data_dir / "config.json"
        if config.is_file():
            loaded = _read_json(config)
            if isinstance(loaded, dict):
                settings = loaded
            else:
                unreadable.append(config.name)
        providers: list[AIProvider] = []
        listing = data_dir / "ai_providers.json"
        if listing.is_file():
            raw = _read_json(listing)
            if isinstance(raw, list):
                for index, item in enumerate(raw):
                    try:
                        providers.append(provider_from_export_dict(item))
                    except (KeyError, ValueError, TypeError):
                        unreadable.append(f"{listing.name}[{index}]")
            else:
                unreadable.append(listing.name)
        return LocalUserData(
            settings=settings,
            ai_providers=tuple(providers),
            not_transferred=tuple(kind for kind, name in _PRESENT if _non_empty(data_dir / name)),
            unreadable=tuple(unreadable),
        )
