"""Порты подписей: то, что use cases получают от инфраструктуры."""

from __future__ import annotations

from typing import Protocol


class IPublicKeyExporter(Protocol):
    """Выгрузка открытого OpenPGP-ключа подписанта из связки ключей студии."""

    def export_public(self, fingerprint: str) -> bytes: ...
