from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import EditFormat
from hse_doc_studio.use_cases.chat._prompt import build_system_prompt
from hse_doc_studio.use_cases.chat.personas import apply_persona, list_personas, persona_prompt


@pytest.mark.unit
def test__persona_prompt__default_and_unknown_are_none() -> None:
    assert persona_prompt(None) is None
    assert persona_prompt("") is None
    assert persona_prompt("default") is None
    assert persona_prompt("does-not-exist") is None


@pytest.mark.unit
def test__persona_prompt__known_returns_text() -> None:
    text = persona_prompt("latex_engineer")
    assert text is not None
    assert "LaTeX" in text


@pytest.mark.unit
def test__persona_prompt__custom_uses_free_form_instructions() -> None:
    assert persona_prompt("custom", "Будь язвительным ревьюером") == "Будь язвительным ревьюером"
    # Empty/whitespace custom text → no block.
    assert persona_prompt("custom", "   ") is None
    assert persona_prompt("custom", None) is None


@pytest.mark.unit
def test__persona_prompt__user_defined_role_resolved_from_map() -> None:
    custom = {"role-123": "Веди себя как нормоконтролёр"}
    assert persona_prompt("role-123", None, custom) == "Веди себя как нормоконтролёр"
    # Unknown id (deleted role) → neutral.
    assert persona_prompt("role-gone", None, custom) is None
    # A built-in preset still wins over the custom map.
    assert "LaTeX" in (persona_prompt("latex_engineer", None, custom) or "")


@pytest.mark.unit
def test__list_personas__includes_default_presets_and_custom() -> None:
    ids = {p.id for p in list_personas()}
    assert ids >= {"default", "custom", "supervisor_critic", "latex_engineer", "committee_member"}
    # Every entry exposes a human label/description for the UI.
    assert all(p.label and p.description for p in list_personas())


@pytest.mark.unit
def test__apply_persona__appends_block_only_when_present() -> None:
    assert apply_persona("BASE", "default") == "BASE"
    assert apply_persona("BASE", None) == "BASE"
    appended = apply_persona("BASE", "methodologist")
    assert appended.startswith("BASE\n\n")
    assert "методист" in appended


def _project(meta: dict[str, object]) -> Project:
    return cast(
        Project,
        SimpleNamespace(
            lock=SimpleNamespace(template_id="vkr", pack_id="hse-cs-se", version="2026.1"),
            lang="ru",
            meta=meta,
            documents=[],
            # team mode: _team_line promta chitaet staffing/authors.
            staffing="solo",
            authors=[],
        ),
    )


@pytest.mark.unit
def test__build_system_prompt__injects_project_meta_persona_when_session_unset() -> None:
    prompt = build_system_prompt(_project({"agent_persona": "supervisor_critic"}), EditFormat.search_replace, None)
    assert "научный руководитель-критик" in prompt


@pytest.mark.unit
def test__build_system_prompt__no_persona_when_absent_or_default() -> None:
    base = build_system_prompt(_project({}), EditFormat.search_replace, None)
    default = build_system_prompt(_project({"agent_persona": "default"}), EditFormat.search_replace, None)
    assert "Роль:" not in base
    assert "Роль:" not in default


@pytest.mark.unit
def test__build_system_prompt__session_persona_overrides_project_meta() -> None:
    # An explicit per-session persona wins over the project-level default.
    prompt = build_system_prompt(
        _project({"agent_persona": "supervisor_critic"}),
        EditFormat.search_replace,
        None,
        persona_id="methodologist",
    )
    assert "методист" in prompt
    assert "научный руководитель-критик" not in prompt


@pytest.mark.unit
def test__build_system_prompt__session_custom_persona_uses_instructions() -> None:
    prompt = build_system_prompt(
        _project({}),
        EditFormat.search_replace,
        None,
        persona_id="custom",
        persona_instructions="Отвечай как придирчивый нормоконтролёр",
    )
    assert "придирчивый нормоконтролёр" in prompt


@pytest.mark.unit
def test__build_system_prompt__resolves_user_defined_role_by_id() -> None:
    prompt = build_system_prompt(
        _project({}),
        EditFormat.search_replace,
        None,
        persona_id="role-xyz",
        custom_personas={"role-xyz": "Роль: дотошный тех.писатель."},
    )
    assert "дотошный тех.писатель" in prompt
