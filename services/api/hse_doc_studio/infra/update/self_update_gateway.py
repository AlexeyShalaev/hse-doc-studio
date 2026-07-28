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

from hse_doc_studio.infra.ai.agent.run_manager import AgentRunManager
from hse_doc_studio.infra.compile.compile_runner import CompileRunner
from hse_doc_studio.infra.update.deployment import DeploymentMode, docker_alive
from hse_doc_studio.infra.update.update_manager import UpdateManager

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
        compile_runner: CompileRunner,
        agent_runs: AgentRunManager,
        deployment_mode: DeploymentMode,
        image_base: str,
    ) -> None:
        self._update_manager = update_manager
        self._compile_runner = compile_runner
        self._agent_runs = agent_runs
        self._deployment_mode = deployment_mode
        self._image_base = image_base

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
        return self._compile_runner.has_any_active() or self._agent_runs.has_any_active()

    async def start(self, target_version: str) -> bool:
        if not is_valid_version(target_version):
            logger.warning("self-update: refused an invalid version", version=target_version)
            return False
        return await self._update_manager.spawn_self_update(self.target_image(target_version))
