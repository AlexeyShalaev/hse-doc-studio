"""Streebog and GOST R 34.10-2012 verification (pure Python, via gostcrypto).

Used only to *check* signatures that arrive from КриптоПро / КриптоАРМ: neither
`cryptography` nor pyHanko speak GOST. Wire conventions (RFC 9215 / RFC 7091):

  - signature   = s || r, both big-endian;
  - public key  = LE(x) || LE(y) inside an OCTET STRING;
  - the hash output is read as a little-endian number, so it is reversed
    before it is handed to gostcrypto, which wants big-endian.

The conventions are pinned by tests against the RFC 9215 sample requests.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Any

# Signature / public-key algorithm OIDs (GOST R 34.10-2012).
OID_GOST3410_2012_256 = "1.2.643.7.1.1.1.1"
OID_GOST3410_2012_512 = "1.2.643.7.1.1.1.2"
OID_SIGN_2012_256 = "1.2.643.7.1.1.3.2"
OID_SIGN_2012_512 = "1.2.643.7.1.1.3.3"

# Legacy GOST R 34.10-2001 / R 34.11-94: no hash implementation here, so these
# can be recognised and reported but not verified.
OID_GOST3410_2001 = "1.2.643.2.2.19"
OID_SIGN_2001 = "1.2.643.2.2.3"
OID_GOSTR3411_94 = "1.2.643.2.2.9"

OID_STREEBOG_256 = "1.2.643.7.1.1.2.2"
OID_STREEBOG_512 = "1.2.643.7.1.1.2.3"

GOST_SIGNATURE_OIDS = frozenset({OID_SIGN_2012_256, OID_SIGN_2012_512, OID_GOST3410_2012_256, OID_GOST3410_2012_512})
GOST_LEGACY_OIDS = frozenset({OID_SIGN_2001, OID_GOST3410_2001, OID_GOSTR3411_94})

# Curve parameter-set OID -> gostcrypto curve name. CryptoPro-A/B/C are the
# TC26 256-bit sets B/C/D.
_CURVES: dict[str, str] = {
    "1.2.643.7.1.2.1.1.1": "id-tc26-gost-3410-2012-256-paramSetA",
    "1.2.643.2.2.35.1": "id-tc26-gost-3410-2012-256-paramSetB",
    "1.2.643.2.2.35.2": "id-tc26-gost-3410-2012-256-paramSetC",
    "1.2.643.2.2.35.3": "id-tc26-gost-3410-2012-256-paramSetD",
    # CryptoPro-XchA / XchB are key-exchange aliases of CryptoPro-A / CryptoPro-C
    # (RFC 4357). КриптоПро puts XchA into real certificates, so this matters.
    "1.2.643.2.2.36.0": "id-tc26-gost-3410-2012-256-paramSetB",
    "1.2.643.2.2.36.1": "id-tc26-gost-3410-2012-256-paramSetD",
    "1.2.643.7.1.2.1.2.1": "id-tc26-gost-3410-12-512-paramSetA",
    "1.2.643.7.1.2.1.2.2": "id-tc26-gost-3410-12-512-paramSetB",
    "1.2.643.7.1.2.1.2.3": "id-tc26-gost-3410-2012-512-paramSetC",
}


class GostError(ValueError):
    """Unsupported or malformed GOST input."""


def streebog(data: bytes, bits: int) -> bytes:
    import gostcrypto  # noqa: PLC0415

    name = "streebog256" if bits == 256 else "streebog512"
    return bytes(gostcrypto.gosthash.new(name, data=data).digest())


def hash_function(oid: str) -> Callable[[bytes], bytes] | None:
    """Digest by algorithm OID (dotted) or common name; None when unknown."""
    if oid == OID_STREEBOG_256:
        return lambda d: streebog(d, 256)
    if oid == OID_STREEBOG_512:
        return lambda d: streebog(d, 512)
    name = {"sha1": "sha1", "sha256": "sha256", "sha384": "sha384", "sha512": "sha512", "sha224": "sha224"}.get(oid)
    if name is None:
        return None
    return lambda d: hashlib.new(name, d).digest()


def verify_gost3410(
    key_bits: int,
    curve_oid: str,
    public_key_octets: bytes,
    digest: bytes,
    signature: bytes,
) -> bool:
    """Verify `signature` (wire form s||r) over `digest` (raw hash output)."""
    from gostcrypto import gostsignature  # noqa: PLC0415

    curve_name = _CURVES.get(curve_oid)
    if curve_name is None:
        raise GostError(f"Unsupported GOST curve {curve_oid}")
    size = key_bits // 8
    if len(public_key_octets) != size * 2 or len(signature) != size * 2 or len(digest) != size:
        raise GostError("GOST key, signature or digest has the wrong length")
    x = public_key_octets[:size][::-1]
    y = public_key_octets[size:][::-1]
    sig_s, sig_r = signature[:size], signature[size:]
    mode = gostsignature.MODE_256 if key_bits == 256 else gostsignature.MODE_512
    curves: dict[str, Any] = gostsignature.CURVES_R_1323565_1_024_2019
    verifier = gostsignature.new(mode, curves[curve_name])
    try:
        return bool(verifier.verify(bytearray(x + y), bytearray(digest[::-1]), bytearray(sig_r + sig_s)))
    except gostsignature.GOSTSignatureError as exc:
        raise GostError(str(exc)) from exc
