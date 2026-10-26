"""Доверенный материал проверки подписи, читаемый с диска Студии."""

from __future__ import annotations

from pathlib import Path

from hse_doc_studio.core.jobs.files import InlineBlob
from hse_doc_studio.core.jobs.verify import OpenPgpTrust, OpenPgpTrustMode, TrustBundle
from hse_doc_studio.infra.signatures.openpgp import looks_like_openpgp_signature

_ROOT_SUFFIXES = {".cer", ".crt", ".pem", ".der"}


def read_trusted_roots(roots_dir: Path) -> list[bytes]:
    if not roots_dir.is_dir():
        return []
    return [p.read_bytes() for p in sorted(roots_dir.iterdir()) if p.suffix.lower() in _ROOT_SUFFIXES]


def read_chain_cache(cache_dir: Path | None) -> list[bytes]:
    """Сертификаты издателей, скачанные раньше (chain_cache): строят цепочку, доверия не дают."""
    if cache_dir is None or not cache_dir.is_dir():
        return []
    return [p.read_bytes() for p in sorted(cache_dir.glob("*.cer"))]


class LocalTrustMaterialProvider:
    """Снимок `data_dir/trusted_roots` и `data_dir/chain_cache` с теми же фильтрами и порядком, что у проверяющего.

    Связку OpenPGP не выгружает: встроенный раннер берёт постоянную `data_dir/gnupg`.
    """

    def __init__(self, roots_dir: Path, cache_dir: Path | None = None) -> None:
        self._roots_dir = roots_dir
        self._cache_dir = cache_dir

    def snapshot(self, signature: bytes | None = None) -> TrustBundle:
        """Для OpenPGP-подписи корни и кеш цепочек не читаются: проверка идет по связке gpg, как и раньше."""
        openpgp = OpenPgpTrust(mode=OpenPgpTrustMode.runner_home)
        if signature is not None and looks_like_openpgp_signature(signature):
            return TrustBundle(openpgp=openpgp)
        return TrustBundle(
            roots=tuple(InlineBlob.from_bytes(b) for b in read_trusted_roots(self._roots_dir)),
            intermediates=tuple(InlineBlob.from_bytes(b) for b in read_chain_cache(self._cache_dir)),
            openpgp=openpgp,
        )
