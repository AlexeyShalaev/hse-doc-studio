"""Параметры развёртывания, от которых зависят сценарии синхронизации: чистые значения, без чтения настроек."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_REMOTE_BRANCH = "main"
DEFAULT_FETCH_INTERVAL_S = 300
MIN_FETCH_INTERVAL_S = 60


@dataclass(frozen=True)
class GitSyncPolicy:
    """`allow_local_remotes` уже учитывает режим: на общем сервере локальные адреса не допускаются."""

    enabled: bool = True
    allow_insecure_http: bool = False
    allow_local_remotes: bool = False
    # Почта служебной подписи: коммиты с ней не приписываются человеку.
    bot_email: str = "bot@hse-studio.local"
