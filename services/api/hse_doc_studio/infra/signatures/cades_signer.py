"""CAdES detached signatures via cryptography (PKCS#7 / CMS).

Creates a standard DER-encoded detached SignedData blob (.sig / .p7s) that
covers the bytes of an arbitrary file.  No pyHanko dependency — uses only
`cryptography` which is already a base dependency.

Verifiable with:
  - КриптоАРМ, КриптоПро (provided the cert is trusted)
  - Госуслуги portal (upload doc + .sig)
  - openssl cms -verify -inform DER -in doc.pdf.sig -content doc.pdf ...
"""

from __future__ import annotations

from pathlib import Path

import structlog

logger = structlog.get_logger()


class UnsupportedSigningKeyError(ValueError):
    """`key_dir/key.pem` holds a key type PKCS#7 SignedData cannot sign with.

    PKCS#7 / CMS defines signature algorithms for RSA and ECDSA only, so an
    Ed25519 / Ed448 / DSA / DH / X25519 key — all of which
    `load_pem_private_key` happily returns — has no valid CAdES encoding.
    Raised instead of letting `add_signer` fail deep inside `cryptography`,
    so the caller logs a message that names the actual problem.
    """


def sign_detached(data_path: Path, sig_path: Path, key_dir: Path) -> None:
    """Create a CAdES detached signature for `data_path`, write to `sig_path`.

    Reads `key_dir/key.pem` (RSA/ECDSA private key, no passphrase) and
    `key_dir/cert.pem` (end-entity certificate).  Produces a DER-encoded
    PKCS#7 detached SignedData that covers the raw bytes of `data_path`.
    """
    from cryptography import x509  # noqa: PLC0415
    from cryptography.hazmat.primitives import hashes, serialization  # noqa: PLC0415
    from cryptography.hazmat.primitives.asymmetric import ec, rsa  # noqa: PLC0415
    from cryptography.hazmat.primitives.serialization import pkcs7  # noqa: PLC0415

    key_pem = (key_dir / "key.pem").read_bytes()
    cert_pem = (key_dir / "cert.pem").read_bytes()

    private_key = serialization.load_pem_private_key(key_pem, password=None)
    if not isinstance(private_key, rsa.RSAPrivateKey | ec.EllipticCurvePrivateKey):
        raise UnsupportedSigningKeyError(
            f"Unsupported private key type for CAdES: {type(private_key).__name__}; "
            f"expected an RSA or ECDSA key in {key_dir / 'key.pem'}"
        )
    cert = x509.load_pem_x509_certificate(cert_pem)

    data = data_path.read_bytes()

    sig_bytes = (
        pkcs7.PKCS7SignatureBuilder()
        .set_data(data)
        .add_signer(cert, private_key, hashes.SHA256())
        .sign(serialization.Encoding.DER, [pkcs7.PKCS7Options.DetachedSignature])
    )

    sig_path.parent.mkdir(parents=True, exist_ok=True)
    sig_path.write_bytes(sig_bytes)
    logger.debug("cades_signer: detached sig written", sig=str(sig_path), size=len(sig_bytes))
