from __future__ import annotations

import pytest
from hse_doc_studio.core.enums import ToolKind
from hse_doc_studio.core.mcp.entities import McpSettings, McpToolGroup, McpToolMeta

_READ = McpToolMeta(name="read_tex", group=McpToolGroup.files, kind=ToolKind.read)
_DELETE = McpToolMeta(name="delete_file", group=McpToolGroup.files, kind=ToolKind.write, dangerous=True)
_ADMIN = McpToolMeta(name="admin_list_users", group=McpToolGroup.admin, kind=ToolKind.read, admin=True)


def test__settings__defaults__disabled_and_admin_group_off() -> None:
    settings = McpSettings()

    assert settings.enabled is False
    assert settings.allows(_READ)
    assert not settings.allows(_ADMIN)


def test__allows__dangerous__only_when_enabled_by_name() -> None:
    assert not McpSettings().allows(_DELETE)
    assert McpSettings(enabled_dangerous=frozenset({"delete_file"})).allows(_DELETE)


def test__allows__disabled_group__hides_the_tool() -> None:
    assert not McpSettings(disabled_groups=frozenset({McpToolGroup.files})).allows(_READ)


def test__allows__disabled_tool__hides_the_tool() -> None:
    assert not McpSettings(disabled_tools=frozenset({"read_tex"})).allows(_READ)


def test__round_trip__to_dict_and_back__is_identity() -> None:
    settings = McpSettings(
        enabled=True,
        disabled_tools=frozenset({"read_tex"}),
        disabled_groups=frozenset(),
        enabled_dangerous=frozenset({"delete_file"}),
    )

    assert McpSettings.from_dict(settings.to_dict()) == settings


@pytest.mark.parametrize("raw", [None, "x", 1, [], {"enabled": "yes"}])
def test__from_dict__garbage__gives_defaults(raw: object) -> None:
    assert McpSettings.from_dict(raw) == McpSettings()


def test__from_dict__unknown_groups_and_non_strings__are_dropped() -> None:
    settings = McpSettings.from_dict({"disabled_groups": ["files", "nope"], "disabled_tools": ["a", 3, ""]})

    assert settings.disabled_groups == frozenset({McpToolGroup.files})
    assert settings.disabled_tools == frozenset({"a"})
