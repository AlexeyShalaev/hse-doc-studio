from __future__ import annotations

import pytest
from hse_doc_studio.core.remote_runner import (
    RemoteRunnerError,
    RemoteRunnerErrorCode,
    cloud_flavor,
    is_local_network_url,
    normalize_server_url,
)


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


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:11434/v1",
        "http://127.0.0.1:1234/v1",
        "http://192.168.1.20:8000/v1",
        "http://10.0.0.5/v1",
        "http://gpu:8000/v1",
        "http://gpu.lan:8000/v1",
        "http://mac.local:1234/v1",
        "http://host.docker.internal:11434/v1",
    ],
)
def test__is_local_network_url__own_network__true(url: str) -> None:
    assert is_local_network_url(url)


@pytest.mark.parametrize("url", ["https://api.openai.com/v1", "https://8.8.8.8/v1", "", "not a url"])
def test__is_local_network_url__public_or_broken__false(url: str) -> None:
    assert not is_local_network_url(url)


@pytest.mark.parametrize(
    ("provider_type", "base_url", "expected"),
    [
        ("ollama", "http://hse-ollama:11434/v1", "ollama"),
        ("openai_compat", "http://localhost:1234/v1", "openai"),
        ("openai_compat", "https://openrouter.ai/api/v1", None),
        ("openai", "", None),
        ("claude", "", None),
    ],
)
def test__cloud_flavor__by_provider_kind_and_address(provider_type: str, base_url: str, expected: str | None) -> None:
    assert cloud_flavor(provider_type, base_url) == expected
