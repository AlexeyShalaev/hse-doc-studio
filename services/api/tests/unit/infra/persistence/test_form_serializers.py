from __future__ import annotations

import pytest
from hse_doc_studio.core.value_objects import FormState
from hse_doc_studio.infra.persistence.serializers import (
    deserialize_form_state,
    migrate_legacy_ai_usage,
    serialize_form_state,
)


@pytest.mark.unit
def test__form_state__round_trips() -> None:
    state = FormState(
        schema_version=1,
        completed=True,
        answers={"used_ai": "yes", "tools": ["chatgpt"], "pct": 20},
    )
    restored = deserialize_form_state(serialize_form_state(state))
    assert restored == state


@pytest.mark.unit
def test__deserialize_form_state__tolerates_missing_keys() -> None:
    state = deserialize_form_state({})
    assert state.schema_version == 1
    assert state.completed is False
    assert state.answers == {}


@pytest.mark.unit
def test__deserialize_form_state__ignores_non_dict_answers() -> None:
    state = deserialize_form_state({"answers": ["not", "a", "dict"], "completed": True})
    assert state.answers == {}
    assert state.completed is True


@pytest.mark.unit
def test__migrate_legacy_ai_usage__lifts_entries_into_usage_table() -> None:
    legacy = {
        "completed": True,
        "entries": [
            {"tool": "ChatGPT", "usage_type": "text_generation", "scope": "intro"},
            {"tool": "_meta_pct", "usage_type": "30", "scope": None},
            {"tool": "_meta_details", "usage_type": "Использовал для редактуры", "scope": None},
            {"tool": "tool:chatgpt", "usage_type": "", "scope": None},
            {"tool": "use:editing", "usage_type": "", "scope": None},
        ],
    }
    state = migrate_legacy_ai_usage(legacy)

    assert state.completed is True
    assert state.answers["used_ai"] == "yes"
    assert state.answers["pct"] == 30
    assert state.answers["details"] == "Использовал для редактуры"
    assert state.answers["tools"] == ["chatgpt"]
    assert state.answers["uses"] == ["editing"]
    assert state.answers["usage_table"] == [
        {"tool": "ChatGPT", "version": "", "kind": "text_generation", "scope": "intro"}
    ]


@pytest.mark.unit
def test__migrate_legacy_ai_usage__empty_declaration() -> None:
    state = migrate_legacy_ai_usage({"completed": True, "entries": []})
    assert state.completed is True
    assert "used_ai" not in state.answers
    assert state.answers == {}
