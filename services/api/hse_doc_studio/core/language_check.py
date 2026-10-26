from __future__ import annotations

from typing import Protocol


class ILanguageCheckService(Protocol):
    # Орфография и грамматика (LanguageTool): только то, что нужно проверкам.
    # Статус и жизненный цикл контейнера остаются на конкретном менеджере.
    @property
    def current_base_url(self) -> str | None: ...

    async def ensure_running(self, image: str) -> str | None: ...
