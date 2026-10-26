"""Сами фикстуры удалённых репозиториев: тесты синхронизации стоят на них и не должны молча отваливаться."""

from __future__ import annotations

import os
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.fixtures.git_remote import (
    BareRemote,
    GitHttpServer,
    StudioPair,
    git_binary_available,
    http_backend_available,
    seed_remote,
)


def test__ci__git_and_http_backend_are_installed() -> None:
    if not os.environ.get("CI"):
        pytest.skip("only enforced in CI")

    assert git_binary_available(), "CI image has no git: every sync test would be skipped silently"
    assert http_backend_available(), "CI image has no git http-backend: http transport tests would be skipped"


def test__seed_remote__builds_history_on_top_of_existing_branch(bare_remote: BareRemote) -> None:
    first = seed_remote(bare_remote, {"a.txt": "a"})
    second = seed_remote(bare_remote, {"b.txt": "b"})

    assert bare_remote.head("main") == second
    assert bare_remote.git("rev-parse", f"{second}^") == first
    assert bare_remote.git("show", f"{second}:a.txt") == "a"
    assert bare_remote.git("show", f"{second}:b.txt") == "b"


def test__seed_remote__other_branch__keeps_main_untouched(bare_remote: BareRemote) -> None:
    main = seed_remote(bare_remote, {"a.txt": "a"})

    seed_remote(bare_remote, {"x.txt": "x"}, branch="feature")

    assert bare_remote.head("main") == main
    assert bare_remote.head("feature") is not None


def test__studio_pair__stores_are_isolated_and_have_distinct_roots(studio_pair: StudioPair) -> None:
    assert studio_pair.first.head() != studio_pair.second.head()
    assert studio_pair.first.git_dir != studio_pair.second.git_dir
    assert (studio_pair.first.folder / ".hse-studio" / "git" / "HEAD").exists()
    assert not (studio_pair.first.folder / ".git").exists()


def test__studio_pair__commit__moves_only_that_store(studio_pair: StudioPair) -> None:
    before = studio_pair.second.head()
    studio_pair.first.write("a.txt", "a")

    sha = studio_pair.first.commit("first edit")

    assert studio_pair.first.head() == sha
    assert studio_pair.second.head() == before


def _get(url: str, *, authorization: str | None = None) -> tuple[int, dict[str, str]]:
    request = urllib.request.Request(url)  # noqa: S310 — адрес локального тестового сервера
    if authorization:
        request.add_header("Authorization", authorization)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
            return response.status, dict(response.headers)
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers)


_REFS = "/info/refs?service=git-upload-pack"


def test__http_git_server__requires_basic_auth(http_git_server: GitHttpServer) -> None:
    http_git_server.create_repo("r.git")
    url = http_git_server.url("r.git") + _REFS

    anonymous, headers = _get(url)
    wrong, _ = _get(url, authorization="Basic " + "eDp3cm9uZw==")
    allowed, allowed_headers = _get(url, authorization=http_git_server.basic())

    assert (anonymous, wrong, allowed) == (401, 401, 200)
    assert "Basic" in headers["WWW-Authenticate"]
    assert allowed_headers["Content-Type"] == "application/x-git-upload-pack-advertisement"


def test__http_git_server__records_requests_with_lowercase_headers(http_git_server: GitHttpServer) -> None:
    http_git_server.create_repo("r.git")

    _get(http_git_server.url("r.git") + _REFS, authorization=http_git_server.basic())

    assert http_git_server.authorizations() == [http_git_server.basic()]
    assert http_git_server.requests[0].path.endswith(_REFS)


def test__http_git_server__redirect_mode__answers_302_to_the_other_server(
    http_git_server: GitHttpServer, tmp_path: Path
) -> None:
    http_git_server.redirect_to = "http://127.0.0.1:9"
    request = urllib.request.Request(http_git_server.url("r.git") + _REFS)  # noqa: S310

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args: object, **kwargs: object) -> None:
            return None

    opener = urllib.request.build_opener(_NoRedirect)
    with pytest.raises(urllib.error.HTTPError) as raised:
        opener.open(request, timeout=10)

    assert raised.value.code == 302
    assert raised.value.headers["Location"] == "http://127.0.0.1:9/r.git" + _REFS


def test__http_git_server__token_none__serves_anonymously(
    http_git_server_factory: Callable[..., GitHttpServer],
) -> None:
    server = http_git_server_factory(token=None)
    server.create_repo("r.git")

    status, _ = _get(server.url("r.git") + _REFS)

    assert status == 200
