"""Builds a self-signed GOST R 34.10-2012 certificate and a detached CMS signature.

Hand-rolled DER: neither `cryptography` nor asn1crypto can create GOST objects.
Signing goes through gostcrypto with the wire conventions of RFC 9215.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone

import gostcrypto
from gostcrypto import gostsignature
from hse_doc_studio.infra.signatures import gost

CURVE_OID = "1.2.643.7.1.2.1.1.1"  # id-tc26-gost-3410-2012-256-paramSetA
_CURVE = gostsignature.CURVES_R_1323565_1_024_2019["id-tc26-gost-3410-2012-256-paramSetA"]


def _tlv(tag: int, body: bytes) -> bytes:
    n = len(body)
    if n < 0x80:
        head = bytes([tag, n])
    else:
        raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
        head = bytes([tag, 0x80 | len(raw), *raw])
    return head + body


def _oid(dotted: str) -> bytes:
    parts = [int(p) for p in dotted.split(".")]
    body = bytearray([parts[0] * 40 + parts[1]])
    for p in parts[2:]:
        chunk = [p & 0x7F]
        p >>= 7
        while p:
            chunk.append(0x80 | (p & 0x7F))
            p >>= 7
        body.extend(reversed(chunk))
    return _tlv(0x06, bytes(body))


def _seq(*items: bytes) -> bytes:
    return _tlv(0x30, b"".join(items))


def _set(*items: bytes) -> bytes:
    return _tlv(0x31, b"".join(items))


def _int(value: int) -> bytes:
    raw = value.to_bytes(max(1, (value.bit_length() + 8) // 8), "big")
    return _tlv(0x02, raw)


def _utc(dt: datetime) -> bytes:
    return _tlv(0x17, dt.strftime("%y%m%d%H%M%SZ").encode())


def _name(cn: str, extra: tuple[tuple[str, str], ...] = ()) -> bytes:
    rdns = [_set(_seq(_oid("2.5.4.3"), _tlv(0x0C, cn.encode())))]
    rdns.extend(_set(_seq(_oid(o), _tlv(0x0C, v.encode()))) for o, v in extra)
    return _seq(*rdns)


@dataclass(frozen=True)
class GostIdentity:
    private_key: bytes
    cert_der: bytes
    name_der: bytes
    serial: int

    def sign_digest(self, digest: bytes) -> bytes:
        """Wire-form signature (s || r) over a raw 32-byte Streebog digest."""
        signer = gostsignature.new(gostsignature.MODE_256, _CURVE)
        rs = bytes(signer.sign(bytearray(self.private_key), bytearray(digest[::-1])))
        return rs[32:] + rs[:32]


def make_identity(cn: str = "Иванов Иван Иванович", snils: str = "12345678901") -> GostIdentity:
    private = os.urandom(32)
    verifier = gostsignature.new(gostsignature.MODE_256, _CURVE)
    pub = bytes(verifier.public_key_generate(bytearray(private)))
    pub_le = pub[:32][::-1] + pub[32:][::-1]
    spki = _seq(
        _seq(_oid(gost.OID_GOST3410_2012_256), _seq(_oid(CURVE_OID))),
        _tlv(0x03, b"\x00" + _tlv(0x04, pub_le)),
    )
    name = _name(cn, (("1.2.643.100.3", snils),))
    serial = int.from_bytes(os.urandom(8), "big")
    sig_alg = _seq(_oid(gost.OID_SIGN_2012_256))
    tbs = _seq(
        _tlv(0xA0, _int(2)),
        _int(serial),
        sig_alg,
        name,
        _seq(
            _utc(datetime(2020, 1, 1, tzinfo=timezone.utc)),
            _utc(datetime(2049, 1, 1, tzinfo=timezone.utc)),
        ),
        name,
        spki,
    )
    ident = GostIdentity(private_key=private, cert_der=b"", name_der=name, serial=serial)
    digest = bytes(gostcrypto.gosthash.new("streebog256", data=tbs).digest())
    sig = ident.sign_digest(digest)
    cert = _seq(tbs, sig_alg, _tlv(0x03, b"\x00" + sig))
    return GostIdentity(private_key=private, cert_der=cert, name_der=name, serial=serial)


def make_detached_cms(ident: GostIdentity, content: bytes, signed_at: datetime | None = None) -> bytes:
    """DER CMS SignedData (detached, signed attributes, Streebog-256 + GOST 2012-256)."""
    signed_at = signed_at or datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
    md = bytes(gostcrypto.gosthash.new("streebog256", data=content).digest())
    attrs_body = b"".join(
        [
            _seq(_oid("1.2.840.113549.1.9.3"), _set(_oid("1.2.840.113549.1.7.1"))),
            _seq(_oid("1.2.840.113549.1.9.5"), _set(_utc(signed_at))),
            _seq(_oid("1.2.840.113549.1.9.4"), _set(_tlv(0x04, md))),
        ]
    )
    # DER SET OF sorts members; the three attributes above are built in that order.
    attrs_set = _tlv(0x31, attrs_body)
    to_sign = bytes(gostcrypto.gosthash.new("streebog256", data=attrs_set).digest())
    sig = ident.sign_digest(to_sign)
    digest_alg = _seq(_oid(gost.OID_STREEBOG_256))
    signer = _seq(
        _int(1),
        _seq(ident.name_der, _int(ident.serial)),
        digest_alg,
        _tlv(0xA0, attrs_body),
        _seq(_oid(gost.OID_SIGN_2012_256)),
        _tlv(0x04, sig),
    )
    signed = _seq(
        _int(1),
        _set(digest_alg),
        _seq(_oid("1.2.840.113549.1.7.1")),
        _tlv(0xA0, ident.cert_der),
        _set(signer),
    )
    return _seq(_oid("1.2.840.113549.1.7.2"), _tlv(0xA0, signed))
