from __future__ import annotations

from uuid import UUID

import pytest
from hse_doc_studio.core.git_sync.credentials import (
    MAX_LABEL_LENGTH,
    MAX_TOKEN_LENGTH,
    normalize_credential_host,
    normalize_label,
    normalize_port,
    normalize_token,
    normalize_username,
    secret_aad,
    ssh_key_comment,
    token_family,
)
from hse_doc_studio.core.git_sync.entities import GitCredentialKind
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError


def _code(exc: pytest.ExceptionInfo[GitSyncError]) -> GitErrorCode:
    return exc.value.code


def test__normalize_label__collapses_whitespace() -> None:
    assert normalize_label("  Рабочий   токен \n") == "Рабочий токен"


@pytest.mark.parametrize("raw", ["", "   ", "x" * (MAX_LABEL_LENGTH + 1), "a\x00b", "a\x07b"])
def test__normalize_label__bad_value__is_credential_invalid(raw: str) -> None:
    with pytest.raises(GitSyncError) as exc:
        normalize_label(raw)

    assert _code(exc) is GitErrorCode.credential_invalid


def test__normalize_credential_host__lowercases_and_punycodes() -> None:
    assert normalize_credential_host(" GitHub.COM ") == "github.com"
    assert normalize_credential_host("гит.рф") == "xn--c1ak4a.xn--p1ai"


@pytest.mark.parametrize("raw", ["", "-oProxyCommand=x", "a b", "host/path", "host:22", "a\nb", "ext::sh"])
def test__normalize_credential_host__bad_value__is_credential_invalid(raw: str) -> None:
    with pytest.raises(GitSyncError) as exc:
        normalize_credential_host(raw)

    assert _code(exc) is GitErrorCode.credential_invalid


def test__normalize_username__blank_means_unset() -> None:
    assert normalize_username(None) is None
    assert normalize_username("   ") is None
    assert normalize_username(" oauth2 ") == "oauth2"


@pytest.mark.parametrize("raw", ["a:b", "a b", "a\nb", "x" * 101])
def test__normalize_username__bad_value__is_credential_invalid(raw: str) -> None:
    with pytest.raises(GitSyncError) as exc:
        normalize_username(raw)

    assert _code(exc) is GitErrorCode.credential_invalid


@pytest.mark.parametrize("port", [0, -1, 65536])
def test__normalize_port__out_of_range__is_credential_invalid(port: int) -> None:
    with pytest.raises(GitSyncError) as exc:
        normalize_port(port)

    assert _code(exc) is GitErrorCode.credential_invalid


def test__normalize_port__valid_or_none__passes() -> None:
    assert normalize_port(None) is None
    assert normalize_port(443) == 443


def test__normalize_token__strips_clipboard_whitespace() -> None:
    assert normalize_token("  ghp_abc123\r\n").reveal() == "ghp_abc123"


@pytest.mark.parametrize("raw", ["", "  ", "a b", "tok\x00en", "токен", "t" * (MAX_TOKEN_LENGTH + 1)])
def test__normalize_token__bad_value__is_credential_invalid_without_echo(raw: str) -> None:
    with pytest.raises(GitSyncError) as exc:
        normalize_token(raw)

    assert _code(exc) is GitErrorCode.credential_invalid
    assert raw.strip() == "" or raw.strip() not in exc.value.detail


@pytest.mark.parametrize(
    ("token", "family"),
    [
        ("github_pat_11ABCDEFG0abcdefghij_klmno", "github_pat"),
        ("ghp_abcdefghijklmnopqrstuvwxyz0123456789", "ghp"),
        ("gho_abcdefghijklmnopqrstuvwxyz0123456789", "gho"),
        ("glpat-abcdefghijklmnopqrst", "glpat"),
        ("gldt-abcdefghijklmnopqrst", "gldt"),
        ("random-token-value", None),
        ("", None),
    ],
)
def test__token_family__returns_prefix_only(token: str, family: str | None) -> None:
    assert token_family(token) == family


def test__secret_aad__binds_id_and_kind() -> None:
    ident = UUID("9a8b7c6d-1e2f-4a3b-8c4d-5e6f7a8b9c0d")

    assert secret_aad(ident, GitCredentialKind.pat) == f"{ident}:pat"
    assert secret_aad(ident, GitCredentialKind.pat) != secret_aad(ident, GitCredentialKind.ssh_key)


def test__ssh_key_comment__is_ascii_slug_of_the_label() -> None:
    assert ssh_key_comment("GitLab ВШЭ, ключ 2") == "hse-doc-studio:gitlab-2"
    assert ssh_key_comment("Привет") == "hse-doc-studio"
