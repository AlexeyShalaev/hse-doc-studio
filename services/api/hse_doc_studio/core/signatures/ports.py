"""Порты проверки открепленных подписей: use cases видят их, а не gpg и сеть."""

from __future__ import annotations

from typing import Protocol

from hse_doc_studio.core.jobs.verify import TrustBundle


class IOpenPgpKeyImporter(Protocol):
    """Связка ключей OpenPGP в той части, что нужна при прикреплении подписи."""

    def looks_like_public_key(self, blob: bytes) -> bool: ...

    def import_public_key(self, blob: bytes) -> None:
        """Кладет открытый ключ в связку; бросает GpgUnavailableError (нет gpg) или GpgError (ключ не принят)."""
        ...


class IChainFetcher(Protocol):
    """Достройка цепочки сертификатов подписи по ссылкам AIA (единственное место, где Студия ходит в сеть)."""

    def complete(self, sig_bytes: bytes) -> list[str]:
        """Скачивает недостающие сертификаты издателей; бросает CmsParseError, если подпись не CMS."""
        ...


class ITrustMaterialProvider(Protocol):
    """Доверенный материал проверки подписи: корни, кеш цепочек и режим связки OpenPGP."""

    def snapshot(self) -> TrustBundle: ...
