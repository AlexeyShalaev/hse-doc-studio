from __future__ import annotations

import pytest
from hse_doc_studio.core.settings_scope import SETTING_SCOPES, SettingScope, setting_scope
from hse_doc_studio.use_cases.settings.get_settings import _DEFAULTS

# Ключи, которые читаются из настроек, но не входят в _DEFAULTS: у них нет значения по умолчанию.
_UNDEFAULTED_KEYS = {"languagetool_image", "office_convert_image", "office_editor_image"}


def test__scopes__every_default_key_has_a_scope() -> None:
    assert set(_DEFAULTS) <= set(SETTING_SCOPES)


def test__scopes__no_scope_for_a_key_nobody_reads() -> None:
    assert set(SETTING_SCOPES) == set(_DEFAULTS) | _UNDEFAULTED_KEYS


def test__scopes__build_and_service_keys_belong_to_the_installation() -> None:
    for key in ("max_concurrent_compiles", "compile_image", "languagetool_image", "office_editor_image"):
        assert setting_scope(key) is SettingScope.instance


def test__scopes__personal_keys_belong_to_the_user() -> None:
    for key in ("theme", "interface_language", "latex_passes", "agent_enabled_tools"):
        assert setting_scope(key) is SettingScope.user


def test__setting_scope__unknown_key__raises_with_the_key_in_message() -> None:
    with pytest.raises(KeyError, match="no_such_key"):
        setting_scope("no_such_key")
