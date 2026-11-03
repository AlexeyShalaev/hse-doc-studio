from __future__ import annotations

import pytest
from hse_doc_studio.core.mcp.errors import McpError, McpErrorCode
from hse_doc_studio.use_cases.mcp.prompts import MCP_PROMPTS, get_prompt


@pytest.mark.parametrize("prompt", MCP_PROMPTS, ids=lambda p: p.name)
def test__render__all_arguments__mentions_them(prompt: object) -> None:
    from hse_doc_studio.use_cases.mcp.prompts import McpPrompt  # noqa: PLC0415

    assert isinstance(prompt, McpPrompt)
    args = {a.name: f"<{a.name}>" for a in prompt.arguments}

    text = prompt.render(args)

    assert all(value in text for value in args.values())


def test__render__missing_argument__is_invalid() -> None:
    with pytest.raises(McpError) as err:
        get_prompt("fix_build").render({"project_id": "p"})

    assert err.value.code is McpErrorCode.invalid_arguments


def test__get_prompt__unknown__not_found() -> None:
    with pytest.raises(McpError) as err:
        get_prompt("nope")

    assert err.value.code is McpErrorCode.not_found
