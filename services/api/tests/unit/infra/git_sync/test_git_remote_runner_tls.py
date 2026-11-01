"""Доверие к серверам со своим сертификатом в раннере: `-c` только для адреса сервера и никакого отключения проверки."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pytest
from hse_doc_studio.api.config import GitConfig
from hse_doc_studio.core.git_sync.entities import GitResult, RemoteTarget, ServerCertificate
from hse_doc_studio.core.git_sync.error_classifier import GitOp
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.host_settings import GitHostSettings
from hse_doc_studio.core.git_sync.url import parse_remote_url
from hse_doc_studio.infra.git_sync.git_remote_runner import GitRemoteRunner
from hse_doc_studio.infra.git_sync.process_runner import GitProcessRunner

_STORE = Path("/work/project/.hse-studio/git")
_PIN = "SHA256:b1Kq0vU7m4Zl9Xc2Tn8RjHf3eWyAo5DsPi6GgLxEu0w"
_OTHER = "SHA256:Zr3Vn8Hq1Lw6Ys0Ud4Cx9TkPb2Ea7MgFj5RiOtNo1Ae"
_NOW = datetime(2026, 10, 27, tzinfo=timezone.utc)


@dataclass
class _Process(GitProcessRunner):
    result: GitResult = field(default_factory=lambda: GitResult(0))
    argvs: list[list[str]] = field(default_factory=list)
    envs: list[dict[str, str]] = field(default_factory=list)

    async def run(  # type: ignore[override]
        self, argv: Sequence[str], *, env: Mapping[str, str], cwd: Path, timeout_s: float, on_progress: object = None
    ) -> GitResult:
        self.argvs.append(list(argv))
        self.envs.append(dict(env))
        return self.result


class _Caps:
    git_binary = "git"

    def ssh_path(self) -> str | None:
        return "/usr/bin/ssh"

    async def ensure_git(self, *, cwd: Path, env: dict[str, str]) -> tuple[int, int, int]:
        return (2, 54, 0)


class _Credentials:
    async def get(self, credential_id: object) -> None:
        return None

    async def mark(self, *args: object, **kwargs: object) -> None:
        return None


class _Settings:
    def __init__(self, *items: GitHostSettings, trust: Path | None = None) -> None:
        self.items = {(item.host, item.port): item for item in items}
        self.trust = trust

    async def get(self, host: str, port: int | None) -> GitHostSettings | None:
        return self.items.get((host, port))

    async def materialize(self) -> None:
        return None

    def trust_file(self, host: str, port: int | None) -> Path | None:
        return self.trust if self.items.get((host, port)) else None


class _Certificates:
    def __init__(self, fingerprint: str | None = _PIN, *, untrusted_issuer: bool = False) -> None:
        self.fingerprint = fingerprint
        self.untrusted_issuer = untrusted_issuer
        self.fetched: list[tuple[str, int | None]] = []
        self.issuer_checks: list[tuple[str, int | None, Path | None]] = []

    async def issuer_is_untrusted(self, host: str, port: int | None, ca_file: Path | None) -> bool:
        self.issuer_checks.append((host, port, ca_file))
        return self.untrusted_issuer

    async def fetch(self, host: str, port: int | None) -> ServerCertificate:
        self.fetched.append((host, port))
        if self.fingerprint is None:
            raise GitSyncError(GitErrorCode.offline)
        return ServerCertificate(self.fingerprint, "CN=git.hse.local", "CN=HSE CA", _NOW, _NOW, False, "PEM")

    def normalize_ca_pem(self, pem: str) -> str:
        return pem


def _runner(
    process: _Process, settings: _Settings | None, certificates: _Certificates | None = None, **config: bool
) -> GitRemoteRunner:
    return GitRemoteRunner(
        GitConfig(**config),
        _Credentials(),  # type: ignore[arg-type]
        local_mode=True,
        process=process,
        capabilities=_Caps(),  # type: ignore[arg-type]
        host_settings=settings,  # type: ignore[arg-type]
        certificates=certificates,  # type: ignore[arg-type]
    )


def _target(raw: str = "https://git.hse.local:8443/team/paper.git") -> RemoteTarget:
    return RemoteTarget(parse_remote_url(raw, allow_http=True, allow_local=True))


async def _run(runner: GitRemoteRunner, target: RemoteTarget | None = None) -> None:
    await runner.run(["ls-remote", "--", "x"], op=GitOp.probe, git_dir=_STORE, target=target or _target(), timeout_s=5)


def _ssl_settings(argv: list[str]) -> list[str]:
    return [part for part in argv if "sslCAInfo" in part or "sslVerify" in part]


async def test__run__server_with_trust_file__passes_ssl_ca_info_scoped_to_its_address() -> None:
    process = _Process()
    trust = Path("/data/git/trust/abc.pem")
    runner = _runner(process, _Settings(GitHostSettings("git.hse.local", 8443, ca_pem="PEM"), trust=trust))

    await _run(runner)

    argv = process.argvs[0]
    assert _ssl_settings(argv) == [f"http.https://git.hse.local:8443/.sslCAInfo={trust}"]
    assert argv.index("-c") < argv.index("ls-remote")


async def test__run__server_with_trust_file__global_ca_variables_do_not_override_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # GIT_SSL_CAINFO git ставит выше `http.<адрес>.sslCAInfo`: без сброса файл сервера молча игнорировался бы.
    monkeypatch.setenv("GIT_SSL_CAINFO", "/etc/ssl/corp.pem")
    monkeypatch.setenv("GIT_SSL_CAPATH", "/etc/ssl/corp")
    monkeypatch.setenv("SSL_CERT_FILE", "/etc/ssl/other.pem")
    process = _Process()
    runner = _runner(
        process, _Settings(GitHostSettings("git.hse.local", 8443, ca_pem="PEM"), trust=Path("/data/git/trust/abc.pem"))
    )

    await _run(runner)

    env = process.envs[0]
    assert "GIT_SSL_CAINFO" not in env
    assert "GIT_SSL_CAPATH" not in env
    assert env["SSL_CERT_FILE"] == "/etc/ssl/other.pem"


async def test__run__server_without_trust__keeps_the_admin_ca_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_SSL_CAINFO", "/etc/ssl/corp.pem")
    process = _Process()
    runner = _runner(process, _Settings())

    await _run(runner)

    assert process.envs[0]["GIT_SSL_CAINFO"] == "/etc/ssl/corp.pem"


async def test__run__server_without_trust__adds_nothing() -> None:
    process = _Process()
    runner = _runner(process, _Settings(GitHostSettings("git.hse.local", 8443, provider_override=None, ca_pem=None)))

    await _run(runner)

    assert _ssl_settings(process.argvs[0]) == []


async def test__run__other_server__does_not_get_the_trust_of_this_one() -> None:
    process = _Process()
    settings = _Settings(GitHostSettings("git.hse.local", 8443, ca_pem="PEM"), trust=Path("/data/t.pem"))

    await _run(_runner(process, settings), _target("https://github.com/hse/course.git"))

    assert _ssl_settings(process.argvs[0]) == []


async def test__run__port_is_part_of_the_server_identity() -> None:
    process = _Process()
    settings = _Settings(GitHostSettings("git.hse.local", 8443, ca_pem="PEM"), trust=Path("/data/t.pem"))

    await _run(_runner(process, settings), _target("https://git.hse.local/team/paper.git"))

    assert _ssl_settings(process.argvs[0]) == []


async def test__run__verification_is_never_switched_off() -> None:
    process = _Process()
    settings = _Settings(
        GitHostSettings("git.hse.local", 8443, ca_pem="PEM", pinned_fingerprint=_PIN, pinned_pem="PEM"),
        trust=Path("/data/t.pem"),
    )

    await _run(_runner(process, settings, _Certificates()))

    assert not any("sslVerify" in part for part in process.argvs[0])
    assert not any("GIT_SSL_NO_VERIFY" in part for part in process.argvs[0])


async def test__run__pinned_server_with_the_same_certificate__runs_git() -> None:
    process = _Process()
    certificates = _Certificates(_PIN)
    settings = _Settings(
        GitHostSettings("git.hse.local", 8443, pinned_fingerprint=_PIN, pinned_pem="PEM"), trust=Path("/data/t.pem")
    )

    await _run(_runner(process, settings, certificates))

    assert certificates.fetched == [("git.hse.local", 8443)]
    assert len(process.argvs) == 1


async def test__run__pinned_server_presents_another_certificate__fails_before_git_with_both_fingerprints() -> None:
    process = _Process()
    settings = _Settings(
        GitHostSettings("git.hse.local", 8443, pinned_fingerprint=_PIN, pinned_pem="PEM"), trust=Path("/data/t.pem")
    )

    with pytest.raises(GitSyncError) as error:
        await _run(_runner(process, settings, _Certificates(_OTHER)))

    assert error.value.code is GitErrorCode.tls_pin_mismatch
    assert (error.value.ctx["expected"], error.value.ctx["actual"]) == (_PIN, _OTHER)
    assert process.argvs == []


async def test__run__pinned_server_unreachable__lets_git_report_the_real_cause() -> None:
    process = _Process()
    settings = _Settings(
        GitHostSettings("git.hse.local", 8443, pinned_fingerprint=_PIN, pinned_pem="PEM"), trust=Path("/data/t.pem")
    )

    await _run(_runner(process, settings, _Certificates(None)))

    assert len(process.argvs) == 1


async def test__run__plain_http_server__never_gets_ssl_settings() -> None:
    process = _Process()
    settings = _Settings(GitHostSettings("git.hse.local", 8080, ca_pem="PEM"), trust=Path("/data/t.pem"))

    target = RemoteTarget(
        parse_remote_url("http://git.hse.local:8080/team/paper.git", allow_http=True), insecure_http=True
    )

    await _run(_runner(process, settings, allow_insecure_http=True), target)

    assert _ssl_settings(process.argvs[0]) == []


_UNTRUSTED = (
    "fatal: unable to access 'https://git.hse.local:8443/team/paper.git/': "
    "SSL certificate problem: self-signed certificate\n"
)


async def test__run__untrusted_certificate__error_carries_the_certificate_the_server_presented() -> None:
    process = _Process(GitResult(128, stderr=_UNTRUSTED))
    runner = _runner(process, _Settings(), _Certificates(_PIN))

    with pytest.raises(GitSyncError) as error:
        await _run(runner)

    assert error.value.code is GitErrorCode.tls_untrusted_ca
    certificate = error.value.ctx["certificate"]
    assert certificate.fingerprint_sha256 == _PIN  # type: ignore[attr-defined]
    assert not hasattr(certificate, "pem")


async def test__run__untrusted_certificate_and_server_cannot_be_read_again__keeps_the_code_without_certificate() -> (
    None
):
    process = _Process(GitResult(128, stderr=_UNTRUSTED))
    runner = _runner(process, _Settings(), _Certificates(None))

    with pytest.raises(GitSyncError) as error:
        await _run(runner)

    assert error.value.code is GitErrorCode.tls_untrusted_ca
    assert "certificate" not in error.value.ctx


async def test__run__expired_certificate__is_a_plain_tls_error_that_a_new_ca_cannot_fix() -> None:
    stderr = "fatal: unable to access 'https://git.hse.local/x/': SSL certificate problem: certificate has expired\n"
    runner = _runner(_Process(GitResult(128, stderr=stderr)), _Settings(), _Certificates(_PIN))

    with pytest.raises(GitSyncError) as error:
        await _run(runner, _target("https://git.hse.local/x.git"))

    assert error.value.code is GitErrorCode.tls_error


# Debian (образ Студии): libcurl-gnutls для любого сбоя проверки печатает одну и ту же строку.
_GNUTLS = (
    "fatal: unable to access 'https://git.hse.local:8443/team/paper.git/': "
    "server certificate verification failed. CAfile: none CRLfile: none\n"
)


async def test__run__gnutls_verification_failed_and_issuer_unknown__is_untrusted_ca_with_the_certificate() -> None:
    certificates = _Certificates(_PIN, untrusted_issuer=True)
    runner = _runner(_Process(GitResult(128, stderr=_GNUTLS)), _Settings(), certificates)

    with pytest.raises(GitSyncError) as error:
        await _run(runner)

    assert error.value.code is GitErrorCode.tls_untrusted_ca
    assert error.value.ctx["certificate"].fingerprint_sha256 == _PIN  # type: ignore[attr-defined]
    assert certificates.issuer_checks == [("git.hse.local", 8443, None)]


async def test__run__gnutls_verification_failed_for_another_reason__stays_a_tls_error() -> None:
    certificates = _Certificates(_PIN, untrusted_issuer=False)
    runner = _runner(_Process(GitResult(128, stderr=_GNUTLS)), _Settings(), certificates)

    with pytest.raises(GitSyncError) as error:
        await _run(runner)

    assert error.value.code is GitErrorCode.tls_error
    assert "certificate" not in error.value.ctx


async def test__run__gnutls_failure_on_a_server_with_trust_file__checks_the_chain_against_that_file() -> None:
    trust = Path("/data/git/trust/abc.pem")
    settings = _Settings(GitHostSettings("git.hse.local", 8443, ca_pem="PEM"), trust=trust)
    certificates = _Certificates(_PIN, untrusted_issuer=True)

    with pytest.raises(GitSyncError):
        await _run(_runner(_Process(GitResult(128, stderr=_GNUTLS)), settings, certificates))

    assert certificates.issuer_checks == [("git.hse.local", 8443, trust)]


async def test__run__openssl_names_the_reason__the_chain_is_not_checked_again() -> None:
    stderr = "fatal: unable to access 'https://git.hse.local/x/': SSL certificate problem: certificate has expired\n"
    certificates = _Certificates(_PIN, untrusted_issuer=True)

    with pytest.raises(GitSyncError) as error:
        await _run(
            _runner(_Process(GitResult(128, stderr=stderr)), _Settings(), certificates),
            _target("https://git.hse.local/x.git"),
        )

    assert error.value.code is GitErrorCode.tls_error
    assert certificates.issuer_checks == []
