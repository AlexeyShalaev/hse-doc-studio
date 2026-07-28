from __future__ import annotations

import pytest
from hse_doc_studio.core.agent.edits import SearchReplaceBlock
from hse_doc_studio.infra.ai.agent.edit_applier import FuzzySearchReplaceApplier


@pytest.mark.unit
def test__applier__exact_match_replaces() -> None:
    applier = FuzzySearchReplaceApplier()
    new, errors = applier.apply("hello world", [SearchReplaceBlock(search="world", replace="there")])
    assert errors == []
    assert new == "hello there"


@pytest.mark.unit
def test__applier__fuzzy_tolerates_minor_drift() -> None:
    applier = FuzzySearchReplaceApplier(threshold=0.8)
    content = "строка один\n\\section{Введение}\nстрока три\n"
    # extra spaces inside braces → not an exact substring, but a close line match
    new, errors = applier.apply(
        content, [SearchReplaceBlock(search="\\section{ Введение }", replace="\\section{Вступление}\n")]
    )
    assert errors == []
    assert "Вступление" in new
    assert "Введение" not in new


@pytest.mark.unit
def test__applier__miss_is_atomic_and_reports_nearest() -> None:
    applier = FuzzySearchReplaceApplier()
    content = "alpha beta gamma"
    new, errors = applier.apply(
        content,
        [
            SearchReplaceBlock(search="alpha", replace="ALPHA"),
            SearchReplaceBlock(search="completely unrelated text that is nowhere", replace="X"),
        ],
    )
    assert len(errors) == 1
    assert "блок #2" in errors[0]
    assert new == content  # atomic: a single miss reverts the whole batch


@pytest.mark.unit
def test__applier__empty_search_fails() -> None:
    applier = FuzzySearchReplaceApplier()
    _, errors = applier.apply("text", [SearchReplaceBlock(search="", replace="x")])
    assert len(errors) == 1
