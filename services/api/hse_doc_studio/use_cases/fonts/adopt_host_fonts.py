"""Перенести шрифты пользователя к себе — один раз, при первой установке.

Шаблоны просят Times New Roman, Arial и Consolas: так выглядят учебные документы
по ГОСТ. Без них сборка не падает — в преамбуле стоит `\\IfFontExistsTF` со
свободными клонами, — но начертания расходятся с оригиналом, и человек замечает
это уже на распечатке.

Достать их приложение может само: шрифты стоят у пользователя, каталог у каждой
ОС известен, а докер-сокет позволяет туда заглянуть. Просить за этим в настройки
нечего — тем более что до первой сборки никто туда и не зайдёт.

Переносим ТОЛЬКО то, что нужно шаблонам. Каталог шрифтов Windows весит под
гигабайт, и копировать его целиком в папку с работами человек не просил.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from hse_doc_studio.core.fonts.entities import InstalledFont
from hse_doc_studio.core.fonts.repositories import IFontStore, ISystemFontProvider

logger = structlog.get_logger()

# Семейства, которые называет пак. Сравнение по нижнему регистру и по вхождению:
# у одного семейства несколько файлов (обычный, жирный, курсив), а имена внутри
# файла бывают с суффиксами вроде «Times New Roman PS».
WANTED_FAMILIES: tuple[str, ...] = (
    "times new roman",
    "arial",
    "consolas",
    "courier new",
)


@dataclass
class AdoptHostFontsOutput:
    installed: list[InstalledFont]
    # Перенос не понадобился: шрифты уже были или хост их не отдал.
    skipped_reason: str | None = None


class AdoptHostFontsUC:
    def __init__(self, provider: ISystemFontProvider, store: IFontStore) -> None:
        self._provider = provider
        self._store = store

    async def execute(self) -> AdoptHostFontsOutput:
        if self._store.has_fonts():
            # Папка не пуста — значит человек уже что-то выбрал сам, и лезть в
            # неё со своими умолчаниями нельзя.
            return AdoptHostFontsOutput(installed=[], skipped_reason="already_has_fonts")

        available = await self._provider.list_fonts()
        if not available:
            return AdoptHostFontsOutput(installed=[], skipped_reason="host_fonts_unavailable")

        wanted = [f for f in available if _is_wanted(f.family or f.name)]
        installed: list[InstalledFont] = []
        for font in wanted:
            try:
                data = await self._provider.read_font(font.path)
                installed.append(self._store.save_font(font.name, data))
            except (ValueError, OSError) as exc:
                # Один недочитанный файл не повод бросать остальные: без части
                # начертаний документ соберётся, без всех — нет.
                logger.info("host font skipped", font=font.name, exc=str(exc))

        logger.info("host fonts adopted", count=len(installed))
        return AdoptHostFontsOutput(installed=installed)


def _is_wanted(name: str) -> bool:
    lowered = name.lower()
    return any(family in lowered for family in WANTED_FAMILIES)
