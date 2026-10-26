from __future__ import annotations

from pathlib import PurePosixPath

import pytest
from hse_doc_studio.core.git_sync.merge.paths import collision_groups, comparison_key, is_safe_entry, is_safe_path
from hypothesis import given, settings
from hypothesis import strategies as st


@pytest.mark.parametrize(
    "path",
    [
        "main.tex",
        "chapters/введение.tex",
        "figures/scheme.png",
        ".hse-studio/project.json",
        ".hse-studio/forms/intro--ivanov.json",
        ".hse-studio/frozen/main.pdf",
        ".gitignore",
        ".github/workflows/ci.yml",
        "a b/c d.tex",
        "...tex",
    ],
)
def test__is_safe_path__ordinary_project_file__is_safe(path: str) -> None:
    assert is_safe_path(path)


@pytest.mark.parametrize(
    "path",
    [
        "",
        "/etc/passwd",
        "../outside.tex",
        "a/../../b",
        "a/./b",
        "a//b",
        "a/",
        "./a",
        "a\\b.tex",
        "C:/Windows/x",
        "a/b:stream",
        "..",
        "...",
        ".. /x",
        "a/.. /b",
        ".git/config",
        "sub/.git/hooks/pre-commit",
        ".GIT/config",
        ".Git /config",
        ".g\u200bit/config",
        "GIT~1/config",
        ".hse-studio/git/HEAD",
        ".HSE-Studio/Git/config",
        ".hse-studio/update/journal.json",
        ".hse-studio/compiles/x/main.pdf",
        ".hse-studio/chats/1.json",
        ".hse-studio/backup/main.tex",
        ".hse-studio/submissions/a.zip",
        "a\x00b",
        "a\nb",
    ],
)
def test__is_safe_path__escaping_or_private_path__is_unsafe(path: str) -> None:
    assert not is_safe_path(path)


def test__is_safe_path__studio_private_name_outside_the_studio_dir__is_safe() -> None:
    assert is_safe_path("update/notes.tex")
    assert is_safe_path("chapters/.hse-studio/git")


@pytest.mark.parametrize(("mode", "safe"), [("100644", True), ("100755", True), ("120000", False), ("160000", False)])
def test__is_safe_entry__symlinks_and_submodules__are_unsafe(mode: str, safe: bool) -> None:
    assert is_safe_entry("main.tex", mode) is safe


def test__is_safe_entry__unsafe_path_with_regular_mode__is_unsafe() -> None:
    assert not is_safe_entry("../x", "100644")


def test__comparison_key__nfd_and_nfc_cyrillic__equal() -> None:
    assert comparison_key("й.tex") == comparison_key("и\u0306.tex")


def test__collision_groups__case_and_normalization_variants__grouped() -> None:
    names = ["Chapter.tex", "chapter.tex", "other.tex", "й.tex", "и\u0306.tex", "ЙОГУРТ.tex"]

    assert collision_groups(names) == [("Chapter.tex", "chapter.tex"), ("и\u0306.tex", "й.tex")]


def test__collision_groups__distinct_names__empty() -> None:
    assert collision_groups(["a.tex", "b.tex", "a/b.tex"]) == []


_DANGEROUS_PARTS = [".", "..", ".git", ".GIT", "git~1", ".hse-studio", "git", "update", "C:", "a\\b", "", " ", "x"]


@settings(max_examples=300, deadline=None)
@given(parts=st.lists(st.sampled_from(_DANGEROUS_PARTS) | st.text(max_size=6), min_size=1, max_size=5))
def test__is_safe_path__fuzz__a_safe_path_never_escapes_or_touches_private_dirs(parts: list[str]) -> None:
    path = "/".join(parts)
    if not is_safe_path(path):
        return
    posix = PurePosixPath(path)
    assert not posix.is_absolute()
    assert all(part not in {"", ".", ".."} for part in path.split("/"))
    lowered = [part.casefold() for part in posix.parts]
    assert ".git" not in lowered
    assert not (lowered[0] == ".hse-studio" and len(lowered) > 1 and lowered[1] in {"git", "update", "backup"})
