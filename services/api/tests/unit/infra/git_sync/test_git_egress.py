from __future__ import annotations

import socket

import pytest
from hse_doc_studio.api.config import GitConfig
from hse_doc_studio.core.git_sync.entities import RemoteTarget
from hse_doc_studio.core.git_sync.error_classifier import GitOp
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.protocols import DetectionRequest, IntrospectionRequest
from hse_doc_studio.core.git_sync.providers import GitProvider
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.git_sync.url import parse_remote_url
from hse_doc_studio.infra.egress.policy import ResolvingEgressPolicy
from hse_doc_studio.infra.git_sync.git_remote_runner import GitRemoteRunner
from hse_doc_studio.infra.git_sync.host_key_scanner import SshKeyscanScanner
from hse_doc_studio.infra.git_sync.provider_api import HttpProviderDetector, HttpTokenIntrospector
from hse_doc_studio.infra.git_sync.tls_certificates import TlsCertificateService

from tests.unit.infra.git_sync.test_git_remote_runner import _STORE, _Caps, _Credentials, _Process


def _policy(allowlist: list[str] | None = None, **names: list[str]) -> ResolvingEgressPolicy:
    async def resolve(host: str, port: int) -> list[str]:
        if host not in names:
            raise socket.gaierror(socket.EAI_NONAME, "unknown")
        return names[host]

    return ResolvingEgressPolicy(allowlist or [], resolver=resolve)


def _runner(process: _Process, egress: ResolvingEgressPolicy | None) -> GitRemoteRunner:
    return GitRemoteRunner(
        GitConfig(),
        _Credentials(),  # type: ignore[arg-type]
        local_mode=False,
        process=process,
        capabilities=_Caps(),  # type: ignore[arg-type]
        egress=egress,
    )


def _target(raw: str) -> RemoteTarget:
    return RemoteTarget(parse_remote_url(raw, allow_http=True, allow_local=False))


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1/hse/course.git",
        "https://169.254.169.254/hse/course.git",
        "https://intranet.example/hse/course.git",
        "ssh://git@10.0.0.8/hse/course.git",
    ],
)
async def test__run__internal_address__egress_blocked_and_git_is_not_started(url: str) -> None:
    process = _Process()
    runner = _runner(process, _policy(**{"intranet.example": ["10.0.0.9"]}))

    with pytest.raises(GitSyncError) as caught:
        await runner.run(["ls-remote", "--", url], op=GitOp.probe, git_dir=_STORE, target=_target(url), timeout_s=5)

    assert caught.value.code is GitErrorCode.egress_blocked
    assert process.calls == []


async def test__run__public_address__starts_git_with_redirects_off() -> None:
    process = _Process()
    url = "https://git.example.org/hse/course.git"
    runner = _runner(process, _policy(**{"git.example.org": ["93.184.216.34"]}))

    await runner.run(["ls-remote", "--", url], op=GitOp.probe, git_dir=_STORE, target=_target(url), timeout_s=5)

    argv = process.calls[0][0]
    assert "http.followRedirects=false" in argv
    assert "http.followRedirects=initial" in argv  # базовое значение остаётся, последнее `-c` его перекрывает
    assert argv.index("http.followRedirects=false") > argv.index("http.followRedirects=initial")
    assert process.calls[0][1]["GIT_ALLOW_PROTOCOL"] == "https:ssh"


async def test__run__allowlisted_lan_host__passes() -> None:
    process = _Process()
    url = "https://git.corp.local/hse/course.git"
    runner = _runner(process, _policy(["git.corp.local"], **{"git.corp.local": ["10.1.1.1"]}))

    await runner.run(["ls-remote", "--", url], op=GitOp.probe, git_dir=_STORE, target=_target(url), timeout_s=5)

    assert len(process.calls) == 1


async def test__run__unresolvable_host__left_to_git_to_report() -> None:
    process = _Process()
    url = "https://gone.example/hse/course.git"
    runner = _runner(process, _policy())

    await runner.run(["ls-remote", "--", url], op=GitOp.probe, git_dir=_STORE, target=_target(url), timeout_s=5)

    assert len(process.calls) == 1


async def test__run__without_policy__local_mode_is_unchanged() -> None:
    process = _Process()
    url = "https://127.0.0.1/hse/course.git"
    runner = _runner(process, None)

    await runner.run(["ls-remote", "--", url], op=GitOp.probe, git_dir=_STORE, target=_target(url), timeout_s=5)

    argv = process.calls[0][0]
    assert "http.followRedirects=false" not in argv


async def test__scan_and_certificate__internal_host__egress_blocked() -> None:
    egress = _policy()

    with pytest.raises(GitSyncError) as scanned:
        await SshKeyscanScanner(GitConfig(), egress).scan("10.0.0.1", 22)
    with pytest.raises(GitSyncError) as fetched:
        await TlsCertificateService(1.0, egress).fetch("127.0.0.1", 443)

    assert scanned.value.code is GitErrorCode.egress_blocked
    assert fetched.value.code is GitErrorCode.egress_blocked


async def test__introspect__internal_api__egress_blocked() -> None:
    request = IntrospectionRequest(
        provider=GitProvider.gitlab, api_base="https://127.0.0.1/api/v4", token=Secret("glpat-x"), ca_file=None
    )

    with pytest.raises(GitSyncError) as caught:
        await HttpTokenIntrospector(1.0, egress=_policy()).introspect(request)

    assert caught.value.code is GitErrorCode.egress_blocked


async def test__detect__internal_host__finds_nothing_without_a_request() -> None:
    request = DetectionRequest(
        host="127.0.0.1",
        port=None,
        secure=True,
        segments=("hse", "course"),
        providers=(GitProvider.gitlab,),
        ca_file=None,
    )

    assert await HttpProviderDetector(1.0, _policy()).detect(request) is None
