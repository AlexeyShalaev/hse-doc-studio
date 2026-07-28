from __future__ import annotations

import pytest
from hse_doc_studio.use_cases.checks.apply_check_fix import ApplyCheckFixUC


@pytest.mark.unit
def test__apply__replaces_on_target_line() -> None:
    content = 'line one\nword "q" word\nline three\n'
    out = ApplyCheckFixUC._apply(content, '"q"', "«q»", line=2)
    assert out == "line one\nword «q» word\nline three\n"


@pytest.mark.unit
def test__apply__only_first_occurrence_on_line() -> None:
    content = "a - b - c\n"
    out = ApplyCheckFixUC._apply(content, " - ", " — ", line=1)
    assert out == "a — b - c\n"


@pytest.mark.unit
def test__apply__preserves_other_lines_and_endings() -> None:
    content = "first\r\nsecond ...\r\nthird\r\n"
    out = ApplyCheckFixUC._apply(content, "...", "…", line=2)
    assert out == "first\r\nsecond …\r\nthird\r\n"


@pytest.mark.unit
def test__apply__missing_on_line__raises() -> None:
    with pytest.raises(ValueError, match="больше не применим"):
        ApplyCheckFixUC._apply("hello world\n", "xyz", "abc", line=1)


@pytest.mark.unit
def test__apply__whole_file_when_no_line() -> None:
    content = "a\nb foo b\nc\n"
    out = ApplyCheckFixUC._apply(content, "foo", "bar", line=None)
    assert "bar" in out


@pytest.mark.unit
def test__apply__missing_in_file__raises() -> None:
    with pytest.raises(ValueError, match="больше не применим"):
        ApplyCheckFixUC._apply("abc\n", "zzz", "q", line=None)


@pytest.mark.unit
def test__apply__line_out_of_range_falls_back_to_whole_file() -> None:
    content = "only line foo\n"
    out = ApplyCheckFixUC._apply(content, "foo", "bar", line=99)
    assert out == "only line bar\n"
