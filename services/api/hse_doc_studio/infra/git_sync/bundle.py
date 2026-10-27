"""Переносной файл проекта: git bundle одной ветки, при желании под паролем (порт IGitBundleService).

В файл попадает только `refs/heads/<ветка>`: служебные ссылки хранилища (`refs/hse/template/*`, отслеживаемые
ветки, теги) наружу не уходят. Чужой файл разбирается без доверия: заголовок читается до запуска git, ветка
берётся в отдельную ссылку `refs/hse/bundle/*`, а объекты проверяются тем же `fsck`, что и при сетевой выборке.
"""

from __future__ import annotations

import os
from pathlib import Path

import structlog

from hse_doc_studio.api.config import GitConfig
from hse_doc_studio.core.export_import.encryption import SALT_LENGTH
from hse_doc_studio.core.git_sync.bundle_crypto import (
    SNIFF_BYTES,
    BundleCryptoError,
    BundleFormat,
    WrongPasswordError,
    check_password,
    decrypt_stream,
    encrypt_stream,
    sniff,
)
from hse_doc_studio.core.git_sync.bundle_header import MAX_HEADER_BYTES, BundleHeader, parse_bundle_header
from hse_doc_studio.core.git_sync.error_classifier import DETAIL_TAIL_CHARS, scrub
from hse_doc_studio.core.git_sync.error_messages import git_error
from hse_doc_studio.core.git_sync.errors import GitErrorCode
from hse_doc_studio.core.git_sync.protocols import IGitRemoteRunner
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.vcs.errors import VcsInvalidRefError
from hse_doc_studio.core.vcs.refs import validate_ref_name
from hse_doc_studio.infra.vcs.git_vcs_service import store_git_dir

logger = structlog.get_logger()

_PLAIN_NAME = "bundle.plain"
_PREREQUISITES_MARKER = "prerequisite"
_SHA1_ONLY = "object-format=sha1"
_OBJECT_FORMAT = "object-format="
_FILTER = "filter"


class GitBundleService:
    def __init__(self, runner: IGitRemoteRunner, config: GitConfig) -> None:
        self._runner = runner
        self._timeout_s = config.bundle_timeout_s

    # --- чужой файл ------------------------------------------------------------------------------------------

    def check_upload(self, source: Path, password: Secret | None) -> BundleFormat:
        with source.open("rb") as stream:
            head = stream.read(MAX_HEADER_BYTES)
            kind = sniff(head[:SNIFF_BYTES])
            if kind is BundleFormat.plain:
                if parse_bundle_header(head) is None:
                    raise git_error(GitErrorCode.bundle_invalid)
                return kind
            if kind is not BundleFormat.encrypted:
                raise git_error(GitErrorCode.bundle_invalid)
            if not password:
                raise git_error(GitErrorCode.bundle_password_required)
            stream.seek(0)
            try:
                check_password(stream, password.reveal())
            except WrongPasswordError:
                raise git_error(GitErrorCode.bundle_password_wrong) from None
            except BundleCryptoError:
                raise git_error(GitErrorCode.bundle_invalid) from None
        return kind

    def unpack(self, source: Path, workdir: Path, password: Secret | None) -> Path:
        with source.open("rb") as stream:
            kind = sniff(stream.read(SNIFF_BYTES))
            if kind is BundleFormat.plain:
                return source
            if kind is not BundleFormat.encrypted:
                raise git_error(GitErrorCode.bundle_invalid)
            if not password:
                raise git_error(GitErrorCode.bundle_password_required)
            stream.seek(0)
            target = workdir / _PLAIN_NAME
            try:
                with target.open("wb") as out:
                    decrypt_stream(stream, out, password.reveal())
            except WrongPasswordError:
                raise git_error(GitErrorCode.bundle_password_wrong) from None
            except BundleCryptoError:
                raise git_error(GitErrorCode.bundle_invalid) from None
        return target

    def read_header(self, plain: Path) -> BundleHeader:
        with plain.open("rb") as stream:
            header = parse_bundle_header(stream.read(MAX_HEADER_BYTES))
        if header is None or not self._supported(header):
            raise git_error(GitErrorCode.bundle_invalid)
        return header

    @staticmethod
    def _supported(header: BundleHeader) -> bool:
        """Хранилища Студии работают на sha1 и без частичных клонов: другие файлы git открыл бы, но не так, как надо."""
        formats = [item for item in header.capabilities if item.startswith(_OBJECT_FORMAT)]
        return all(item == _SHA1_ONLY for item in formats) and not any(
            item.startswith(_FILTER) for item in header.capabilities
        )

    async def verify(self, folder: Path, plain: Path) -> None:
        result = await self._runner.run_local(
            ["bundle", "verify", str(plain)], git_dir=store_git_dir(folder), timeout_s=self._timeout_s, check=False
        )
        if result.returncode == 0:
            return
        tail = scrub(result.stderr)[-DETAIL_TAIL_CHARS:].strip()
        logger.info("bundle verify failed", tail=tail)
        if _PREREQUISITES_MARKER in result.stderr:
            raise git_error(GitErrorCode.bundle_prerequisites_missing)
        raise git_error(GitErrorCode.bundle_invalid)

    async def stage_branch(self, folder: Path, plain: Path, *, branch: str, ref: str) -> str:
        git_dir = store_git_dir(folder)
        fetched = await self._runner.run_local(
            [
                "fetch",
                "--no-tags",
                "--no-write-fetch-head",
                "--no-recurse-submodules",
                "--",
                str(plain),
                f"+refs/heads/{_branch(branch)}:{ref}",
            ],
            git_dir=git_dir,
            timeout_s=self._timeout_s,
            check=False,
            # Bundle открывается как локальный файл: другие транспорты остаются закрытыми.
            allow_protocol="file",
        )
        if fetched.returncode != 0:
            logger.info("bundle unpack failed", tail=scrub(fetched.stderr)[-DETAIL_TAIL_CHARS:].strip())
            raise git_error(GitErrorCode.bundle_invalid)
        tip = await self._runner.run_local(
            ["rev-parse", "--verify", f"{ref}^{{commit}}"], git_dir=git_dir, timeout_s=self._timeout_s
        )
        return tip.stdout.decode("ascii", errors="replace").strip()

    # --- свой файл -------------------------------------------------------------------------------------------

    async def create_bundle(self, folder: Path, *, branch: str, dest: Path) -> None:
        await self._runner.run_local(
            ["bundle", "create", str(dest), f"refs/heads/{_branch(branch)}"],
            git_dir=store_git_dir(folder),
            timeout_s=self._timeout_s,
        )

    def encrypt_bundle(self, plain: Path, dest: Path, password: Secret) -> None:
        with plain.open("rb") as source, dest.open("wb") as target:
            encrypt_stream(source, target, password.reveal(), salt=os.urandom(SALT_LENGTH))


def _branch(name: str) -> str:
    try:
        return validate_ref_name(name)
    except VcsInvalidRefError:
        raise git_error(GitErrorCode.branch_missing) from None
