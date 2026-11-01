"""Поля bootstrap трека gitremote: `git_remote` на сервере и `git_server_login` в локальной Студии."""

from __future__ import annotations

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.mode import StudioMode


def git_remote_capabilities() -> dict[str, bool]:
    if settings.mode is StudioMode.local:
        return {"git_remote": False, "git_server_login": True}
    return {"git_remote": settings.git_remote.enabled, "git_server_login": False}
