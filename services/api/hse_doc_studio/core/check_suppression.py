from __future__ import annotations

import re

# A per-line suppression marker, mirroring eslint-disable-line. Placed as a
# LaTeX comment, so it's git-tracked and moves with the text:
#   \foo{...}                       % hse-noqa            -> suppress ALL on this line
#   \foo{...}                       % hse-noqa: rule-a    -> suppress rule-a only
#   \foo{...}                       % hse-noqa: rule-a, rule-b
# The rule list runs up to the next `%` or end-of-line; multiple markers on one
# line are unioned.
_MARKER = re.compile(r"hse-noqa(?:\s*:\s*([^%\n]*))?", re.IGNORECASE)

_SPLIT = re.compile(r"[,\s]+")


def line_suppresses_rule(line: str, rule_id: str) -> bool:
    """Whether a source line's `% hse-noqa` marker(s) suppress `rule_id`."""
    for match in _MARKER.finditer(line):
        rules = match.group(1)
        if rules is None or not rules.strip():
            return True  # bare `hse-noqa` -> suppress every rule on the line
        if rule_id in {part for part in _SPLIT.split(rules.strip()) if part}:
            return True
    return False
