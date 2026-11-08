"""Порты подписей: то, что use cases получают от инфраструктуры (gpg, сеть, связка ключей)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from hse_doc_studio.core.jobs.verify import TrustBundle

if TYPE_CHECKING:
    from hse_doc_studio.core.entities import Project


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

    def snapshot(self, signature: bytes | None = None) -> TrustBundle:
        """Материал для проверки; `signature` подсказка: сертификаты OpenPGP-подписи не нужны, их можно не читать."""
        ...


class IPublicKeyExporter(Protocol):
    """Выгрузка открытого OpenPGP-ключа подписанта из связки ключей студии."""

    def export_public(self, fingerprint: str) -> bytes: ...


class ISignerScope(Protocol):
    """Чьи слоты подписывает смотрящий: его персоны в проекте (docs/design/signature-plan.md, раздел 5)."""

    async def personas(self, project: Project) -> frozenset[str]:
        """Слаги авторов и роли руководителей, к которым привязан актор; `author` у владельца solo-проекта.

        Локально человек один и он автор: все персоны авторов проекта. Пустое множество: своих слотов нет.
        """
        ...
