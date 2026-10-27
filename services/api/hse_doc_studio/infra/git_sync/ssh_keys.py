"""Ключи доступа ssh: Ed25519 на `cryptography`, без ssh-keygen (его нет в образе)."""

from __future__ import annotations

import base64
import hashlib

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

from hse_doc_studio.core.git_sync.protocols import GeneratedSshKey
from hse_doc_studio.core.git_sync.secret import Secret


def public_key_fingerprint(public_line: str) -> str:
    """`SHA256:...` по строке authorized_keys, как печатает `ssh-keygen -lf`."""
    blob = base64.b64decode(public_line.split()[1])
    digest = hashlib.sha256(blob).digest()
    return "SHA256:" + base64.b64encode(digest).decode().rstrip("=")


class Ed25519KeyGenerator:
    """Закрытый ключ без парольной фразы: защита на диске обеспечивается шифром секретов, а спросить фразу при
    фоновой выборке некому."""

    def generate(self, comment: str) -> GeneratedSshKey:
        key = Ed25519PrivateKey.generate()
        private = key.private_bytes(Encoding.PEM, PrivateFormat.OpenSSH, NoEncryption()).decode()
        public = key.public_key().public_bytes(Encoding.OpenSSH, PublicFormat.OpenSSH).decode()
        return GeneratedSshKey(
            private_key=Secret(private),
            public_key=f"{public} {comment}".strip(),
            fingerprint_sha256=public_key_fingerprint(public),
        )
