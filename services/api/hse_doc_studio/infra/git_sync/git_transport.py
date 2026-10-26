"""GitTransport: probe, выборка и отправка поверх GitRemoteRunner.

Адрес и доступ приходят явно (RemoteTarget), в конфиг хранилища транспорт не заглядывает: адрес без
секретов, а токен раннер берёт из хранилища доступов. Refspec строится только здесь из проверенных
имён веток, отправляется всегда закреплённый коммит и никогда не force, не all и не mirror.
"""

from __future__ import annotations

import contextlib
import re
import shutil
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

from hse_doc_studio.api.config import GitConfig
from hse_doc_studio.core.git_sync.entities import (
    GitHostKey,
    GitOperationError,
    RemoteProbe,
    RemoteTarget,
    TlsCertificate,
)
from hse_doc_studio.core.git_sync.error_classifier import DETAIL_TAIL_CHARS, GitOp, scrub
from hse_doc_studio.core.git_sync.error_messages import git_error
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.protocols import IGitRemoteRunner, ProgressCallback
from hse_doc_studio.core.vcs.errors import VcsInvalidRefError
from hse_doc_studio.core.vcs.refs import validate_ref_name

_HEADS = "refs/heads/"
_SYMREF = "ref: "
_SHA = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_LOCAL_TIMEOUT_S = 30.0
# Крупнее этого файлы при поверхностной выборке вершины не скачиваются: project.json мал, PDF и картинки нет.
_TIP_BLOB_LIMIT = "1m"
_MISSING_PATH = ("does not exist in", "exists on disk, but not in")
# Сервер ответил, но не пустил: он достижим, дело в доступе.
_REACHABLE_CODES = frozenset(
    {
        GitErrorCode.auth_failed,
        GitErrorCode.forbidden_write,
        GitErrorCode.sso_required,
        GitErrorCode.not_found_or_no_access,
        GitErrorCode.rate_limited,
    }
)


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _branch(name: str) -> str:
    try:
        return validate_ref_name(name)
    except VcsInvalidRefError:
        raise git_error(GitErrorCode.branch_missing) from None


def _usable_branch(name: str) -> bool:
    try:
        validate_ref_name(name)
    except VcsInvalidRefError:
        return False
    return True


def parse_ls_remote(output: str) -> tuple[str | None, tuple[str, ...]]:
    """(ветка по умолчанию, ветки) из вывода `ls-remote --symref`; ветка по умолчанию только если она существует."""
    default: str | None = None
    branches: list[str] = []
    for line in output.splitlines():
        if line.startswith(_SYMREF):
            ref = line.removeprefix(_SYMREF).split("\t", 1)[0]
            if ref.startswith(_HEADS):
                default = ref.removeprefix(_HEADS)
            continue
        _, _, ref = line.partition("\t")
        if ref.startswith(_HEADS) and _usable_branch(ref.removeprefix(_HEADS)):
            branches.append(ref.removeprefix(_HEADS))
    return (default if default in branches else None), tuple(branches)


class GitTransport:
    def __init__(self, runner: IGitRemoteRunner, config: GitConfig) -> None:
        self._runner = runner
        self._config = config

    async def probe(self, target: RemoteTarget) -> RemoteProbe:
        try:
            async with self._scratch_store() as store:
                result = await self._runner.run(
                    ["ls-remote", "--symref", "--", target.url.display_url, "HEAD", f"{_HEADS}*"],
                    op=GitOp.probe,
                    git_dir=store,
                    target=target,
                    timeout_s=self._config.probe_timeout_s,
                )
        except GitSyncError as exc:
            return self._failed_probe(exc)
        default, branches = parse_ls_remote(result.stdout.decode("utf-8", errors="replace"))
        return RemoteProbe(
            ok=True,
            reachable=True,
            auth_ok=True,
            empty=not branches,
            default_branch=default,
            branches=branches,
        )

    async def read_tip_file(self, target: RemoteTarget, *, branch: str, path: str) -> bytes | None:
        branch = _branch(branch)
        if path.startswith(("/", "-")) or ".." in path.split("/"):
            raise git_error(GitErrorCode.git_error, tail="invalid path")
        async with self._scratch_store() as store:
            await self._fetch_tip(store, target, branch)
            result = await self._runner.run_local(
                ["cat-file", "blob", f"FETCH_HEAD:{path}"], git_dir=store, timeout_s=_LOCAL_TIMEOUT_S, check=False
            )
        if result.returncode == 0:
            return result.stdout
        if any(marker in result.stderr for marker in _MISSING_PATH):
            return None
        raise git_error(GitErrorCode.git_error, tail=scrub(result.stderr)[-DETAIL_TAIL_CHARS:].strip())

    async def fetch(
        self,
        git_dir: Path,
        target: RemoteTarget,
        *,
        branch: str,
        timeout_s: float | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        branch = _branch(branch)
        await self._runner.run(
            [
                "fetch",
                "--no-tags",
                "--no-recurse-submodules",
                "--no-write-fetch-head",
                "--progress",
                "--",
                target.url.display_url,
                f"+{_HEADS}{branch}:refs/remotes/origin/{branch}",
            ],
            op=GitOp.fetch,
            git_dir=git_dir,
            target=target,
            timeout_s=timeout_s or self._config.fetch_timeout_s,
            on_progress=on_progress,
        )

    async def push(
        self,
        git_dir: Path,
        target: RemoteTarget,
        *,
        local_sha: str,
        remote_branch: str,
        timeout_s: float | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        branch = _branch(remote_branch)
        if not _SHA.match(local_sha):
            raise git_error(GitErrorCode.git_error, tail="invalid commit id")
        await self._runner.run(
            [
                "push",
                "--porcelain",
                "--progress",
                "--no-verify",
                "--no-recurse-submodules",
                "--",
                target.url.display_url,
                f"{local_sha}:{_HEADS}{branch}",
            ],
            op=GitOp.push,
            git_dir=git_dir,
            target=target,
            timeout_s=timeout_s or self._config.push_timeout_s,
            on_progress=on_progress,
        )
        # Адрес передан напрямую, поэтому git сам отслеживаемую ветку не обновляет.
        await self._runner.run_local(
            ["update-ref", f"refs/remotes/origin/{branch}", local_sha], git_dir=git_dir, timeout_s=_LOCAL_TIMEOUT_S
        )

    async def _fetch_tip(self, store: Path, target: RemoteTarget, branch: str) -> None:
        base = ["fetch", "--depth=1", "--no-tags", "--no-recurse-submodules"]
        tail = ["--", target.url.display_url, f"{_HEADS}{branch}"]
        timeout_s = self._config.probe_timeout_s
        try:
            await self._runner.run(
                [*base, f"--filter=blob:limit={_TIP_BLOB_LIMIT}", *tail],
                op=GitOp.fetch,
                git_dir=store,
                target=target,
                timeout_s=timeout_s,
            )
        except GitSyncError as exc:
            if exc.code is not GitErrorCode.git_error or "filter" not in exc.detail.lower():
                raise
            await self._runner.run(base + tail, op=GitOp.fetch, git_dir=store, target=target, timeout_s=timeout_s)

    @contextlib.asynccontextmanager
    async def _scratch_store(self) -> AsyncIterator[Path]:
        """Пустое временное хранилище: probe и чтение вершины работают до того, как у проекта появилась сеть."""
        root = Path(tempfile.mkdtemp(prefix="hse-probe-"))
        try:
            store = root / "store"
            await self._runner.run_local(
                ["init", "--bare", "--quiet", str(store)], git_dir=None, timeout_s=_LOCAL_TIMEOUT_S
            )
            yield store
        finally:
            shutil.rmtree(root, ignore_errors=True)

    @staticmethod
    def _failed_probe(exc: GitSyncError) -> RemoteProbe:
        raw_keys = exc.ctx.get("host_keys")
        host_keys = tuple(key for key in raw_keys if isinstance(key, GitHostKey)) if isinstance(raw_keys, tuple) else ()
        certificate = exc.ctx.get("certificate")
        return RemoteProbe(
            ok=False,
            reachable=exc.code in _REACHABLE_CODES,
            error=GitOperationError(exc.code, exc.detail),
            host_keys=host_keys,
            certificate=certificate if isinstance(certificate, TlsCertificate) else None,
            expected_fingerprint=_text(exc.ctx.get("expected")),
            actual_fingerprint=_text(exc.ctx.get("actual")),
        )
