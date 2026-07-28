"""Кто управляет нашим контейнером — мы сами или docker compose.

Различие важно ровно в одном месте, но там оно решающее. Мастер настройки
применяет выбор пересозданием контейнера. Для установки, поднятой одной командой
`docker run`, это окончательный ответ. А для compose-установки — нет: файл
`docker-compose.yml` и `.env` останутся прежними, и первый же
`docker compose up -d` вернёт старую конфигурацию. Пользователь при этом увидит,
что приложение «забыло» выбранную папку, — то самое молчаливое поведение, ради
устранения которого мастер и появился.

Поэтому compose-установке мастер не предлагает кнопку, а показывает, какую
строку поправить.
"""

from __future__ import annotations

from hse_doc_studio.infra.docker.cli import run_docker
from hse_doc_studio.infra.runtime.environment import self_container_ref

_INSPECT_TIMEOUT_S = 5.0
_COMPOSE_PROJECT_LABEL = "com.docker.compose.project"


class DockerSelfInfo:
    """Метки собственного контейнера. Ответ кэшируется: пересоздание убивает процесс."""

    def __init__(self) -> None:
        self._resolved = False
        self._compose_project: str | None = None

    async def compose_project(self) -> str | None:
        """Имя compose-проекта, которым нас подняли; None — не compose."""
        if self._resolved:
            return self._compose_project
        self._resolved = True
        self_ref = self_container_ref()
        if self_ref is None:
            return None
        template = f'{{{{index .Config.Labels "{_COMPOSE_PROJECT_LABEL}"}}}}'
        rc, out, _err = await run_docker(["inspect", "-f", template, self_ref], timeout=_INSPECT_TIMEOUT_S)
        name = out.strip()
        # На отсутствующем ключе docker печатает `<nil>` — непустую строку,
        # которую легко принять за имя проекта.
        if rc == 0 and name and name != "<nil>":
            self._compose_project = name
        return self._compose_project
