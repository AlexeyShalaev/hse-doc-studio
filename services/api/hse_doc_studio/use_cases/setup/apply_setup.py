"""Применить выбор пользователя из мастера первоначальной настройки.

Пользователь называет ОДНУ папку на своей машине — в ней будут жить и его
проекты, и настройки, и шрифты. Одна папка вместо трёх настроек выбрана
намеренно: каждая развилка в установке — это место, где можно ошибиться, а
разложить внутри неё подкаталоги приложение умеет само.

Применение — это пересоздание собственного контейнера: примонтировать каталог к
живому контейнеру докер не умеет. Пересоздание идёт тем же механизмом, что и
обновление версии, поэтому у него бесплатно есть и ожидание здоровья, и откат.
"""

from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.paths import looks_absolute
from hse_doc_studio.core.setup import IMountProbe, ISetupApplier, MountProbeResult

# Куда каталог пользователя приезжает внутри контейнера. Значение фиксированное:
# это деталь реализации, а не то, что кому-то нужно настраивать.
DATA_MOUNT_POINT = "/data"


@dataclass
class ApplySetupInput:
    host_path: str
    # Каталог шрифтов на хосте, если пользователь поправил автоопределение.
    fonts_host_path: str | None = None
    # Скачивать ли движок LaTeX фоном после пересоздания.
    prefetch_tex_image: bool = True


@dataclass
class ApplySetupOutput:
    applied: bool
    # Машиночитаемая причина отказа; None — заявка принята и контейнер
    # пересоздаётся прямо сейчас.
    error_code: str | None = None
    probe: MountProbeResult | None = None


class ApplySetupUC:
    def __init__(self, probe: IMountProbe, applier: ISetupApplier) -> None:
        self._probe = probe
        self._applier = applier

    async def execute(self, inp: ApplySetupInput) -> ApplySetupOutput:
        host_path = inp.host_path.strip().replace("\\", "/").rstrip("/") or inp.host_path.strip()
        if not host_path:
            return ApplySetupOutput(applied=False, error_code="empty_path")
        if not looks_absolute(host_path):
            # Самая частая ошибка установки: относительный путь докер принимает
            # за имя тома и молча монтирует пустоту вместо папки пользователя.
            return ApplySetupOutput(applied=False, error_code="not_absolute")

        result = await self._probe.probe(host_path)
        if not result.is_ok:
            return ApplySetupOutput(applied=False, error_code=str(result.status), probe=result)

        fonts_path = (inp.fonts_host_path or "").strip().replace("\\", "/").rstrip("/") or None
        spawned = await self._applier.apply(
            data_host_path=host_path,
            fonts_host_path=fonts_path,
            prefetch_tex_image=inp.prefetch_tex_image,
        )
        if not spawned:
            return ApplySetupOutput(applied=False, error_code="recreate_failed", probe=result)
        return ApplySetupOutput(applied=True, probe=result)
