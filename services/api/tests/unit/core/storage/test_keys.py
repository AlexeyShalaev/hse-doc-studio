from __future__ import annotations

import hashlib

import pytest
from hse_doc_studio.core.storage import InvalidObjectKeyError, blob_key, is_sha256, validate_key


def test__blob_key__valid_sha__sharded_by_first_two_chars() -> None:
    sha = hashlib.sha256(b"x").hexdigest()

    assert blob_key(sha) == f"blobs/{sha[:2]}/{sha}"


@pytest.mark.parametrize("sha", ["", "abc", "A" * 64, "g" * 64, "../" + "a" * 61, "a" * 65])
def test__blob_key__not_a_sha256__refused(sha: str) -> None:
    assert not is_sha256(sha)
    with pytest.raises(InvalidObjectKeyError):
        blob_key(sha)


def test__validate_key__ordinary_key__returned() -> None:
    assert validate_key("artifacts/1b2/pdf/съёмка.pdf") == "artifacts/1b2/pdf/съёмка.pdf"


def test__validate_key__longer_than_1024_bytes__refused() -> None:
    with pytest.raises(InvalidObjectKeyError):
        validate_key("a" * 1025)
