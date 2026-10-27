from __future__ import annotations

import base64
from pathlib import Path

import pytest
from hse_doc_studio.core.git_sync.error_classifier import (
    CLASSIFIER_CODES,
    DETAIL_TAIL_CHARS,
    GitOp,
    Transport,
    classify_git_stderr,
    scrub,
)
from hse_doc_studio.core.git_sync.errors import GitErrorCode

_FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "git_stderr"
_FILES = sorted(_FIXTURES.glob("*.txt"))


def _parts(path: Path) -> tuple[GitErrorCode, GitOp, Transport]:
    code, op, transport, _ = path.stem.split("__", 3)
    return GitErrorCode(code), GitOp(op), Transport(transport)


@pytest.mark.parametrize("path", _FILES, ids=lambda p: p.stem)
def test__classify_git_stderr__captured_stderr__maps_to_code_in_file_name(path: Path) -> None:
    expected, op, transport = _parts(path)

    result = classify_git_stderr(path.read_text(encoding="utf-8"), op=op, transport=transport)

    assert result.code is expected


def test__classify_git_stderr__fixtures__cover_every_code_the_classifier_can_return() -> None:
    covered = {_parts(path)[0] for path in _FILES}

    assert covered == set(CLASSIFIER_CODES)


def test__classify_git_stderr__403_is_auth_failed_on_read_and_forbidden_write_on_push() -> None:
    text = "fatal: unable to access 'https://h/o/r.git/': The requested URL returned error: 403\n"

    assert classify_git_stderr(text, op=GitOp.fetch, transport=Transport.https).code is GitErrorCode.auth_failed
    assert classify_git_stderr(text, op=GitOp.push, transport=Transport.https).code is GitErrorCode.forbidden_write


def test__classify_git_stderr__host_key_text_over_https__is_not_a_host_key_error() -> None:
    text = "Host key verification failed.\n"

    assert classify_git_stderr(text, op=GitOp.fetch, transport=Transport.https).code is GitErrorCode.git_error


def test__classify_git_stderr__changed_key__wins_over_unknown_key() -> None:
    text = "WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!\nHost key verification failed.\n"

    assert classify_git_stderr(text, op=GitOp.fetch, transport=Transport.ssh).code is GitErrorCode.host_key_changed


def test__classify_git_stderr__saml_403__is_sso_not_auth() -> None:
    text = "remote: Resource protected by organization SAML enforcement.\nThe requested URL returned error: 403\n"

    assert classify_git_stderr(text, op=GitOp.push, transport=Transport.https).code is GitErrorCode.sso_required


def test__classify_git_stderr__localized_git_output__falls_back_to_git_error() -> None:
    text = "fatal: Не удалось определить адрес хоста\n"

    result = classify_git_stderr(text, op=GitOp.fetch, transport=Transport.https)

    assert result.code is GitErrorCode.git_error
    assert result.detail == text.strip()


def test__classify_git_stderr__empty_stderr__is_git_error_with_empty_detail() -> None:
    result = classify_git_stderr("", op=GitOp.fetch, transport=Transport.https)

    assert result.code is GitErrorCode.git_error
    assert result.detail == ""


def test__classify_git_stderr__detail__keeps_only_the_last_400_chars() -> None:
    text = "x" * 1000 + "THE-END"

    result = classify_git_stderr(text, op=GitOp.fetch, transport=Transport.https)

    assert len(result.detail) == DETAIL_TAIL_CHARS
    assert result.detail.endswith("THE-END")


def test__classify_git_stderr__detail__never_carries_the_known_secret() -> None:
    token = "glpat-AbCdEfGhIjKlMnOpQrSt"
    text = f"fatal: unable to access 'https://oauth2:{token}@gitlab.com/g/p.git/': weird failure\n"

    result = classify_git_stderr(text, op=GitOp.fetch, transport=Transport.https, secrets=[token])

    assert token not in result.detail


_CANARY = "s3cr3t-CANARY-t0ken-9f8e7d6c5b4a"


def _b64(value: str) -> str:
    return base64.b64encode(value.encode()).decode()


@pytest.mark.parametrize(
    "text",
    [
        f"token {_CANARY} leaked",
        f"https://{_CANARY}@github.com/o/r.git",
        f"https://user:{_CANARY}@github.com/o/r.git",
        f"fatal: Authentication failed for 'https://x-access-token:{_CANARY}@github.com/o/r.git/'",
        f"Authorization: Basic {_b64(f'user:{_CANARY}')}",
        f"authorization: bearer {_CANARY}",
        f"http.https://github.com/.extraheader=AUTHORIZATION: basic {_b64(f'x:{_CANARY}')}",
        f"Proxy-Authorization: Basic {_CANARY}",
        f"basic {_b64(_CANARY)}",
        f"basic {_b64(f':{_CANARY}').rstrip('=')}",
    ],
)
def test__scrub__known_secret__never_survives(text: str) -> None:
    assert _CANARY not in scrub(text, [_CANARY])
    assert _b64(_CANARY).rstrip("=") not in scrub(text, [_CANARY])


@pytest.mark.parametrize(
    "token",
    [
        "ghp_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789",
        "gho_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789",
        "ghs_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789",
        "github_pat_11ABCDEFG0abcdefghijkl_mnopqrstuvwxyz0123456789ABCDEFGHIJKL",
        "glpat-AbCdEfGhIjKlMnOpQrSt-_",
        "gldt-AbCdEfGhIjKlMnOpQrSt1234",
    ],
)
def test__scrub__token_shapes__are_removed_without_knowing_the_secret(token: str) -> None:
    out = scrub(f"remote: bad credentials {token} for repo")

    assert token not in out
    assert "bad credentials" in out


def test__scrub__pem_block__is_removed() -> None:
    pem = "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAA\nAAAA\n-----END OPENSSH PRIVATE KEY-----"

    out = scrub(f"before\n{pem}\nafter")

    assert "b3BlbnNz" not in out
    assert out.startswith("before")
    assert out.endswith("after")


def test__scrub__pem_block_cut_by_tail__is_removed() -> None:
    out = scrub("tail -----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA")

    assert "MIIEow" not in out


def test__scrub__url_userinfo__is_masked_but_host_stays() -> None:
    out = scrub("fatal: unable to access 'https://user:pw@git.example.com/o/r.git/': 403")

    assert "user:pw" not in out
    assert "git.example.com/o/r.git" in out


def test__scrub__plain_text_without_secrets__is_unchanged() -> None:
    text = "fatal: couldn't find remote ref main\n"

    assert scrub(text, ["secret-value"]) == text


def test__scrub__short_secret__is_ignored_to_keep_the_message_readable() -> None:
    assert scrub("abc fatal abc", ["abc"]) == "abc fatal abc"


def test__scrub__longer_secret_containing_a_shorter_one__is_removed_whole() -> None:
    out = scrub("value=tokentoken-extra", ["token", "tokentoken-extra"])

    assert "extra" not in out
