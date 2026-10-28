from __future__ import annotations

import pytest
from hse_doc_studio.api.auth_cookie import credentials_from_request, session_cookie_name
from hse_doc_studio.api.config import Settings
from hse_doc_studio.core.mode import StudioMode
from pydantic import ValidationError
from starlette.requests import Request


def _request(headers: dict[str, str]) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "method": "GET", "path": "/", "headers": raw})


def test_cookie_name_depends_on_transport() -> None:
    assert session_cookie_name(secure=True) == "__Host-hse_session"
    assert session_cookie_name(secure=False) == "hse_session"


def test_credentials_read_cookie_and_bearer() -> None:
    creds = credentials_from_request(
        _request({"cookie": "hse_session=abc", "authorization": "Bearer tok"}), secure=False
    )

    assert creds.session_secret == "abc"
    assert creds.bearer_token == "tok"


def test_secure_cookie_wins_and_other_auth_scheme_is_ignored() -> None:
    creds = credentials_from_request(
        _request({"cookie": "hse_session=a; __Host-hse_session=b", "authorization": "Basic x"}), secure=False
    )

    assert creds.session_secret == "b"
    assert creds.bearer_token is None


def test_plain_cookie_is_ignored_over_https() -> None:
    request = _request({"cookie": "hse_session=planted"})

    assert credentials_from_request(request, secure=True).session_secret is None
    assert credentials_from_request(request, secure=False).session_secret == "planted"


def test_host_cookie_is_read_over_https() -> None:
    request = _request({"cookie": "hse_session=planted; __Host-hse_session=real"})

    assert credentials_from_request(request, secure=True).session_secret == "real"


def test_anonymous_request_has_no_credentials() -> None:
    creds = credentials_from_request(_request({}))

    assert creds.session_secret is None
    assert creds.bearer_token is None


def test_server_cors_wildcard_with_credentials_is_refused() -> None:
    with pytest.raises(ValidationError, match="explicit origins"):
        Settings(_env_file=None, mode=StudioMode.server, cors={"allow_origins": ["*"], "allow_credentials": True})


def test_server_cors_wildcard_without_credentials_and_explicit_origins_pass() -> None:
    Settings(_env_file=None, mode=StudioMode.server, cors={"allow_origins": ["*"], "allow_credentials": False})
    Settings(_env_file=None, mode=StudioMode.server, cors={"allow_origins": ["https://studio.example.org"]})


def test_local_cors_is_not_validated() -> None:
    Settings(_env_file=None, mode=StudioMode.local, cors={"allow_origins": ["*"], "allow_credentials": True})


def test_uvicorn_does_not_trust_forwarded_headers_by_default() -> None:
    kwargs = Settings(_env_file=None).get_uvicorn_kwargs()

    assert kwargs["proxy_headers"] is False
    assert kwargs["forwarded_allow_ips"] != "*"
