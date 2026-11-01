from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol


class ILanguageCheckService(Protocol):
    # Орфография и грамматика (LanguageTool): только то, что нужно проверкам.
    # Статус и жизненный цикл контейнера остаются на конкретном менеджере.
    @property
    def current_base_url(self) -> str | None: ...

    async def ensure_running(self, image: str) -> str | None: ...

    def auth_headers(self) -> Mapping[str, str]:
        """Заголовки запроса к `current_base_url`: у локального контейнера их нет, у прокси сервера токен задачи."""
        ...
