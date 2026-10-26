"""Параметры развёртывания, от которых зависят сценарии синхронизации: чистые значения, без чтения настроек."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_REMOTE_BRANCH = "main"
DEFAULT_FETCH_INTERVAL_S = 300
MIN_FETCH_INTERVAL_S = 60
# Повторная выборка по просьбе интерфейса (открытие проекта, возврат в окно) раньше этого срока git не запускает.
FETCH_DEBOUNCE_S = 15


@dataclass(frozen=True)
class GitSyncPolicy:
    """`allow_local_remotes` уже учитывает режим: на общем сервере локальные адреса не допускаются."""

    enabled: bool = True
    allow_insecure_http: bool = False
    allow_local_remotes: bool = False
    # Почта служебной подписи: коммиты с ней не приписываются человеку.
    bot_email: str = "bot@hse-studio.local"
    # Блоб такого размера (и больше) останавливает отправку до загрузки: хостинги отказывают около 100 МБ.
    large_file_bytes: int = 95_000_000
    # Первая отправка длинной истории идёт дольше обычной; None: обычный срок отправки.
    first_push_timeout_s: float | None = None
