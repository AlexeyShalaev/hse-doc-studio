"""Готова ли эта установка работать — вопрос, который интерфейс задаёт первым.

Ответ считается на каждый запрос, а не кэшируется на процесс: докер могли
запустить уже после старта приложения, и заставлять пользователя перезапускать
продукт ради одного этого — ровно та невежливость, из-за которой люди бросают
установку на половине.
"""

from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.paths import PathMapping
from hse_doc_studio.core.setup import (
    IDockerHealthProbe,
    ISelfContainerInfo,
    SetupReport,
    assess_docker,
    assess_project_storage,
    build_report,
)
from hse_doc_studio.infra.compile.docker_image_manager import docker_socket_gid


@dataclass
class InspectSetupOutput:
    report: SetupReport


class InspectSetupUC:
    def __init__(
        self,
        docker: IDockerHealthProbe,
        self_info: ISelfContainerInfo,
        paths: PathMapping,
        *,
        in_container: bool,
        host_data_dir: str | None,
    ) -> None:
        self._docker = docker
        self._self_info = self_info
        self._paths = paths
        self._in_container = in_container
        self._host_data_dir = host_data_dir

    async def execute(self) -> InspectSetupOutput:
        alive, reason = await self._docker.check()
        # Спрашиваем про compose только когда демон отвечает: без него ответом
        # будет не «не compose», а «неизвестно», и мастер спрятал бы кнопку зря.
        compose_project = await self._self_info.compose_project() if alive else None
        return InspectSetupOutput(
            report=build_report(
                [
                    assess_docker(
                        alive=alive,
                        reason_code=str(reason) if reason is not None else None,
                        # Прочитать владельца сокета мы можем даже без права им
                        # пользоваться — и тогда подсказка называет точное число
                        # вместо «узнайте gid командой stat».
                        socket_gid=docker_socket_gid(),
                    ),
                    assess_project_storage(
                        in_container=self._in_container,
                        mounts=self._paths.mounts,
                        host_data_dir=self._host_data_dir,
                    ),
                ],
                compose_project=compose_project,
            )
        )
