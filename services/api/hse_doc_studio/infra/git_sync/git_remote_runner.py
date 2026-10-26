"""GitRemoteRunner: единственное место, где запускается git, который ходит в сеть.

Безопасность держится на трёх вещах. Окружение собирается по белому списку (`base_git_env`), а не
копируется у сервера: ключи API и GIT_TRACE туда не попадают. Конфиг хранилища проекта недоверенный,
поэтому поверх него идут защитные `-c`. Токен доставляется только через окружение процесса и привязан
к хосту адреса (см. auth_env). Всё, что git напечатал, проходит очистку от секретов до того, как
текст увидит кто-то ещё.
"""

from __future__ import annotations

import tempfile
import time
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

import structlog

from hse_doc_studio.api.config import GitConfig
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.git_sync.entities import CredentialStatus, GitCredential, GitResult, RemoteTarget
from hse_doc_studio.core.git_sync.error_classifier import (
    DETAIL_TAIL_CHARS,
    GitOp,
    Transport,
    classify_git_stderr,
    scrub,
)
from hse_doc_studio.core.git_sync.error_messages import git_error
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.protocols import IGitCredentialRepository, ProgressCallback
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.git_sync.url import RemoteKind
from hse_doc_studio.infra.git_sync.auth_env import HttpAuth, allowed_protocols, build_http_auth
from hse_doc_studio.infra.git_sync.git_capabilities import GitCapabilities
from hse_doc_studio.infra.git_sync.process_runner import GitProcessRunner, ProcessTimeoutError
from hse_doc_studio.infra.vcs.git_env import base_git_env, hardened_git_config

logger = structlog.get_logger()

_MS = 1000
# Защита от зависшего соединения: ниже 1 КБ/с в течение 30 с git обрывает передачу.
_LOW_SPEED_LIMIT = "1000"
_LOW_SPEED_TIME = "30"


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


class GitRemoteRunner:
    def __init__(
        self,
        config: GitConfig,
        credentials: IGitCredentialRepository,
        *,
        local_mode: bool,
        process: GitProcessRunner | None = None,
        capabilities: GitCapabilities | None = None,
    ) -> None:
        self._config = config
        self._credentials = credentials
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
        self._check_policy(target)
        credential, secret = self._load_credential(target)
        auth = build_http_auth(target.url, credential, secret) if credential and secret else None
        env = {
            **base_git_env(),
            "GIT_ALLOW_PROTOCOL": allowed_protocols(target.url),
            "GIT_PROTOCOL_FROM_USER": "0",
            **(auth.env if auth else {}),
        }
        await self._capabilities.ensure_git(cwd=git_dir.parent, env=env)
        started = time.monotonic()
        try:
            result = await self._spawn(args, git_dir=git_dir, env=env, timeout_s=timeout_s, on_progress=on_progress)
        except GitSyncError as exc:
            self._log(args, target, started, None, exc.code)
            raise
        if result.returncode == 0:
            self._log(args, target, started, 0, None)
            self._remember_success(credential)
            return result
        error = self._failure(result, op=op, target=target, credential=credential, auth=auth)
        self._log(args, target, started, result.returncode, error.code)
        if error.code is GitErrorCode.auth_failed and credential is not None:
            self._credentials.mark(credential.id, CredentialStatus.auth_failed)
        raise error

    async def run_local(
        self, args: Sequence[str], *, git_dir: Path | None, timeout_s: float, check: bool = True
    ) -> GitResult:
        # Сети здесь нет: в недоверенном хранилище ленивая подгрузка объектов не должна ходить наружу без доступа.
        env = {**base_git_env(), "GIT_ALLOW_PROTOCOL": "none"}
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
    ) -> GitResult:
        argv = [self._capabilities.git_binary]
        if git_dir is not None:
            argv += ["--git-dir", str(git_dir)]
        argv += [*hardened_git_config(), *_network_config(), *args]
        cwd = git_dir.parent if git_dir is not None else Path(tempfile.gettempdir())
        try:
            return await self._process.run(argv, env=env, cwd=cwd, timeout_s=timeout_s, on_progress=on_progress)
        except ProcessTimeoutError:
            raise git_error(GitErrorCode.timeout) from None
        except OSError:
            raise git_error(GitErrorCode.git_unavailable) from None

    def _check_policy(self, target: RemoteTarget) -> None:
        kind = target.url.kind
        if kind is RemoteKind.http and not (self._config.allow_insecure_http and target.insecure_http):
            raise git_error(GitErrorCode.url_scheme_forbidden)
        if kind is RemoteKind.file and not self._allow_local:
            raise git_error(GitErrorCode.url_scheme_forbidden)
        if kind is RemoteKind.ssh:
            raise git_error(GitErrorCode.ssh_unavailable)

    def _load_credential(self, target: RemoteTarget) -> tuple[GitCredential | None, Secret | None]:
        if target.credential_id is None or target.url.kind is RemoteKind.file:
            return None, None
        credential = self._credentials.get(target.credential_id)
        if credential is None:
            raise git_error(GitErrorCode.credentials_missing)
        try:
            return credential, self._credentials.get_secret(credential.id)
        except NotFoundError:
            raise git_error(GitErrorCode.credentials_missing) from None

    def _failure(
        self,
        result: GitResult,
        *,
        op: GitOp,
        target: RemoteTarget,
        credential: GitCredential | None,
        auth: HttpAuth | None,
    ) -> GitSyncError:
        text = result.stderr
        if op is GitOp.push and result.stdout:
            # Построчный отчёт `--porcelain` приходит в stdout: отказ ветки виден только там.
            text += "\n" + result.stdout.decode("utf-8", errors="replace")
        classified = classify_git_stderr(
            text, op=op, transport=Transport(target.url.kind.value), secrets=auth.secrets if auth else ()
        )
        code = classified.code
        if code is GitErrorCode.auth_failed and credential is None:
            code = GitErrorCode.credentials_missing
        return git_error(code, tail=classified.detail)

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
