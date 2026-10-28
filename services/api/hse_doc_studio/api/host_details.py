"""Сведения об установке (ядро хоста, образ, путь данных, ошибки docker) видит только администратор.

В локальной установке пользователь и есть хозяин машины, прячется только на сервере.
"""

from __future__ import annotations

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.mode import StudioMode


def hides_host_details() -> bool:
    if settings.mode is not StudioMode.server:
        return False
    actor = current_actor()
    return actor is None or not actor.is_instance_admin
