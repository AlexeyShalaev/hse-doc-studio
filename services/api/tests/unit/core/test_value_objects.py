from __future__ import annotations

from hse_doc_studio.core.value_objects import CheckLocation


def test__check_location__windows_separators__normalises_to_posix_separators() -> None:
    location = CheckLocation(file="tz\\tz.tex", line=42)

    assert location.file == "tz/tz.tex"
    assert location.line == 42


def test__check_location__posix_path__leaves_unchanged() -> None:
    location = CheckLocation(file="common/preamble.tex")

    assert location.file == "common/preamble.tex"
    assert location.line is None


def test__check_location__nested_windows_path__normalises_to_posix_separators() -> None:
    location = CheckLocation(file="pres\\beamer\\pres.tex", line=1)

    assert location.file == "pres/beamer/pres.tex"
