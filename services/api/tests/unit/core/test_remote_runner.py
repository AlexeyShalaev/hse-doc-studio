from __future__ import annotations

import pytest
from hse_doc_studio.core.remote_runner import RemoteRunnerError, RemoteRunnerErrorCode, normalize_server_url


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://studio.example.org", "https://studio.example.org"),
        ("  https://studio.example.org/ ", "https://studio.example.org"),
        ("https://example.org/studio/", "https://example.org/studio"),
        ("http://localhost:8000", "http://localhost:8000"),
        ("http://127.0.0.1:8000/", "http://127.0.0.1:8000"),
        ("http://[::1]:8000", "http://[::1]:8000"),
    ],
)
def test__normalize_server_url__allowed__returns_without_trailing_slash(raw: str, expected: str) -> None:
    assert normalize_server_url(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "studio.example.org",
        "http://studio.example.org",
        "ftp://studio.example.org",
        "https://user:pass@studio.example.org",
        "https://studio.example.org/?token=1",
        "https://studio.example.org/#x",
        "https://",
        "https://studio.example.org:99999",
    ],
)
def test__normalize_server_url__unsafe_or_broken__raises_url_invalid(raw: str) -> None:
    with pytest.raises(RemoteRunnerError) as caught:
        normalize_server_url(raw)

    assert caught.value.code is RemoteRunnerErrorCode.url_invalid
