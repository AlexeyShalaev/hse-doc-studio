"""`ISelfUpdateGateway` поверх Docker: подмена работающего приложения другой версией.

Собирает в одном месте три вопроса, которые всегда идут вместе: умеет ли эта
установка обновляться сама, безопасно ли это прямо сейчас и собственно запуск.
Раньше первые два жили в роутере, из-за чего фоновое автообновление не могло ими
воспользоваться, не потянув за собой слой API.

Механика подмены — в `update_manager.py` (отдельный контейнер-апдейтер, который
переживает пересоздание бэкенда) и `updater.py` (сама подмена с откатом).
"""

from __future__ import annotations

import re

import structlog

from hse_doc_studio.core.jobs.protocols import IJobDispatcher
from hse_doc_studio.core.update.entities import ImageOverlay, OverlayOnUpdate
from hse_doc_studio.infra.ai.agent.run_manager import AgentRunManager
from hse_doc_studio.infra.update.deployment import DeploymentMode, docker_alive
from hse_doc_studio.infra.update.update_manager import UpdateManager
from hse_doc_studio.infra.update.updater import drops_image_overlays, image_overlays

logger = structlog.get_logger()

# Тег релиза — буквы, цифры, точка, дефис, подчёркивание. Заодно закрывает
# инъекцию в имя образа и в команду docker, которые собираются из этой строки.
VERSION_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")


def is_valid_version(version: str) -> bool:
    return VERSION_RE.fullmatch(version) is not None


class DockerSelfUpdateGateway:
    def __init__(
        self,
        update_manager: UpdateManager,
        dispatcher: IJobDispatcher,
        agent_runs: AgentRunManager,
        deployment_mode: DeploymentMode,
        image_base: str,
    ) -> None:
        self._update_manager = update_manager
        self._dispatcher = dispatcher
        self._agent_runs = agent_runs
        self._deployment_mode = deployment_mode
        self._image_base = image_base
        self._overlays: tuple[ImageOverlay, ...] | None = None

    def target_image(self, version: str) -> str:
        # Публикуется ОДИН образ (см. publish.yml): суффикс `/all-in-one` остался
        # от прежней раскладки и превращал обновление в pull несуществующей ссылки.
        return f"{self._image_base}:{version}"

    async def can_self_update(self) -> bool:
        # Только образ all-in-one: подменять один контейнер — это ровно то, что
        # умеет апдейтер. В native-запуске подменять нечего, в standard версий
        # несколько и их согласование — дело compose, а не приложения.
        if self._deployment_mode != "all-in-one":
            return False
        return await docker_alive()

    def is_busy(self) -> bool:
        return self._dispatcher.has_any_active() or self._agent_runs.has_any_active()

    async def image_overlays(self) -> tuple[ImageOverlay, ...]:
        # Привязки контейнера не меняются, пока он жив (пересоздание убивает процесс): один inspect на запуск.
        if self._overlays is not None:
            return self._overlays
        if self._deployment_mode != "all-in-one":
            self._overlays = ()
            return self._overlays
        container = await self._update_manager.inspect_self()
        if container is None:
            return ()  # докер не ответил: спросим в следующий раз
        current_ref = (container.get("Config") or {}).get("Image")
        # Цель обновления всегда опубликованный образ (`target_image`), версия на решение не влияет.
        action = (
            OverlayOnUpdate.drop
            if drops_image_overlays(current_ref, self.target_image("latest"))
            else OverlayOnUpdate.keep
        )
        self._overlays = tuple(
            ImageOverlay(destination=o["destination"], source=o["source"], on_update=action)
            for o in image_overlays(container.get("Mounts"))
        )
        return self._overlays

    async def start(self, target_version: str) -> bool:
        if not is_valid_version(target_version):
            logger.warning("self-update: refused an invalid version", version=target_version)
            return False
        for overlay in await self.image_overlays():
            # Подробности пишет и сам апдейтер, но его журнал живёт в отдельном контейнере.
            logger.warning(
                "self-update: host folder mounted over an image directory",
                destination=overlay.destination,
                source=overlay.source,
                on_update=overlay.on_update.value,
            )
        return await self._update_manager.spawn_self_update(self.target_image(target_version))
