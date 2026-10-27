from __future__ import annotations

import pytest
from hse_doc_studio.core.vcs.errors import VcsCommandError, VcsInvalidRefError
from hse_doc_studio.core.vcs.refs import validate_ref_name, validate_revision

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "name",
    ["main", "draft-2", "feature/intro", "v1.0", "release_2026", "черновик", "a/b/c", "x@y", "a.b", "-".join("ab")],
)
def test__validate_ref_name__accepts(name: str) -> None:
    assert validate_ref_name(name) == name


@pytest.mark.parametrize(
    "name",
    [
        "",
        "   ",
        "-x",
        "--output=/tmp/x",
        "-",
        "@",
        "HEAD",
        "a b",
        "a\tb",
        "a\nb",
        "a\x7fb",
        "a~1",
        "a^",
        "a:b",
        "a?",
        "a*",
        "a[0]",
        "a\\b",
        "a..b",
        "a@{1}",
        "a.",
        "/a",
        "a/",
        "a//b",
        ".hidden",
        "a/.b",
        "x.lock",
        "a/x.lock/b",
        "a" * 201,
    ],
)
def test__validate_ref_name__rejects(name: str) -> None:
    with pytest.raises(VcsInvalidRefError) as info:
        validate_ref_name(name)
    assert info.value.value == name
    assert isinstance(info.value, VcsCommandError)  # роутеры отвечают на него 400


@pytest.mark.parametrize("rev", ["deadbeef", "HEAD", "HEAD~2", "master", "v1.0^{commit}", "a" * 40])
def test__validate_revision__accepts(rev: str) -> None:
    assert validate_revision(rev) == rev


@pytest.mark.parametrize("rev", ["", "-x", "--output=x", "a\x00b", "a\nb"])
def test__validate_revision__rejects(rev: str) -> None:
    with pytest.raises(VcsInvalidRefError):
        validate_revision(rev)
