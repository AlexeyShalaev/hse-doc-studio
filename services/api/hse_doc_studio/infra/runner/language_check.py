"""LanguageTool на раннере: поднимать контейнер он не вправе, внешняя проверка даёт пустой результат."""

from __future__ import annotations


class NoLanguageCheck:
    """`ILanguageCheckService` без сервиса: `ExternalCheckEngine` без адреса ничего не находит."""

    @property
    def current_base_url(self) -> str | None:
        return None

    async def ensure_running(self, image: str) -> str | None:
        return None
