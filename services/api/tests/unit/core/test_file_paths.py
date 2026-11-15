from __future__ import annotations

import pytest
from hse_doc_studio.core.file_paths import FilePathProblem, InvalidFilePathError, writable_file_path


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("figure.png", "figure.png"),
        ("vkr/images/рис 1.png", "vkr/images/рис 1.png"),
        ("./vkr//refs.bib", "vkr/refs.bib"),
        ("vkr/images/", "vkr/images"),
        ("a/.hidden-but-allowed", "a/.hidden-but-allowed"),
        (".gitignore", ".gitignore"),
        ("name with #hash?.pdf", "name with #hash?.pdf"),
    ],
)
def test__writable_file_path__accepts_user_paths(raw: str, expected: str) -> None:
    assert writable_file_path(raw) == expected


@pytest.mark.parametrize(
    ("raw", "problem"),
    [
        ("", FilePathProblem.empty),
        ("/", FilePathProblem.empty),
        ("./", FilePathProblem.empty),
        ("/etc/passwd", FilePathProblem.absolute),
        ("../escape.png", FilePathProblem.parent),
        ("vkr/../../escape.png", FilePathProblem.parent),
        ("vkr\\..\\escape.png", FilePathProblem.bad_char),
        ("bad\nname.tex", FilePathProblem.bad_char),
        ("nul\0.png", FilePathProblem.bad_char),
        (".hse-studio/project.json", FilePathProblem.reserved),
        (".HSE-Studio/project.json", FilePathProblem.reserved),
        (".git/hooks/pre-commit", FilePathProblem.reserved),
        ("vkr/.GIT/config", FilePathProblem.reserved),
        ("vkr/.build/vkr.aux", FilePathProblem.reserved),
        ("a" * 256 + ".png", FilePathProblem.too_long),
        ("/".join(["dir"] * 300), FilePathProblem.too_long),
    ],
)
def test__writable_file_path__rejects_unsafe_paths(raw: str, problem: FilePathProblem) -> None:
    with pytest.raises(InvalidFilePathError) as caught:
        writable_file_path(raw)
    assert caught.value.problem is problem
    assert caught.value.message()


def test__invalid_file_path__is_a_value_error_for_old_callers() -> None:
    with pytest.raises(ValueError, match="invalid file path"):
        writable_file_path("../x")
