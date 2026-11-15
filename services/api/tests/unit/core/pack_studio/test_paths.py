from __future__ import annotations

import pytest
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.paths import (
    is_registry_path,
    validate_packs_path,
    validate_rel_path,
    version_ref_of,
)


@pytest.mark.parametrize(
    "path",
    [
        "",
        "/etc/passwd",
        "../x",
        "a/../../x",
        "a/./b",
        "a//b",
        "a/",
        "a\\b",
        "a/\x00b",
        "a/\nb",
        ".git/config",
        "pack/.GIT/HEAD",
        "pack/.gitmodules",
        " pack/x",
        "a" * 1025,
        "p/" + "я" * 200,
    ],
)
def test__validate_rel_path__unsafe__is_path_not_allowed(path: str) -> None:
    with pytest.raises(PackStudioError) as caught:
        validate_rel_path(path)

    assert caught.value.code is PackStudioErrorCode.path_not_allowed


def test__validate_rel_path__nfd__is_normalized_to_nfc() -> None:
    assert validate_rel_path("pack/files/ё.tex") == "pack/files/ё.tex"


def test__validate_rel_path__ordinary_pack_path__is_kept() -> None:
    path = "hse-cs-sse/templates/coursework/versions/2026.1.5/files/common/meta.tex.j2"

    assert validate_rel_path(path) == path


@pytest.mark.parametrize(("raw", "expected"), [("packs", "packs"), ("/packs/", "packs"), (".", "."), ("", ".")])
def test__validate_packs_path__normalizes(raw: str, expected: str) -> None:
    assert validate_packs_path(raw) == expected


def test__version_ref_of__inside_version__names_pack_template_version_and_rest() -> None:
    ref = version_ref_of("p/templates/t/versions/2026.1.0/files/a.tex")

    assert ref is not None
    assert (ref.pack, ref.template, ref.version, ref.rest) == ("p", "t", "2026.1.0", "files/a.tex")
    assert ref.dir == "p/templates/t/versions/2026.1.0"


@pytest.mark.parametrize("path", ["p/templates/t/releases.yaml", "p/templates/t/examples/a.yaml", "p/pack.yaml"])
def test__version_ref_of__outside_version__is_none(path: str) -> None:
    assert version_ref_of(path) is None


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("p/templates/t/releases.yaml", True),
        ("p/Templates/t/RELEASES.yaml", True),
        ("p/templates/t/versions/1/releases.yaml", False),
        ("releases.yaml", False),
    ],
)
def test__is_registry_path(path: str, expected: bool) -> None:
    assert is_registry_path(path) is expected
