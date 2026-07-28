"""Применение настройки = пересоздание собственного контейнера с новым биндом.

Отдельный тонкий адаптер, а не вызов `UpdateManager` из use case: домену не за
чем знать ни про переменные окружения, ни про точку монтирования. Здесь же
собран весь набор правок, который делает выбранную папку рабочей.
"""

from __future__ import annotations

from hse_doc_studio.infra.update.update_manager import UpdateManager
from hse_doc_studio.use_cases.setup.apply_setup import DATA_MOUNT_POINT


class ContainerSetupApplier:
    def __init__(self, updates: UpdateManager) -> None:
        self._updates = updates

    async def apply(
        self,
        *,
        data_host_path: str,
        fonts_host_path: str | None = None,
        prefetch_tex_image: bool = True,
    ) -> bool:
        env = {
            # Где каталог данных виден НАМ.
            "HSE_STUDIO__DATA_DIR": DATA_MOUNT_POINT,
            # И где он лежит на машине пользователя. Без второго значения
            # приложение не сможет отдать папку проекта контейнеру сборки:
            # `docker -v` резолвится демоном против хоста, и внутреннее имя
            # `/data` там означает не то же самое.
            "HSE_STUDIO__HOST_DATA_DIR": data_host_path,
        }
        if not prefetch_tex_image:
            # Галочку сняли — уважаем выбор и после пересоздания: иначе новый
            # контейнер начал бы тянуть пять гигабайт, о которых человек
            # только что сказал «не надо».
            env["HSE_STUDIO__COMPILE__PREFETCH_IMAGE"] = "false"
        if fonts_host_path:
            # Автоопределение каталога шрифтов промахнулось, и пользователь его
            # поправил. Переменная переживает пересоздание, в отличие от
            # настроек: каталог данных на этот момент ещё не подключён.
            env["HSE_STUDIO__FONTS__HOST_DIR"] = fonts_host_path
        return await self._updates.spawn_reconfigure(
            mounts={DATA_MOUNT_POINT: data_host_path},
            env=env,
        )
