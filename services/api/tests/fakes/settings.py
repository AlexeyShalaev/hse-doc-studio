from __future__ import annotations

from typing import Any


class InMemorySettingsRepository:
    """ISettingsRepository в памяти: отдаёт копию, как файл отдаёт свежий разбор."""

    def __init__(self, stored: dict[str, Any] | None = None) -> None:
        self._data: dict[str, Any] = dict(stored or {})

    async def get(self) -> dict[str, Any]:
        return dict(self._data)

    async def save(self, settings: dict[str, Any]) -> None:
        self._data = dict(settings)
