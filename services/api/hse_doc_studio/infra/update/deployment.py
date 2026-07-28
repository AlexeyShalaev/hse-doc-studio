"""Как именно запущено приложение — от этого зависит, умеет ли оно себя обновлять.

Сам ответ живёт в `infra/runtime/environment.py` — там он один на весь бэкенд.
Здесь остаётся только то, что специфично для обновления: быстрый пинг демона
докера, без которого кнопка «Обновить» обещала бы то, чего не будет.
"""

from __future__ import annotations

from hse_doc_studio.infra.docker.cli import docker_available
from hse_doc_studio.infra.runtime.environment import DeploymentMode, deployment_mode, in_container

__all__ = ["DeploymentMode", "deployment_mode", "docker_alive", "in_container"]

_DOCKER_PING_TIMEOUT_SEC = 2.0


async def docker_alive() -> bool:
    """Отвечает ли демон Docker. Никогда не бросает — только True/False.

    Таймаут короче общего: это опрос для интерфейса («О программе», гейт
    самообновления), и заставлять пользователя ждать здесь нечего.
    """
    return await docker_available(timeout=_DOCKER_PING_TIMEOUT_SEC)
