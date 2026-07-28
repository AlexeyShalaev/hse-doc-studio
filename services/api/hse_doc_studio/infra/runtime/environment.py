"""Где именно исполняется процесс — ОДИН ответ на весь бэкенд.

Раньше на вопрос «я внутри контейнера?» отвечали три независимые реализации:
одна смотрела `/.dockerenv` и cgroup, вторая — `/.dockerenv` и
`/run/.containerenv`, третья не проверяла вовсе и молча считала, что да. Пока
продукт умел ровно один способ запуска, расхождение ничего не стоило. С
появлением мастера первоначальной настройки оно стало бы источником багов, в
которых одна часть приложения считает себя контейнером, а другая — нет, и
пользователь получает то совет править compose-файл, которого у него нет, то
кнопку обновления, обновлять которой нечего.

Режим поставки определяется по КОНТЕЙНЕРУ, а не по наличию собранного
фронтенда. Прежняя проверка («статика есть → значит all-in-one») ошибалась
ровно там, где ошибка дороже всего: локальный запуск с собранной статикой
объявлял себя обновляемым образом.
"""

from __future__ import annotations

import os
import socket
from pathlib import Path
from typing import Literal

DeploymentMode = Literal["all-in-one", "standard", "native"]
"""Как поставлен продукт:

* `all-in-one` — единый образ: и API, и собранный интерфейс внутри контейнера;
  единственный режим, в котором работает обновление одной кнопкой;
* `standard` — контейнер только с API (интерфейс отдаёт кто-то другой);
* `native` — процесс на машине пользователя, без контейнера.
"""

# `/.dockerenv` кладёт сам docker, `/run/.containerenv` — podman. Cgroup — на
# случай рантайма, который не создаёт ни того, ни другого.
_DOCKER_MARKER = Path("/.dockerenv")
_PODMAN_MARKER = Path("/run/.containerenv")
_CGROUP_PATH = Path("/proc/self/cgroup")
_CGROUP_MARKERS = ("docker", "containerd", "kubepods", "libpod")


def in_container() -> bool:
    """Живёт ли процесс внутри контейнера."""
    if _DOCKER_MARKER.exists() or _PODMAN_MARKER.exists():
        return True
    try:
        cgroup = _CGROUP_PATH.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return any(marker in cgroup for marker in _CGROUP_MARKERS)


def self_container_ref() -> str | None:
    """Как назвать САМ этот контейнер в командах докера; None — запуск нативный.

    Внутри контейнера hostname по умолчанию равен его короткому id, и этого
    достаточно и для `docker inspect`, и для `docker network connect`, и как
    DNS-имя внутри пользовательской сети (docker регистрирует короткий id
    алиасом автоматически).
    """
    if not in_container():
        return None
    ref = os.environ.get("HOSTNAME") or socket.gethostname()
    return ref or None


def deployment_mode(static_dir: Path | None) -> DeploymentMode:
    """Режим поставки: сперва контейнер, и только потом — есть ли интерфейс.

    Порядок проверок важен. Наличие собранной статики — свойство СБОРКИ, а не
    способа запуска: она есть и у локального `uvicorn`, поднятого поверх
    собранного фронтенда. Спросив про неё первой, мы объявляли такой запуск
    обновляемым образом, и кнопка «Обновить» уходила искать свой контейнер по
    hostname машины.
    """
    if not in_container():
        return "native"
    return "all-in-one" if static_dir is not None else "standard"
