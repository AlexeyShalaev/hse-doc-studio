from __future__ import annotations

import pytest
from hse_doc_studio.core.enums import RequirementFormatKind
from hse_doc_studio.core.value_objects import RequirementsFormat
from hse_doc_studio.use_cases.chat.tools._requirements_format import (
    describe_format,
    format_from_args,
    summarize_matrix,
)
from tests.unit.use_cases.chat.tools.conftest import _matrix


def test__format_from_args__id_kind__parses_pattern_and_docs_list() -> None:
    fmt = format_from_args({"kind": "id", "id_pattern": r"ТЗ-Ф-\d+", "definition_docs": ["tz", "tp"]})

    assert fmt.kind is RequirementFormatKind.id
    assert fmt.id_pattern == r"ТЗ-Ф-\d+"
    assert fmt.definition_docs == ("tz", "tp")


def test__format_from_args__comma_separated_docs_string__splits_into_tuple() -> None:
    fmt = format_from_args({"kind": "id", "id_pattern": "R-\\d+", "definition_docs": "tz, tp ,"})

    assert fmt.definition_docs == ("tz", "tp")


def test__format_from_args__custom_kind__parses_def_and_ref_patterns() -> None:
    fmt = format_from_args({"kind": "custom", "def_pattern": r"(?P<id>R-\d+)", "ref_pattern": r"(?P<ids>R-\d+)"})

    assert fmt.kind is RequirementFormatKind.custom
    assert fmt.def_pattern == r"(?P<id>R-\d+)"
    assert fmt.ref_pattern == r"(?P<ids>R-\d+)"


def test__format_from_args__unknown_kind__raises_value_error() -> None:
    with pytest.raises(ValueError, match="kind"):
        format_from_args({"kind": "bogus"})


def test__describe_and_summarize__id_format_with_matrix__human_readable_output() -> None:
    fmt = RequirementsFormat(kind=RequirementFormatKind.id, id_pattern=r"R-\d+", definition_docs=("tz",))

    assert "R-\\d+" in describe_format(fmt)
    text = summarize_matrix(_matrix(fmt))
    assert "Требований: 2" in text
    assert "R-01" in text
