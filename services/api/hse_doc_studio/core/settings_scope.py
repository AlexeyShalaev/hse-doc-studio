"""Область каждого ключа настроек: пользователь или установка.

Локально обе области лежат в одном config.json. На сервере ключи пользователя живут у
пользователя, а ключи установки общие и меняются только админом, поэтому у каждого ключа
область известна заранее и берётся из этого реестра, а не угадывается по месту вызова.
"""

from __future__ import annotations

from enum import StrEnum

from hse_doc_studio.core.vcs.author import PROFILE_EMAIL_KEY, PROFILE_NAME_KEY

# Откуда взято значение ключа установки; строка с источником env правке из интерфейса не поддаётся.
SOURCE_ADMIN = "admin"
SOURCE_ENV = "env"


class SettingScope(StrEnum):
    user = "user"
    instance = "instance"


SETTING_SCOPES: dict[str, SettingScope] = {
    "theme": SettingScope.user,
    "interface_language": SettingScope.user,
    "default_engine": SettingScope.user,
    "latex_passes": SettingScope.user,
    "latex_flags": SettingScope.user,
    "default_ai_provider_id": SettingScope.user,
    "default_ai_model": SettingScope.user,
    "agent_auto_approve_writes": SettingScope.user,
    "agent_enabled_tools": SettingScope.user,
    "default_agent_persona": SettingScope.user,
    "default_agent_persona_instructions": SettingScope.user,
    "git_fetch_interval_s": SettingScope.user,
    # Профиль автора на сервере берётся из users; ключи остаются машинными, локальными.
    PROFILE_NAME_KEY: SettingScope.user,
    PROFILE_EMAIL_KEY: SettingScope.user,
    "max_concurrent_compiles": SettingScope.instance,
    "compile_image": SettingScope.instance,
    "auto_update": SettingScope.instance,
    "disk_usage_warn_gb": SettingScope.instance,
    "languagetool_image": SettingScope.instance,
    "office_convert_image": SettingScope.instance,
    "office_editor_image": SettingScope.instance,
}


def setting_scope(key: str) -> SettingScope:
    """Область ключа; неизвестный ключ это ошибка программиста, а не данных."""
    try:
        return SETTING_SCOPES[key]
    except KeyError:
        raise KeyError(f"у ключа настроек {key!r} нет области в SETTING_SCOPES") from None
