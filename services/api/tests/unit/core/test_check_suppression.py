from __future__ import annotations

import pytest
from hse_doc_studio.core.check_suppression import line_suppresses_rule


@pytest.mark.parametrize(
    ("line", "rule_id", "expected"),
    [
        (r"\foo % hse-noqa", "any-rule", True),
        (r"\foo % hse-noqa: rule-a", "rule-a", True),
        (r"\foo % hse-noqa: rule-a", "rule-b", False),
        (r"\foo % hse-noqa: rule-a, rule-b", "rule-b", True),
        (r"\foo % hse-noqa: rule-a rule-b", "rule-b", True),
        (r"\foo % hse-noqa: rule-a  % hse-noqa: rule-b", "rule-b", True),
        (r"\foo", "rule-a", False),
        (r"\foo % just a normal comment", "rule-a", False),
        (r"\foo % HSE-NOQA: rule-a", "rule-a", True),
    ],
)
def test__line_suppresses_rule__noqa_variants__matches_expected(line: str, rule_id: str, expected: bool) -> None:
    assert line_suppresses_rule(line, rule_id) is expected
