"""GitRemoteRunner: единственное место, где запускается git, который ходит в сеть.

Безопасность держится на трёх вещах. Окружение собирается по белому списку (`base_git_env`), а не
копируется у сервера: ключи API и GIT_TRACE туда не попадают. Конфиг хранилища проекта недоверенный,
поэтому поверх него идут защитные `-c`. Токен доставляется только через окружение процесса и привязан
к хосту адреса (см. auth_env); редиректы с токеном отключены, потому что git шлёт заголовок и на новый
хост. Всё, что git напечатал, проходит очистку от секретов до того, как текст увидит кто-то ещё.
"""

from __future__ import annotations

import tempfile
import time
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

import structlog

from hse_doc_studio.api.config import GitConfig
from hse_doc_studio.core.egress import IEgressPolicy
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.git_sync.entities import (
    CredentialStatus,
    GitCredential,
    GitCredentialKind,
    GitResult,
    RemoteTarget,
    ScannedHostKey,
)
from hse_doc_studio.core.git_sync.error_classifier import (
    DETAIL_TAIL_CHARS,
    GitOp,
    Transport,
    classify_git_stderr,
    scrub,
    tls_reason_is_hidden,
)
from hse_doc_studio.core.git_sync.error_messages import git_error
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.protocols import (
    ICertificateService,
    IGitCredentialRepository,
    IGitHostSettingsRepository,
    IHostKeyScanner,
    IKnownHostsStore,
    ProgressCallback,
)
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.git_sync.url import RemoteKind, RemoteUrl
from hse_doc_studio.infra.git_sync.auth_env import (
    allowed_protocols,
    build_http_auth,
    check_credential_matches,
)
from hse_doc_studio.infra.git_sync.egress_guard import authorize_git_host
from hse_doc_studio.infra.git_sync.git_capabilities import GitCapabilities
from hse_doc_studio.infra.git_sync.process_runner import GitProcessRunner, ProcessTimeoutError
from hse_doc_studio.infra.git_sync.ssh_command import build_ssh_command, temporary_key_file
from hse_doc_studio.infra.vcs.git_env import base_git_env, hardened_git_config

logger = structlog.get_logger()

_MS = 1000
# Защита от зависшего соединения: ниже 1 КБ/с в течение 30 с git обрывает передачу.
_LOW_SPEED_LIMIT = "1000"
_LOW_SPEED_TIME = "30"
# Переменные, которыми git берёт файл или каталог доверенных CA раньше, чем `http.<адрес>.sslCAInfo` из конфига.
_CA_ENV_OVERRIDES = ("GIT_SSL_CAINFO", "GIT_SSL_CAPATH")


def _network_config() -> list[str]:
    """`-c` поверх hardened_git_config: проверка объектов, редиректы только на первом запросе, без фонового gc."""
    settings = {
        "safe.directory": "*",
        "core.askPass": "",
        "transfer.fsckObjects": "true",
        "http.followRedirects": "initial",
        "http.lowSpeedLimit": _LOW_SPEED_LIMIT,
        "http.lowSpeedTime": _LOW_SPEED_TIME,
        "gc.auto": "0",
        "gc.autoDetach": "false",
        "maintenance.auto": "false",
    }
    return [part for key, value in settings.items() for part in ("-c", f"{key}={value}")]


def _with_dot_git(args: Sequence[str], url: RemoteUrl) -> list[str]:
    """Адрес без `.git` получает суффикс: GitLab перенаправляет `<repo>/info/refs` на `<repo>.git/info/refs`.

    С токеном редиректы выключены, поэтому без суффикса самый частый ввод (адрес из строки браузера) падал бы.
    """
    if url.kind not in (RemoteKind.https, RemoteKind.http) or url.display_url.endswith(".git"):
        return list(args)
    return [f"{arg}.git" if arg == url.display_url else arg for arg in args]


class GitRemoteRunner:
    def __init__(
        self,
        config: GitConfig,
        credentials: IGitCredentialRepository,
        *,
        local_mode: bool,
        process: GitProcessRunner | None = None,
        capabilities: GitCapabilities | None = None,
        known_hosts: IKnownHostsStore | None = None,
        scanner: IHostKeyScanner | None = None,
        host_settings: IGitHostSettingsRepository | None = None,
        certificates: ICertificateService | None = None,
        egress: IEgressPolicy | None = None,
    ) -> None:
        self._config = config
        self._egress = egress
        self._credentials = credentials
        self._host_settings = host_settings
        self._certificates = certificates
        self._known_hosts = known_hosts
        self._scanner = scanner
        self._allow_local = config.allow_local_remotes and local_mode
        self._process = process or GitProcessRunner()
        self._capabilities = capabilities or GitCapabilities(
            min_version=config.git_min_version, ssh_binary=config.ssh_binary
        )

    async def run(
        self,
        args: Sequence[str],
        *,
        op: GitOp,
        git_dir: Path,
        target: RemoteTarget,
        timeout_s: float,
        on_progress: ProgressCallback | None = None,
    ) -> GitResult:
        await authorize_git_host(self._egress, target.url.host, target.url.port)
        self._check_policy(target)
        if target.url.kind is RemoteKind.ssh:
            return await self._run_ssh(
                args, op=op, git_dir=git_dir, target=target, timeout_s=timeout_s, on_progress=on_progress
            )
        credential, secret = self._load_credential(target)
        auth = build_http_auth(target.url, credential, secret) if credential and secret else None
        trust_config = await self._trust_config(target)
        env = {
            **base_git_env(),
            "GIT_ALLOW_PROTOCOL": allowed_protocols(target.url),
            "GIT_PROTOCOL_FROM_USER": "0",
            **(auth.env if auth else {}),
        }
        if trust_config:
            # Переменные окружения git ставит выше конфига: общий CA администратора перекрыл бы файл этого сервера.
            for name in _CA_ENV_OVERRIDES:
                env.pop(name, None)
        extra_config = trust_config
        if auth is not None or self._egress is not None:
            # Заголовок доступа git добавляет ко всем запросам сессии, в том числе после перехода на другой хост:
            # с токеном редиректы не идут вовсе. На общем сервере они выключены и без токена: редирект уводит git
            # на адрес, который политика egress не видела. Локально публичный адрес по-прежнему может перенаправлять.
            extra_config = [*trust_config, "-c", "http.followRedirects=false"]
            args = _with_dot_git(args, target.url)
        return await self._execute(
            args,
            op=op,
            git_dir=git_dir,
            target=target,
            env=env,
            credential=credential,
            secrets=auth.secrets if auth else (),
            timeout_s=timeout_s,
            on_progress=on_progress,
            extra_config=extra_config,
        )

    async def _run_ssh(
        self,
        args: Sequence[str],
        *,
        op: GitOp,
        git_dir: Path,
        target: RemoteTarget,
        timeout_s: float,
        on_progress: ProgressCallback | None,
    ) -> GitResult:
        # Сервер без подтверждённого ключа не пускаем дальше: человек сначала сверяет отпечаток, потом выбирает ключ.
        if self._known_hosts is not None and self._known_hosts.find(*self._host_port(target)) is None:
            keys = await self._scan(target, swallow=False)
            raise git_error(GitErrorCode.host_key_unknown, host_keys=tuple(key.public() for key in keys))
        credential, secret = self._load_credential(target)
        if credential is None or secret is None:
            raise git_error(GitErrorCode.credentials_missing)
        ssh = self._capabilities.ssh_path()
        if ssh is None or self._known_hosts is None:
            raise git_error(GitErrorCode.ssh_unavailable)
        with temporary_key_file(secret) as key_file:
            env = {
                **base_git_env(),
                "GIT_ALLOW_PROTOCOL": allowed_protocols(target.url),
                "GIT_PROTOCOL_FROM_USER": "0",
                "GIT_SSH_COMMAND": build_ssh_command(ssh, key_file=key_file, known_hosts=self._known_hosts.file_path()),
            }
            return await self._execute(
                args,
                op=op,
                git_dir=git_dir,
                target=target,
                env=env,
                credential=credential,
                secrets=(secret.reveal(),),
                timeout_s=timeout_s,
                on_progress=on_progress,
            )

    async def _execute(
        self,
        args: Sequence[str],
        *,
        op: GitOp,
        git_dir: Path,
        target: RemoteTarget,
        env: dict[str, str],
        credential: GitCredential | None,
        secrets: tuple[str, ...],
        timeout_s: float,
        on_progress: ProgressCallback | None,
        extra_config: Sequence[str] = (),
    ) -> GitResult:
        await self._capabilities.ensure_git(cwd=git_dir.parent, env=env)
        started = time.monotonic()
        try:
            result = await self._spawn(
                args, git_dir=git_dir, env=env, timeout_s=timeout_s, on_progress=on_progress, extra_config=extra_config
            )
        except GitSyncError as exc:
            self._log(args, target, started, None, exc.code)
            raise
        if result.returncode == 0:
            self._log(args, target, started, 0, None)
            self._remember_success(credential)
            return result
        error = await self._failure(result, op=op, target=target, credential=credential, secrets=secrets)
        self._log(args, target, started, result.returncode, error.code)
        if error.code is GitErrorCode.auth_failed and credential is not None:
            self._credentials.mark(credential.id, CredentialStatus.auth_failed)
        raise error

    async def run_local(
        self,
        args: Sequence[str],
        *,
        git_dir: Path | None,
        timeout_s: float,
        check: bool = True,
        allow_protocol: str = "none",
    ) -> GitResult:
        # Сети здесь нет: в недоверенном хранилище ленивая подгрузка объектов не должна ходить наружу без доступа.
        env = {**base_git_env(), "GIT_ALLOW_PROTOCOL": allow_protocol}
        cwd = git_dir.parent if git_dir is not None else Path(tempfile.gettempdir())
        await self._capabilities.ensure_git(cwd=cwd, env=env)
        result = await self._spawn(args, git_dir=git_dir, env=env, timeout_s=timeout_s, on_progress=None)
        if check and result.returncode != 0:
            raise git_error(GitErrorCode.git_error, tail=scrub(result.stderr)[-DETAIL_TAIL_CHARS:].strip())
        return result

    async def _spawn(
        self,
        args: Sequence[str],
        *,
        git_dir: Path | None,
        env: dict[str, str],
        timeout_s: float,
        on_progress: ProgressCallback | None,
        extra_config: Sequence[str] = (),
    ) -> GitResult:
        argv = [self._capabilities.git_binary]
        if git_dir is not None:
            argv += ["--git-dir", str(git_dir)]
        argv += [*hardened_git_config(), *_network_config(), *extra_config, *args]
        cwd = git_dir.parent if git_dir is not None else Path(tempfile.gettempdir())
        try:
            return await self._process.run(argv, env=env, cwd=cwd, timeout_s=timeout_s, on_progress=on_progress)
        except ProcessTimeoutError:
            raise git_error(GitErrorCode.timeout) from None
        except OSError:
            raise git_error(GitErrorCode.git_unavailable) from None

    async def _trust_config(self, target: RemoteTarget) -> list[str]:
        """Доверие к серверу с самоподписанным или внутренним сертификатом: `-c` только для адреса этого сервера.

        Закреплённый сертификат сверяется до запуска git: другой сертификат это подмена или смена, а не сбой сети.
        Проверка цепочки при этом не отключается: git доверяет ровно файлу PEM этого сервера.
        """
        if self._host_settings is None or target.url.kind is not RemoteKind.https or target.url.host is None:
            return []
        host, port = target.url.host, target.url.port
        settings = self._host_settings.get(host, port)
        if settings is None or not settings.has_trust:
            return []
        if settings.pinned_fingerprint is not None and self._certificates is not None:
            await self._check_pin(host, port, settings.pinned_fingerprint)
        trust_file = self._host_settings.trust_file(host, port)
        if trust_file is None:
            return []
        authority = f"{host}:{port}" if port else host
        return ["-c", f"http.https://{authority}/.sslCAInfo={trust_file}"]

    async def _check_pin(self, host: str, port: int | None, pinned: str) -> None:
        assert self._certificates is not None  # noqa: S101 — проверено вызывающим
        try:
            presented = await self._certificates.fetch(host, port)
        except GitSyncError:
            # Сервер недоступен: пусть git сообщит причину сам, подмены здесь нет.
            return
        if presented.fingerprint_sha256 != pinned:
            raise git_error(GitErrorCode.tls_pin_mismatch, expected=pinned, actual=presented.fingerprint_sha256)

    def _check_policy(self, target: RemoteTarget) -> None:
        kind = target.url.kind
        if kind is RemoteKind.http and not (self._config.allow_insecure_http and target.insecure_http):
            raise git_error(GitErrorCode.url_scheme_forbidden)
        if kind is RemoteKind.file and not self._allow_local:
            raise git_error(GitErrorCode.url_scheme_forbidden)
        if kind is RemoteKind.ssh and (self._capabilities.ssh_path() is None or self._known_hosts is None):
            raise git_error(GitErrorCode.ssh_unavailable)

    def _load_credential(self, target: RemoteTarget) -> tuple[GitCredential | None, Secret | None]:
        if target.url.kind is RemoteKind.file:
            return None, None
        if target.credential_id is None:
            if target.url.kind is RemoteKind.ssh:
                raise git_error(GitErrorCode.credentials_missing)
            return None, None
        credential = self._credentials.get(target.credential_id)
        if credential is None:
            raise git_error(GitErrorCode.credentials_missing)
        if target.url.kind is RemoteKind.ssh:
            self._check_ssh_credential(target, credential)
        try:
            return credential, self._credentials.get_secret(credential.id)
        except NotFoundError:
            raise git_error(GitErrorCode.credentials_missing) from None

    @staticmethod
    def _check_ssh_credential(target: RemoteTarget, credential: GitCredential) -> None:
        if credential.kind is not GitCredentialKind.ssh_key:
            raise git_error(GitErrorCode.credential_invalid)
        check_credential_matches(target.url, credential)

    async def _failure(
        self,
        result: GitResult,
        *,
        op: GitOp,
        target: RemoteTarget,
        credential: GitCredential | None,
        secrets: tuple[str, ...],
    ) -> GitSyncError:
        text = result.stderr
        if op is GitOp.push and result.stdout:
            # Построчный отчёт `--porcelain` приходит в stdout: отказ ветки виден только там.
            text += "\n" + result.stdout.decode("utf-8", errors="replace")
        classified = classify_git_stderr(text, op=op, transport=Transport(target.url.kind.value), secrets=secrets)
        code = classified.code
        if code is GitErrorCode.auth_failed and credential is None:
            code = GitErrorCode.credentials_missing
        if code in {GitErrorCode.host_key_unknown, GitErrorCode.host_key_changed}:
            return await self._host_key_error(code, target)
        if code is GitErrorCode.tls_error and tls_reason_is_hidden(text) and await self._issuer_untrusted(target):
            code = GitErrorCode.tls_untrusted_ca
        if code is GitErrorCode.tls_untrusted_ca:
            return await self._untrusted_ca_error(target)
        return git_error(code, tail=classified.detail)

    async def _issuer_untrusted(self, target: RemoteTarget) -> bool:
        """Git (libcurl-gnutls) не назвал причину отказа: по сертификату сервера видно, дело ли в центре выдачи.

        Проверка идёт теми же доверенными центрами, что у git: система плюс файл PEM этого сервера, если он задан.
        """
        host = target.url.host
        if self._certificates is None or host is None or target.url.kind is not RemoteKind.https:
            return False
        trust_file = self._host_settings.trust_file(host, target.url.port) if self._host_settings is not None else None
        return await self._certificates.issuer_is_untrusted(host, target.url.port, trust_file)

    async def _untrusted_ca_error(self, target: RemoteTarget) -> GitSyncError:
        """Сертификат не принят: он идёт в ошибке, чтобы человек сверил отпечаток и решил, добавить CA или закрепить."""
        if self._certificates is None or target.url.host is None:
            return git_error(GitErrorCode.tls_untrusted_ca)
        try:
            presented = await self._certificates.fetch(target.url.host, target.url.port)
        except GitSyncError:
            return git_error(GitErrorCode.tls_untrusted_ca)
        return git_error(GitErrorCode.tls_untrusted_ca, certificate=presented.public())

    async def _host_key_error(self, code: GitErrorCode, target: RemoteTarget) -> GitSyncError:
        """Ключ хоста не подошёл: отпечатки идут в ошибке, чтобы человек решил на месте, без второго запроса."""
        scanned = await self._scan(target, swallow=True)
        if code is GitErrorCode.host_key_unknown:
            return git_error(code, host_keys=tuple(key.public() for key in scanned))
        known = self._known_hosts.find(*self._host_port(target)) if self._known_hosts is not None else None
        if known is None or not known.fingerprints_sha256 or not scanned:
            return git_error(code)
        same_type = [key for key in scanned if key.type in known.key_types]
        actual = (same_type or scanned)[0]
        return git_error(code, expected=known.fingerprints_sha256[0], actual=actual.fingerprint_sha256)

    async def _scan(self, target: RemoteTarget, *, swallow: bool) -> list[ScannedHostKey]:
        if self._scanner is None:
            return []
        host, port = self._host_port(target)
        try:
            return await self._scanner.scan(host, port)
        except GitSyncError:
            if swallow:
                return []
            raise

    @staticmethod
    def _host_port(target: RemoteTarget) -> tuple[str, int | None]:
        return str(target.url.host), target.url.port

    def _remember_success(self, credential: GitCredential | None) -> None:
        if credential is not None:
            self._credentials.mark(credential.id, CredentialStatus.ok, used_at=datetime.now(timezone.utc))

    @staticmethod
    def _log(
        args: Sequence[str], target: RemoteTarget, started: float, rc: int | None, code: GitErrorCode | None
    ) -> None:
        logger.info(
            "git remote command finished",
            command=args[0] if args else "",
            host=target.url.host,
            transport=target.url.kind.value,
            credential_id=str(target.credential_id) if target.credential_id else None,
            duration_ms=round((time.monotonic() - started) * _MS),
            rc=rc,
            code=code.value if code else None,
        )
