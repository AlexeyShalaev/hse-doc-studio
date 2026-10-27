from __future__ import annotations

import base64
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from hse_doc_studio.core.git_sync.entities import CredentialStatus, GitCredential, GitCredentialKind
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.git_sync.url import RemoteUrl, parse_remote_url
from hse_doc_studio.infra.git_sync.auth_env import DEFAULT_TOKEN_USERNAME, allowed_protocols, build_http_auth

_TOKEN = "ghp_CANARYtokenValue1234567890abcdef"


def _credential(**changes: object) -> GitCredential:
    base: dict[str, object] = {
        "id": uuid4(),
        "kind": GitCredentialKind.pat,
        "label": "Рабочий",
        "host": "github.com",
        "username": None,
        "status": CredentialStatus.unverified,
        "created_at": datetime(2026, 10, 26, tzinfo=timezone.utc),
    }
    base.update(changes)
    return GitCredential(**base)  # type: ignore[arg-type]


def _remote(raw: str = "https://github.com/hse/course.git") -> RemoteUrl:
    return parse_remote_url(raw, allow_http=True, allow_local=True)


def test__build_http_auth__pat__header_scoped_to_exact_host() -> None:
    auth = build_http_auth(_remote(), _credential(), Secret(_TOKEN))

    expected = base64.b64encode(f"{DEFAULT_TOKEN_USERNAME}:{_TOKEN}".encode()).decode()
    assert auth.env == {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
        "GIT_CONFIG_VALUE_0": f"Authorization: Basic {expected}",
    }


def test__build_http_auth__username_from_credential__used_in_basic_pair() -> None:
    auth = build_http_auth(_remote(), _credential(username="oauth2"), Secret(_TOKEN))

    pair = base64.b64decode(auth.env["GIT_CONFIG_VALUE_0"].rsplit(" ", 1)[1]).decode()
    assert pair == f"oauth2:{_TOKEN}"


def test__build_http_auth__port_in_url__port_in_key() -> None:
    remote = _remote("https://git.example.com:8443/team/repo.git")

    auth = build_http_auth(remote, _credential(host="git.example.com"), Secret(_TOKEN))

    assert auth.env["GIT_CONFIG_KEY_0"] == "http.https://git.example.com:8443/.extraheader"


def test__build_http_auth__plain_http__scheme_in_key() -> None:
    remote = _remote("http://git.example.com/team/repo.git")

    auth = build_http_auth(remote, _credential(host="git.example.com"), Secret(_TOKEN))

    assert auth.env["GIT_CONFIG_KEY_0"] == "http.http://git.example.com/.extraheader"


def test__build_http_auth__secrets_to_scrub__token_and_pair() -> None:
    auth = build_http_auth(_remote(), _credential(username="anna"), Secret(_TOKEN))

    assert auth.secrets == (_TOKEN, f"anna:{_TOKEN}")


def test__build_http_auth__other_host__credential_host_mismatch() -> None:
    with pytest.raises(GitSyncError) as raised:
        build_http_auth(_remote("https://evil.example.com/a/b.git"), _credential(), Secret(_TOKEN))

    assert raised.value.code is GitErrorCode.credential_host_mismatch
    assert _TOKEN not in str(raised.value)


def test__build_http_auth__host_case_differs__still_matches() -> None:
    auth = build_http_auth(_remote("https://GitHub.com/a/b.git"), _credential(host="GITHUB.com"), Secret(_TOKEN))

    assert "http.https://github.com/" in auth.env["GIT_CONFIG_KEY_0"]


def test__build_http_auth__ssh_key_credential_for_https__credential_invalid() -> None:
    with pytest.raises(GitSyncError) as raised:
        build_http_auth(_remote(), _credential(kind=GitCredentialKind.ssh_key), Secret("pem"))

    assert raised.value.code is GitErrorCode.credential_invalid


def test__build_http_auth__ssh_remote__credentials_missing() -> None:
    with pytest.raises(GitSyncError) as raised:
        build_http_auth(_remote("ssh://git@github.com/a/b.git"), _credential(), Secret(_TOKEN))

    assert raised.value.code is GitErrorCode.credentials_missing


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://github.com/a/b.git", "https:ssh"),
        ("ssh://git@github.com/a/b.git", "https:ssh"),
        ("http://git.example.com/a/b.git", "https:ssh:http"),
        ("file:///srv/git/b.git", "https:ssh:file"),
    ],
)
def test__allowed_protocols__only_what_the_address_needs(raw: str, expected: str) -> None:
    assert allowed_protocols(_remote(raw)) == expected
