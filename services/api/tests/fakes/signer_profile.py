from __future__ import annotations

import datetime
import struct
import zlib
from dataclasses import dataclass, replace

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from hse_doc_studio.core.signatures.signer_profile import ProfileImage, ProfilePublicKey, SignerProfile


class InMemorySignerProfileRepository:
    """ISignerProfileRepository в памяти: профиль без картинки и ключа не хранится, как строка в Postgres."""

    def __init__(self) -> None:
        self.profiles: dict[str, SignerProfile] = {}
        self.images: dict[str, bytes] = {}

    async def get(self, user_id: str) -> SignerProfile:
        return self.profiles.get(user_id) or SignerProfile(user_id=user_id)

    async def read_image(self, user_id: str) -> bytes | None:
        return self.images.get(user_id)

    async def save_image(self, user_id: str, png: bytes, image: ProfileImage) -> None:
        self.images[user_id] = png
        self.profiles[user_id] = replace(await self.get(user_id), image=image)

    async def clear_image(self, user_id: str) -> bool:
        found = self.images.pop(user_id, None) is not None
        self._store(replace(await self.get(user_id), image=None))
        return found

    async def save_public_key(self, user_id: str, key: ProfilePublicKey) -> None:
        self.profiles[user_id] = replace(await self.get(user_id), public_key=key)

    async def clear_public_key(self, user_id: str) -> bool:
        profile = await self.get(user_id)
        self._store(replace(profile, public_key=None))
        return profile.public_key is not None

    def _store(self, profile: SignerProfile) -> None:
        if profile.empty:
            self.profiles.pop(profile.user_id, None)
        else:
            self.profiles[profile.user_id] = profile


def make_png(width: int = 300, height: int = 100) -> bytes:
    """Настоящий PNG с прозрачным фоном нужного размера."""

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    raw = b"".join(b"\x00" + b"\xff\xff\xff\x00" * width for _ in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


@dataclass(frozen=True)
class SelfSigned:
    cert_pem: bytes
    cert_der: bytes
    key_pem: bytes
    # Ключ и сертификат вместе, как их выдаёт удостоверяющий центр (.p12, пароль `pw`).
    p12: bytes


def make_self_signed(owner: str = "Анна Смирнова", serial: int = 0xABC) -> SelfSigned:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, owner)])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(serial)
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=30))
        .sign(key, hashes.SHA256())
    )
    return SelfSigned(
        cert_pem=cert.public_bytes(serialization.Encoding.PEM),
        cert_der=cert.public_bytes(serialization.Encoding.DER),
        key_pem=key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        ),
        p12=pkcs12.serialize_key_and_certificates(
            b"signer", key, cert, None, serialization.BestAvailableEncryption(b"pw")
        ),
    )
