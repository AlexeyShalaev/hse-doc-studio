import gzip
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from hse_doc_studio.core.git_remote.entities import GitService
from hse_doc_studio.core.git_remote.protocols import GitBodyInvalidError, GitBodyTooLargeError
from hse_doc_studio.infra.git_remote.smart_http import BodyReader, git_args, git_env, git_protocol, pkt_line


async def _source(*chunks: bytes) -> AsyncIterator[bytes]:
    for chunk in chunks:
        yield chunk


async def _read(reader: BodyReader) -> bytes:
    return b"".join([chunk async for chunk in reader.chunks()])


def test__pkt_line__length_prefix_includes_itself() -> None:
    assert pkt_line("# service=git-upload-pack\n") == b"001e# service=git-upload-pack\n"


def test__git_protocol__only_known_versions_pass() -> None:
    assert git_protocol("version=2") == "version=2"
    assert git_protocol("version=1:version=2") == "version=2"
    assert git_protocol("version=3") is None
    assert git_protocol("foo=bar") is None
    assert git_protocol(None) is None


def test__git_args__hardened_hidden_refs_and_stateless_rpc() -> None:
    args = git_args(GitService.upload_pack, Path("/p/.hse-studio/git"), advertise=True)

    assert args[0] == "git"
    assert args[-3:] == ["--stateless-rpc", "--advertise-refs", "/p/.hse-studio/git"]
    assert "upload-pack" in args
    for value in (
        "uploadpack.hideRefs=refs/hse",
        "uploadpack.hideRefs=refs/remotes",
        "uploadpack.hideRefs=refs/tags",
        "receive.hideRefs=refs/hse",
        "uploadpack.allowAnySHA1InWant=false",
        "uploadpack.allowFilter=true",
        "safe.directory=*",
        "core.fsmonitor=false",
    ):
        assert value in args
    receive = git_args(GitService.receive_pack, Path("/g"), advertise=False, extra_config=["-c", "x.y=1"])
    assert receive[-4:] == ["x.y=1", "receive-pack", "--stateless-rpc", "/g"]


def test__git_env__whitelist_plus_protocol(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HSE_STUDIO__SECRETS__KEY", "secret")
    env = git_env("version=2", {"HSE_PUSH_ACTOR": "u1"})

    assert env["GIT_PROTOCOL"] == "version=2"
    assert env["HSE_PUSH_ACTOR"] == "u1"
    assert "HSE_STUDIO__SECRETS__KEY" not in env
    assert "GIT_PROTOCOL" not in git_env(None)


async def test__body_reader__plain_and_gzip_streams() -> None:
    data = b"0032want abc\n" * 100
    packed = gzip.compress(data)

    assert await _read(BodyReader(_source(data[:10], data[10:]), gzip=False, max_bytes=10_000)) == data
    halves = _source(packed[:7], packed[7:])
    assert await _read(BodyReader(halves, gzip=True, max_bytes=10_000)) == data


async def test__body_reader__limit_counts_plain_and_inflated_bytes() -> None:
    with pytest.raises(GitBodyTooLargeError):
        await _read(BodyReader(_source(b"x" * 11), gzip=False, max_bytes=10))
    bomb = gzip.compress(b"\0" * 1_000_000)
    with pytest.raises(GitBodyTooLargeError):
        await _read(BodyReader(_source(bomb), gzip=True, max_bytes=1000))


async def test__body_reader__broken_gzip__invalid() -> None:
    with pytest.raises(GitBodyInvalidError):
        await _read(BodyReader(_source(b"not gzip at all"), gzip=True, max_bytes=1000))
