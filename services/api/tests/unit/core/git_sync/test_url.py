from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitUrlError
from hse_doc_studio.core.git_sync.url import MAX_URL_LENGTH, GitProvider, RemoteKind, RemoteUrl, parse_remote_url

_CASES_FILE = Path(__file__).resolve().parents[6] / "contracts" / "git-sync" / "url_cases.json"
_CASES: list[dict[str, Any]] = json.loads(_CASES_FILE.read_text(encoding="utf-8"))["cases"]


def _raw_input(case: dict[str, Any]) -> str:
    raw = case["input"]
    if isinstance(raw, dict):
        return raw["prefix"] + raw["repeat"] * raw["times"] + raw["suffix"]
    return str(raw)


def _parse(case: dict[str, Any]) -> RemoteUrl:
    policy = case.get("policy", {})
    return parse_remote_url(
        _raw_input(case), allow_http=policy.get("allow_http", False), allow_local=policy.get("allow_local", False)
    )


@pytest.mark.parametrize("case", [c for c in _CASES if c["ok"]], ids=lambda c: c["name"])
def test__parse_remote_url__shared_vector_ok__matches_expected_fields(case: dict[str, Any]) -> None:
    parsed = _parse(case)

    expected = case["url"]
    assert parsed.display_url == expected["display_url"]
    assert parsed.kind.value == expected["kind"]
    assert parsed.host == expected["host"]
    assert parsed.provider.value == expected["provider"]
    assert parsed.owner == expected["owner"]
    assert parsed.repo == expected["repo"]
    assert parsed.token_stripped is expected["token_stripped"]


@pytest.mark.parametrize("case", [c for c in _CASES if not c["ok"]], ids=lambda c: c["name"])
def test__parse_remote_url__shared_vector_rejected__raises_expected_code(case: dict[str, Any]) -> None:
    with pytest.raises(GitUrlError) as caught:
        _parse(case)

    assert caught.value.code.value == case["error"]


def test__parse_remote_url__vectors_cover_both_error_codes() -> None:
    codes = {c["error"] for c in _CASES if not c["ok"]}

    assert codes == {GitErrorCode.url_invalid.value, GitErrorCode.url_scheme_forbidden.value}


@pytest.mark.parametrize(
    "raw",
    [
        "https://user:hunter2@github.com/o/r.git",
        "https://ghp_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789@github.com/o/r.git",
        "http://TOKEN@git.example.com/o/r.git",
    ],
)
def test__parse_remote_url__userinfo__never_reaches_display_url(raw: str) -> None:
    parsed = parse_remote_url(raw, allow_http=True)

    assert "@" not in parsed.display_url
    assert "hunter2" not in parsed.display_url
    assert "TOKEN" not in parsed.display_url
    assert parsed.token_stripped is True


@pytest.mark.parametrize(
    "raw",
    [
        "https://github.com/o/r.git\x00",
        "https://github.com/o/r\x1b[31m.git",
        "https://github.com/o/r‮.git",
        "https://github.com/o/r .git",
        "https://github.com/o/%0d%0aHost:%20x",
        "https://github.com/o/r.git`id`",
        "https://github.com/o/$(id)",
        "https://github.com/o/r.git&x",
        "https://github.com/%2e%2e/r.git",
        "https://github.com/o//r.git",
        "https://[::1]/o/r.git",
        "https://git.example.com:abc/o/r.git",
        "ssh://git@host/./r.git",
        "git@host:../r.git",
        "-u",
        "--help",
    ],
)
def test__parse_remote_url__hostile_input__is_invalid(raw: str) -> None:
    with pytest.raises(GitUrlError) as caught:
        parse_remote_url(raw, allow_http=True, allow_local=True)

    assert caught.value.code is GitErrorCode.url_invalid


@pytest.mark.parametrize("raw", ["ext::sh", "fd::7/8", "git://github.com/o/r.git", "ssh+git://github.com/o/r.git"])
def test__parse_remote_url__transport_helpers__are_scheme_forbidden(raw: str) -> None:
    with pytest.raises(GitUrlError) as caught:
        parse_remote_url(raw, allow_http=True, allow_local=True)

    assert caught.value.code is GitErrorCode.url_scheme_forbidden


def test__parse_remote_url__exactly_max_length__is_accepted() -> None:
    prefix, suffix = "https://github.com/o/", ".git"
    raw = prefix + "a" * (MAX_URL_LENGTH - len(prefix) - len(suffix)) + suffix

    assert parse_remote_url(raw).repo == "a" * (MAX_URL_LENGTH - len(prefix) - len(suffix))


def test__parse_remote_url__over_max_length__is_invalid() -> None:
    raw = "https://github.com/o/" + "a" * MAX_URL_LENGTH

    with pytest.raises(GitUrlError):
        parse_remote_url(raw)


def test__parse_remote_url__idn_host__is_punycoded() -> None:
    parsed = parse_remote_url("https://пример.рф/team/repo.git")

    assert parsed.host == "xn--e1afmkfd.xn--p1ai"
    assert parsed.display_url == "https://xn--e1afmkfd.xn--p1ai/team/repo.git"


def test__parse_remote_url__error_detail__is_a_message_not_the_input() -> None:
    with pytest.raises(GitUrlError) as caught:
        parse_remote_url("ghp_SECRETSECRETSECRET1234 x")

    assert "ghp_SECRET" not in caught.value.detail
    assert "ghp_SECRET" not in str(caught.value)


def test__remote_url__host_key__adds_port_only_when_present() -> None:
    plain = parse_remote_url("ssh://git@github.com/o/r.git")
    custom = parse_remote_url("ssh://git@git.hse.ru:2222/o/r.git")
    local = parse_remote_url("/srv/r.git", allow_local=True)

    assert plain.host_key == "github.com"
    assert custom.host_key == "[git.hse.ru]:2222"
    assert local.host_key is None


def test__parse_remote_url__ssh_default_user_and_explicit_user() -> None:
    assert parse_remote_url("ssh://github.com/o/r.git").user == "git"
    assert parse_remote_url("anna@git.hse.ru:o/r.git").user == "anna"
    assert parse_remote_url("https://github.com/o/r.git").user is None


def test__parse_remote_url__kinds_and_providers_are_enums() -> None:
    parsed = parse_remote_url("https://bitbucket.org/o/r.git")

    assert parsed.kind is RemoteKind.https
    assert parsed.provider is GitProvider.bitbucket


def test__parse_remote_url__single_segment_path__has_no_owner() -> None:
    parsed = parse_remote_url("https://git.example.com/repo.git")

    assert parsed.owner is None
    assert parsed.repo == "repo"
