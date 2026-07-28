"""Password-based field encryption for the settings export/import bundle.

A single secret (an AI provider ``api_key``) is encrypted on its own with a
per-field random salt so the exported JSON can be shared without leaking keys.
PBKDF2-HMAC-SHA256 derives a Fernet key from the user's password; the salt is
prepended so decryption only needs the password.
"""

from __future__ import annotations

import base64
import os

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

_PBKDF2_ITERATIONS = 600_000
_KEY_LENGTH = 32
_SALT_LENGTH = 16


def _derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=_KEY_LENGTH,
        salt=salt,
        iterations=_PBKDF2_ITERATIONS,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))


def encrypt_token(token: str, password: str) -> str:
    """Encrypt ``token`` and return ``base64(salt):fernet_ciphertext``."""
    salt = os.urandom(_SALT_LENGTH)
    fernet = Fernet(_derive_key(password, salt))
    ciphertext = fernet.encrypt(token.encode())
    salt_b64 = base64.urlsafe_b64encode(salt).decode()
    return f"{salt_b64}:{ciphertext.decode()}"


def decrypt_token(encrypted_token: str, password: str) -> str:
    """Reverse :func:`encrypt_token`.

    Raises ``ValueError`` on a malformed payload or a wrong password (so the
    caller can report "incorrect password" rather than leaking a stack trace).
    """
    try:
        salt_b64, ciphertext = encrypted_token.split(":", 1)
    except ValueError as exc:
        raise ValueError("invalid encrypted token format") from exc

    salt = base64.urlsafe_b64decode(salt_b64)
    fernet = Fernet(_derive_key(password, salt))
    try:
        return fernet.decrypt(ciphertext.encode()).decode()
    except Exception as exc:
        raise ValueError("failed to decrypt — incorrect password or corrupted data") from exc
