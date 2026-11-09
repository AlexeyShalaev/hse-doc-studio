"""Доверенный материал проверки подписи, читаемый с диска Студии."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import structlog

from hse_doc_studio.core.jobs.files import InlineBlob
from hse_doc_studio.core.jobs.verify import OpenPgpTrust, OpenPgpTrustMode, TrustBundle
from hse_doc_studio.core.signatures.errors import GpgError, GpgUnavailableError
from hse_doc_studio.infra.signatures.openpgp import GpgKeyring, looks_like_openpgp_signature

logger = structlog.get_logger()

_ROOT_SUFFIXES = {".cer", ".crt", ".pem", ".der"}
_SECRET_MARKERS = (b"PRIVATE KEY BLOCK", b"SECRET KEY")


def read_trusted_roots(roots_dir: Path) -> list[bytes]:
    if not roots_dir.is_dir():
        return []
    return [p.read_bytes() for p in sorted(roots_dir.iterdir()) if p.suffix.lower() in _ROOT_SUFFIXES]


def read_chain_cache(cache_dir: Path | None) -> list[bytes]:
    """Сертификаты издателей, скачанные раньше (chain_cache): строят цепочку, доверия не дают."""
    if cache_dir is None or not cache_dir.is_dir():
        return []
    return [p.read_bytes() for p in sorted(cache_dir.glob("*.cer"))]


def keys_digest(keys: tuple[InlineBlob, ...]) -> str:
    """Адрес содержимого открытых ключей: sha256 от sha256 каждого блока по порядку."""
    outer = hashlib.sha256()
    for key in keys:
        outer.update(hashlib.sha256(key.to_bytes()).digest())
    return outer.hexdigest()


class LocalTrustMaterialProvider:
    """Снимок `data_dir/trusted_roots`, `data_dir/chain_cache` и открытых ключей связки `data_dir/gnupg`.

    Корни и кеш читаются с теми же фильтрами и порядком, что у проверяющего. Для OpenPGP-подписи
    из связки Студии выгружаются открытые ключи ее издателей (режим `inline`): удаленный раннер
    своей связки не имеет и без них ответил бы `unknown_key` на любой ключ, даже созданный в Студии.
    Секретный материал api не покидает.
    """

    def __init__(self, roots_dir: Path, cache_dir: Path | None = None, keyring: GpgKeyring | None = None) -> None:
        self._roots_dir = roots_dir
        self._cache_dir = cache_dir
        self._keyring = keyring

    def snapshot(self, signature: bytes | None = None) -> TrustBundle:
        """Для OpenPGP-подписи корни и кеш цепочек не читаются: нужны только открытые ключи связки."""
        if signature is not None and looks_like_openpgp_signature(signature):
            return TrustBundle(openpgp=self._openpgp_trust(signature))
        return TrustBundle(
            roots=tuple(InlineBlob.from_bytes(b) for b in read_trusted_roots(self._roots_dir)),
            intermediates=tuple(InlineBlob.from_bytes(b) for b in read_chain_cache(self._cache_dir)),
            openpgp=OpenPgpTrust(mode=OpenPgpTrustMode.runner_home),
        )

    def _openpgp_trust(self, signature: bytes) -> OpenPgpTrust:
        """Открытые ключи издателей подписи; если издателя прочесть не вышло, все открытые ключи связки.

        Без gpg на стороне api выгружать нечего: остается `runner_home`, как до второго этапа.
        Ключа издателя в связке нет: `inline` без ключей, и раннер честно ответит `unknown_key`.
        """
        keyring = self._keyring
        if keyring is None or not keyring.available:
            return OpenPgpTrust(mode=OpenPgpTrustMode.runner_home)
        try:
            issuers = keyring.signature_issuers(signature)
            armored = keyring.export_public_keys(issuers)
        except (GpgError, GpgUnavailableError, OSError, subprocess.SubprocessError) as exc:
            logger.warning("trust_material: openpgp keys not exported", error=str(exc))
            return OpenPgpTrust(mode=OpenPgpTrustMode.runner_home)
        if any(marker in armored for marker in _SECRET_MARKERS):
            # `gpg --export` секретов не выдает; защита на случай чужого бинарника.
            logger.error("trust_material: secret key material in public export, dropped")
            armored = b""
        keys = (InlineBlob.from_bytes(armored),) if armored.strip() else ()
        return OpenPgpTrust(mode=OpenPgpTrustMode.inline, keys=keys, digest=keys_digest(keys))
