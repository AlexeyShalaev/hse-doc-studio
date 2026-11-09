"""Открытая часть ключа подписанта из загруженного файла: сертификат X.509 или открытый ключ OpenPGP.

Закрытый ключ отвергается до разбора: блок PEM `... PRIVATE KEY`, контейнер PKCS#12 и секретный ключ OpenPGP, который
распознаёт сам gpg, как перед импортом в связку (`GpgKeyring.contains_secret_key`). В общую связку ключей сервера
ничего не попадает: файл OpenPGP читается через `gpg --show-keys`, поэтому имя и почта из ключа не видны другим людям.
Данные плашки собираются теми же функциями, что у плашки слота, поэтому выглядят одинаково.
"""

from __future__ import annotations

import asyncio

from asn1crypto import pem

from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.signatures.errors import CmsParseError, GpgError, GpgUnavailableError
from hse_doc_studio.core.signatures.signer_profile import (
    MAX_PROFILE_KEY_BYTES,
    PublicKeyData,
    PublicKeyKind,
    SecretKeyMaterialError,
)
from hse_doc_studio.infra.signatures.key_material import certificate_der, holds_private_key
from hse_doc_studio.infra.signatures.openpgp import GpgKeyring
from hse_doc_studio.use_cases.signatures._studio_signer import openpgp_signer, x509_signer


def _not_a_key() -> ValueError:
    return ValueError(
        localized_error(
            "Файл не похож на сертификат X.509 (.cer, .crt, .pem) или открытый ключ OpenPGP (.asc)",
            "The file is not an X.509 certificate (.cer, .crt, .pem) or an OpenPGP public key (.asc)",
        )
    )


class PublicKeyReader:
    """IPublicKeyReader поверх общей связки gpg, в которую он ничего не импортирует."""

    def __init__(self, keyring: GpgKeyring) -> None:
        self._keyring = keyring

    async def read(self, blob: bytes) -> PublicKeyData:
        if not blob:
            raise ValueError(localized_error("Загружен пустой файл", "Empty file upload"))
        if len(blob) > MAX_PROFILE_KEY_BYTES:
            raise ValueError(
                localized_error(
                    "Файл слишком большой для сертификата или открытого ключа",
                    "The file is too large for a certificate or a public key",
                )
            )
        if holds_private_key(blob):
            raise SecretKeyMaterialError
        der = certificate_der(blob)
        if der is None:
            return await self._openpgp(blob)
        try:
            plate = x509_signer(der)
        except CmsParseError as exc:
            raise _not_a_key() from exc
        return PublicKeyData(PublicKeyKind.x509, pem.armor("CERTIFICATE", der), plate)

    async def _openpgp(self, blob: bytes) -> PublicKeyData:
        if not self._keyring.available:
            raise ValueError(
                localized_error(
                    "В системе нет gpg: открытый ключ OpenPGP не прочитать. Загрузите сертификат X.509",
                    "gpg is not installed: the OpenPGP public key cannot be read. Upload an X.509 certificate",
                )
            )
        try:
            secret = await asyncio.to_thread(self._keyring.contains_secret_key, blob)
            keys = [] if secret else await asyncio.to_thread(self._keyring.show_keys, blob)
        except (GpgUnavailableError, GpgError) as exc:
            raise _not_a_key() from exc
        if secret:
            raise SecretKeyMaterialError
        if not keys:
            raise _not_a_key()
        if len(keys) > 1:
            raise ValueError(
                localized_error(
                    "В файле несколько ключей: загрузите один открытый ключ (gpg --export --armor <отпечаток>)",
                    "The file holds several keys: upload one public key (gpg --export --armor <fingerprint>)",
                )
            )
        return PublicKeyData(PublicKeyKind.openpgp, blob, openpgp_signer(keys[0]))
