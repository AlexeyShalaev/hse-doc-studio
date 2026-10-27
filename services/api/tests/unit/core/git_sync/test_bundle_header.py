from __future__ import annotations

import pytest
from hse_doc_studio.core.git_sync.bundle_header import BundleHeader, parse_bundle_header

pytestmark = pytest.mark.unit

_A = "a" * 40
_B = "b" * 40
_C = "c" * 40


def _parse(text: str) -> BundleHeader:
    header = parse_bundle_header(text.encode())
    assert header is not None
    return header


def test__parse__v2_with_one_branch() -> None:
    header = _parse(f"# v2 git bundle\n{_A} refs/heads/master\n\nPACK")

    assert [(h.ref, h.sha, h.branch) for h in header.heads] == [("refs/heads/master", _A, "master")]
    assert (header.prerequisites, header.capabilities) == ((), ())


def test__parse__v3_capabilities_and_prerequisites() -> None:
    header = _parse(
        f"# v3 git bundle\n@object-format=sha1\n@filter=blob:none\n-{_B} first commit\n{_A} refs/heads/main\n\n"
    )

    assert header.capabilities == ("object-format=sha1", "filter=blob:none")
    assert header.prerequisites == (_B,)
    assert [h.branch for h in header.branches] == ["main"]


def test__parse__branches_exclude_other_refs() -> None:
    header = _parse(f"# v2 git bundle\n{_A} HEAD\n{_B} refs/tags/v1\n{_C} refs/heads/dev/x\n\n")

    assert len(header.heads) == 3
    assert [h.branch for h in header.branches] == ["dev/x"]


@pytest.mark.parametrize(
    "text",
    [
        "",
        "not a bundle\n\n",
        f"# v1 git bundle\n{_A} refs/heads/m\n\n",
        f"# v2 git bundle\n{_A} refs/heads/m\n",  # нет пустой строки: заголовок оборван
        "# v2 git bundle\nnot-a-sha refs/heads/m\n\n",
        f"# v2 git bundle\n{_A}\n\n",
        "# v2 git bundle\n-nothex x\n\n",
    ],
)
def test__parse__malformed__is_none(text: str) -> None:
    assert parse_bundle_header(text.encode()) is None


def test__parse__not_utf8__is_none() -> None:
    assert parse_bundle_header(b"# v2 git bundle\n\xff\xfe\n\n") is None


def test__parse__binary_pack_after_the_header__is_not_read() -> None:
    raw = f"# v2 git bundle\n{_A} refs/heads/m\n\n".encode() + b"PACK\x00\xff\xfe\x80"

    header = parse_bundle_header(raw)

    assert header is not None
    assert [h.ref for h in header.heads] == ["refs/heads/m"]


def test__parse__no_refs_at_all__is_an_empty_header() -> None:
    header = _parse("# v2 git bundle\n\n")

    assert (header.heads, header.branches) == ((), ())
