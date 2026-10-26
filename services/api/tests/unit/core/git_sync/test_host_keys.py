from __future__ import annotations

import pytest
from hse_doc_studio.core.git_sync.host_keys import (
    is_fingerprint,
    key_fingerprint,
    known_host_pattern,
    normalize_known_port,
    parse_key_fields,
)

# Публичный ключ ed25519 у github.com и его отпечаток, как его печатает страница GitHub.
GITHUB_ED25519 = "AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl"
GITHUB_FINGERPRINT = "SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU"


def test__key_fingerprint__matches_the_published_github_fingerprint() -> None:
    assert key_fingerprint(GITHUB_ED25519) == GITHUB_FINGERPRINT


@pytest.mark.parametrize(
    ("host", "port", "expected"),
    [
        ("github.com", None, "github.com"),
        ("github.com", 22, "github.com"),
        ("ssh.github.com", 443, "[ssh.github.com]:443"),
        ("git.hse.ru", 2222, "[git.hse.ru]:2222"),
    ],
)
def test__known_host_pattern__plain_for_port_22_else_bracketed(host: str, port: int | None, expected: str) -> None:
    assert known_host_pattern(host, port) == expected


def test__normalize_known_port__22_is_the_same_entry_as_no_port() -> None:
    assert normalize_known_port(22) is None
    assert normalize_known_port(None) is None
    assert normalize_known_port(443) == 443


@pytest.mark.parametrize(
    ("text", "expected"),
    [(GITHUB_FINGERPRINT, True), ("SHA256:short", False), ("MD5:aa:bb", False), (GITHUB_FINGERPRINT + "x", False)],
)
def test__is_fingerprint__only_full_sha256(text: str, expected: bool) -> None:
    assert is_fingerprint(text) is expected


@pytest.mark.parametrize(
    ("key_type", "blob"),
    [
        ("ssh-ed25519-cert-v01@openssh.com", GITHUB_ED25519),
        ("ssh-ed25519", "not base64 !!"),
        ("ssh-dss", GITHUB_ED25519),
    ],
)
def test__parse_key_fields__rejects_unknown_types_and_garbage(key_type: str, blob: str) -> None:
    assert parse_key_fields(key_type, blob) is None


def test__parse_key_fields__accepts_a_known_type() -> None:
    assert parse_key_fields("ssh-ed25519", GITHUB_ED25519) == ("ssh-ed25519", GITHUB_ED25519)
