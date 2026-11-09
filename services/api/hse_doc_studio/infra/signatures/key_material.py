"""Что лежит в файле ключа: закрытый ключ или сертификат X.509, без расшифровки и без записи куда-либо.

Нужно там, где Студия принимает только открытую часть (профиль подписанта): закрытый ключ узнаётся по блоку PEM любого
вида (`PRIVATE KEY`, `RSA PRIVATE KEY`, `ENCRYPTED PRIVATE KEY`, `PGP PRIVATE KEY BLOCK`) и по контейнеру PKCS#12,
который хранит ключ вместе с сертификатом и обычно закрыт паролем. Секретный ключ OpenPGP в двоичном виде или под
чужим заголовком распознаёт gpg (`GpgKeyring.contains_secret_key`).
"""

from __future__ import annotations

import re

from asn1crypto import pem, pkcs12, x509

_PEM_PRIVATE = re.compile(rb"-----BEGIN [A-Z0-9 ]*PRIVATE KEY")


def holds_private_key(blob: bytes) -> bool:
    """Блок PEM с закрытым ключом где угодно в файле или контейнер PKCS#12 (.p12, .pfx)."""
    return _PEM_PRIVATE.search(blob) is not None or _is_pkcs12(blob)


def _is_pkcs12(blob: bytes) -> bool:
    try:
        pfx = pkcs12.Pfx.load(blob)
        return pfx["version"].native == "v3" and pfx["auth_safe"]["content_type"].native is not None
    except Exception:
        return False


def certificate_der(blob: bytes) -> bytes | None:
    """DER сертификата X.509: сам файл DER или первый блок `CERTIFICATE` файла PEM. None: в файле нет сертификата.

    Возвращаются только байты сертификата: хвост файла и другие блоки PEM отбрасываются.
    """
    if pem.detect(blob):
        try:
            der = next((body for name, _, body in pem.unarmor(blob, multiple=True) if name == "CERTIFICATE"), None)
        except ValueError:
            return None
    else:
        der = blob
    if der is None:
        return None
    try:
        cert = x509.Certificate.load(der)
        # Разбор ленивый: поля читаются здесь, чтобы чужая структура ASN.1 не прошла за сертификат.
        _ = cert.serial_number, cert["tbs_certificate"]["validity"]["not_after"].native, cert.subject.native
        return cert.dump()
    except Exception:
        return None
