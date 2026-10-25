"""Inspect and verify detached CMS / CAdES signatures (RSA, ECDSA and GOST).

Parsing goes through asn1crypto (already a pyHanko dependency). asn1crypto does
not know GOST public keys, so the SubjectPublicKeyInfo is always taken apart as
a raw ASN.1 sequence.

What is checked, per signer:
  - messageDigest against the file (SHA-1/2, Streebog-256/512);
  - the signature itself against the key in the signer's certificate
    (RSA PKCS#1 v1.5 / PSS, ECDSA, GOST R 34.10-2012);
  - the certificate validity window at signing time;
  - the chain to a root from `trusted_roots`. Without a matching root the
    signer is reported, but the chain is never called trusted. Revocation
    (CRL / OCSP) is not checked.
"""

from __future__ import annotations

import contextlib
import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

import structlog
from asn1crypto import cms, core, pem, x509

from hse_doc_studio.infra.signatures import gost

logger = structlog.get_logger()

ChainStatus = Literal["trusted", "untrusted_root", "incomplete", "broken"]
Verdict = Literal["valid", "invalid", "unverified"]

_NAME_FIELDS = {
    "2.5.4.3": "common_name",
    "2.5.4.4": "surname",
    "2.5.4.42": "given_name",
    "2.5.4.10": "organization",
    "2.5.4.11": "unit",
    "2.5.4.12": "title",
    "2.5.4.6": "country",
    "1.2.840.113549.1.9.1": "email",
    "1.2.643.100.3": "snils",
    "1.2.643.3.131.1.1": "inn",
    "1.2.643.100.4": "inn_le",
    "1.2.643.100.1": "ogrn",
    "1.2.643.100.5": "ogrnip",
}

_MAX_CHAIN = 8
_QUALIFIED_POLICY_PREFIX = "1.2.643.100.113."


class CmsParseError(ValueError):
    """The blob is not a CMS SignedData structure."""


@dataclass(frozen=True)
class SignerReport:
    subject: str
    subject_fields: dict[str, str]
    issuer: str
    serial: str
    not_before: datetime
    not_after: datetime
    fingerprint_sha256: str
    signed_at: datetime | None
    digest_algorithm: str
    signature_algorithm: str
    digest_match: bool | None  # None: no signed attributes, the signature covers the file directly
    signature_valid: bool | None  # None: algorithm not supported here
    signature_note: str
    cert_valid_at_signing: bool | None
    chain: ChainStatus
    verdict: Verdict
    notes: list[str] = field(default_factory=list)
    # Chain ends in a self-signed certificate nobody trusts yet: who it is, so the user can decide.
    chain_root_subject: str = ""
    chain_root_fingerprint: str = ""


def inspect_cms(
    sig_bytes: bytes,
    content: bytes,
    trusted_roots: Sequence[bytes] = (),
    intermediates: Sequence[bytes] = (),
) -> list[SignerReport]:
    """Parse a detached CMS signature and verify each signer against `content`.

    `intermediates` (fetched issuer certificates) only help to build the chain: trust
    comes from `trusted_roots` alone.
    """
    der = _to_der(sig_bytes)
    try:
        info = cms.ContentInfo.load(der)
        if info["content_type"].native != "signed_data":
            raise CmsParseError("not a SignedData structure")
        signed = info["content"]
        signer_infos = list(signed["signer_infos"])
        embedded = [c.chosen for c in (signed["certificates"] or []) if c.name == "certificate"]
    except CmsParseError:
        raise
    except Exception as exc:
        raise CmsParseError(f"cannot parse CMS: {exc}") from exc
    if not signer_infos:
        raise CmsParseError("signature has no signers")

    roots = [_load_cert(r) for r in trusted_roots]
    roots = [r for r in roots if r is not None]
    extra = [c for c in (_load_cert(i) for i in intermediates) if c is not None]
    return [_inspect_signer(si, [*embedded, *extra], roots, content) for si in signer_infos]


@dataclass(frozen=True)
class CertificateInfo:
    owner: str
    serial: str  # upper-case hex, as КриптоПро prints it
    not_before: datetime
    not_after: datetime
    fingerprint_sha256: str
    # The certificate carries a КриптоПро class policy (КС1-КА1, 1.2.643.100.113.x), which
    # accredited CAs put into qualified certificates. A hint, not a legal conclusion.
    qualified_hint: bool = False


def _has_qualified_policy(cert: x509.Certificate) -> bool:
    for ext in cert["tbs_certificate"]["extensions"] or []:
        if ext["extn_id"].native == "certificate_policies":
            return any(
                p["policy_identifier"].dotted.startswith(_QUALIFIED_POLICY_PREFIX) for p in ext["extn_value"].parsed
            )
    return False


def describe_certificate(blob: bytes) -> CertificateInfo:
    """Owner, serial and validity of an X.509 certificate (DER or PEM), GOST included."""
    try:
        cert = x509.Certificate.load(_to_der(blob))
        validity = cert["tbs_certificate"]["validity"]
        return CertificateInfo(
            owner=subject_display(cert),
            serial=format(cert.serial_number, "X"),
            not_before=validity["not_before"].native,
            not_after=validity["not_after"].native,
            fingerprint_sha256=hashlib.sha256(cert.dump()).hexdigest(),
            qualified_hint=_has_qualified_policy(cert),
        )
    except Exception as exc:
        raise CmsParseError(f"not an X.509 certificate: {exc}") from exc


def looks_like_cms(blob: bytes) -> bool:
    """Cheap format sniff: PEM CMS/PKCS7 or a DER SEQUENCE carrying the signedData OID."""
    head = blob[:64].lstrip()
    if head.startswith((b"-----BEGIN PKCS7", b"-----BEGIN CMS")):
        return True
    return blob[:1] == b"\x30" and b"\x2a\x86\x48\x86\xf7\x0d\x01\x07\x02" in blob[:32]


def _to_der(blob: bytes) -> bytes:
    if pem.detect(blob):
        return pem.unarmor(blob)[2]
    return blob


def _load_cert(der: bytes) -> x509.Certificate | None:
    try:
        return x509.Certificate.load(_to_der(der))
    except Exception:
        return None


def _name_fields(name: x509.Name) -> dict[str, str]:
    fields: dict[str, str] = {}
    for rdn in name.chosen:
        for item in rdn:
            key = _NAME_FIELDS.get(item["type"].dotted)
            if key is None:
                continue
            with contextlib.suppress(Exception):
                fields.setdefault(key, str(item["value"].native))
    return fields


def _display_name(fields: dict[str, str]) -> str:
    person = " ".join(p for p in (fields.get("surname"), fields.get("given_name")) if p)
    return fields.get("common_name") or person or fields.get("organization") or ""


def subject_display(cert: x509.Certificate) -> str:
    """Human name of a certificate subject (CN, else surname + given name, else organization)."""
    return _display_name(_name_fields(cert.subject))


def _find_signer_cert(signer: cms.SignerInfo, certs: Sequence[x509.Certificate]) -> x509.Certificate | None:
    sid = signer["sid"]
    if sid.name == "issuer_and_serial_number":
        issuer = sid.chosen["issuer"]
        serial = sid.chosen["serial_number"].native
        for c in certs:
            if c.serial_number == serial and c.issuer.dump() == issuer.dump():
                return c
    elif sid.name == "subject_key_identifier":
        ski = sid.chosen.native
        for c in certs:
            if c.key_identifier == ski:
                return c
    return None


def _algo_name(obj: Any) -> str:
    dotted = obj["algorithm"].dotted
    native = obj["algorithm"].native
    return str(native) if native != dotted else dotted


def _signed_attr(signer: cms.SignerInfo, name: str) -> Any:
    attrs = signer["signed_attrs"]
    if not isinstance(attrs, core.Void) and attrs is not None:
        for attr in attrs:
            if attr["type"].native == name:
                return attr["values"][0]
    return None


def _inspect_signer(
    signer: cms.SignerInfo,
    embedded: Sequence[x509.Certificate],
    roots: Sequence[x509.Certificate],
    content: bytes,
) -> SignerReport:
    cert = _find_signer_cert(signer, embedded)
    digest_oid = signer["digest_algorithm"]["algorithm"].dotted
    digest_native = signer["digest_algorithm"]["algorithm"].native
    digest_name = _algo_name(signer["digest_algorithm"])
    sig_alg_name = _algo_name(signer["signature_algorithm"])
    notes: list[str] = []
    hasher = gost.hash_function(digest_oid) or gost.hash_function(str(digest_native))

    signed_at = None
    sa = _signed_attr(signer, "signing_time")
    if sa is not None:
        signed_at = sa.native

    digest_match: bool | None = None
    to_verify = content
    signed_attrs = signer["signed_attrs"]
    if hasher is None:
        notes.append(f"digest algorithm {digest_name} is not supported")
        digest_match = None
    elif signed_attrs is not None and not isinstance(signed_attrs, core.Void) and len(signed_attrs) > 0:
        md = _signed_attr(signer, "message_digest")
        digest_match = md is not None and bytes(md.native) == hasher(content)
        # The signature covers the DER of the attributes re-tagged as SET OF.
        to_verify = b"\x31" + signed_attrs.dump()[1:]

    if cert is None:
        return SignerReport(
            subject="",
            subject_fields={},
            issuer="",
            serial="",
            not_before=datetime.min.replace(tzinfo=timezone.utc),
            not_after=datetime.min.replace(tzinfo=timezone.utc),
            fingerprint_sha256="",
            signed_at=signed_at,
            digest_algorithm=digest_name,
            signature_algorithm=sig_alg_name,
            digest_match=digest_match,
            signature_valid=None,
            signature_note="signer certificate is not embedded in the signature",
            cert_valid_at_signing=None,
            chain="incomplete",
            verdict="invalid" if digest_match is False else "unverified",
            notes=notes,
        )

    subject_fields = _name_fields(cert.subject)
    issuer_fields = _name_fields(cert.issuer)
    validity = cert["tbs_certificate"]["validity"]
    not_before = validity["not_before"].native
    not_after = validity["not_after"].native
    reference = signed_at or datetime.now(timezone.utc)
    cert_valid = not_before <= reference <= not_after

    sig_valid, sig_note = _verify_raw(
        _spki_der(cert),
        signer["signature_algorithm"],
        digest_oid if hasher is not None else None,
        to_verify,
        signer["signature"].native,
    )
    chain, chain_root = _chain_status(cert, embedded, roots)

    if digest_match is False or sig_valid is False:
        verdict: Verdict = "invalid"
    elif sig_valid is True and digest_match is not False and hasher is not None:
        verdict = "valid"
    else:
        verdict = "unverified"

    return SignerReport(
        subject=_display_name(subject_fields),
        subject_fields=subject_fields,
        issuer=_display_name(issuer_fields),
        serial=format(cert.serial_number, "x"),
        not_before=not_before,
        not_after=not_after,
        fingerprint_sha256=hashlib.sha256(cert.dump()).hexdigest(),
        signed_at=signed_at,
        digest_algorithm=digest_name,
        signature_algorithm=sig_alg_name,
        digest_match=digest_match,
        signature_valid=sig_valid,
        signature_note=sig_note,
        cert_valid_at_signing=cert_valid,
        chain=chain,
        verdict=verdict,
        notes=notes,
        chain_root_subject=subject_display(chain_root) if chain_root is not None else "",
        chain_root_fingerprint=hashlib.sha256(chain_root.dump()).hexdigest() if chain_root is not None else "",
    )


def _spki_der(cert: x509.Certificate) -> bytes:
    return bytes(cert["tbs_certificate"]["subject_public_key_info"].dump())


def _verify_raw(
    spki_der: bytes,
    sig_algorithm: Any,
    digest_oid: str | None,
    data: bytes,
    signature: bytes,
) -> tuple[bool | None, str]:
    """Verify `signature` over `data`. Returns (True/False, "") or (None, reason)."""
    sig_oid = sig_algorithm["algorithm"].dotted
    try:
        spki = core.Sequence.load(spki_der)
        key_alg = core.Sequence.load(spki[0].dump())
        key_oid = key_alg[0].dotted
    except Exception as exc:
        return None, f"cannot read public key: {exc}"

    if key_oid in gost.GOST_LEGACY_OIDS or sig_oid in gost.GOST_LEGACY_OIDS:
        return None, "GOST R 34.10-2001 / R 34.11-94 signatures are not supported"

    if key_oid in (gost.OID_GOST3410_2012_256, gost.OID_GOST3410_2012_512):
        return _verify_gost(spki, key_alg, key_oid, sig_oid, digest_oid, data, signature)

    return _verify_classic(spki_der, sig_algorithm, digest_oid, data, signature)


def _verify_gost(
    spki: core.Sequence,
    key_alg: core.Sequence,
    key_oid: str,
    sig_oid: str,
    digest_oid: str | None,
    data: bytes,
    signature: bytes,
) -> tuple[bool | None, str]:
    bits = 256 if key_oid == gost.OID_GOST3410_2012_256 else 512
    hash_oid = {
        gost.OID_SIGN_2012_256: gost.OID_STREEBOG_256,
        gost.OID_SIGN_2012_512: gost.OID_STREEBOG_512,
    }.get(sig_oid, digest_oid)
    hasher = gost.hash_function(hash_oid) if hash_oid else None
    if hasher is None:
        return None, "GOST digest algorithm is not supported"
    try:
        params = core.Sequence.load(key_alg[1].dump())
        curve_oid = params[0].dotted
        octets = core.OctetString.load(spki[1].contents[1:]).native
        return gost.verify_gost3410(bits, curve_oid, octets, hasher(data), signature), ""
    except gost.GostError as exc:
        return None, str(exc)
    except Exception as exc:
        return None, f"cannot verify GOST signature: {exc}"


def _verify_classic(
    spki_der: bytes,
    sig_algorithm: Any,
    digest_oid: str | None,
    data: bytes,
    signature: bytes,
) -> tuple[bool | None, str]:
    from cryptography.exceptions import InvalidSignature  # noqa: PLC0415
    from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa  # noqa: PLC0415
    from cryptography.hazmat.primitives.serialization import load_der_public_key  # noqa: PLC0415

    algo_name = sig_algorithm["algorithm"].native
    try:
        key = load_der_public_key(spki_der)
        hash_cls = _hash_class(sig_algorithm, digest_oid)
        if hash_cls is None:
            return None, "hash algorithm is not supported"
        if isinstance(key, rsa.RSAPublicKey):
            if algo_name == "rsassa_pss":
                params = sig_algorithm["parameters"].native
                salt = params["salt_length"] if params else hash_cls.digest_size
                key.verify(signature, data, padding.PSS(padding.MGF1(hash_cls()), salt), hash_cls())
            else:
                key.verify(signature, data, padding.PKCS1v15(), hash_cls())
        elif isinstance(key, ec.EllipticCurvePublicKey):
            key.verify(signature, data, ec.ECDSA(hash_cls()))
        else:
            return None, f"public key type {type(key).__name__} is not supported"
    except InvalidSignature:
        return False, ""
    except Exception as exc:
        return None, f"cannot verify signature: {exc}"
    return True, ""


def _hash_class(sig_algorithm: Any, digest_oid: str | None) -> Any:
    from cryptography.hazmat.primitives import hashes  # noqa: PLC0415

    try:
        hash_name = sig_algorithm.hash_algo
    except ValueError:
        hash_name = None
    if hash_name is None and digest_oid is not None:
        hash_name = _SHA_BY_OID.get(digest_oid)
    return {
        "sha1": hashes.SHA1,
        "sha224": hashes.SHA224,
        "sha256": hashes.SHA256,
        "sha384": hashes.SHA384,
        "sha512": hashes.SHA512,
    }.get(str(hash_name))


_SHA_BY_OID = {
    "1.3.14.3.2.26": "sha1",
    "2.16.840.1.101.3.4.2.4": "sha224",
    "2.16.840.1.101.3.4.2.1": "sha256",
    "2.16.840.1.101.3.4.2.2": "sha384",
    "2.16.840.1.101.3.4.2.3": "sha512",
}


def _cert_signature_ok(cert: x509.Certificate, issuer: x509.Certificate) -> bool | None:
    sig_alg = cert["signature_algorithm"]
    oid = sig_alg["algorithm"].dotted
    digest_oid = {
        gost.OID_SIGN_2012_256: gost.OID_STREEBOG_256,
        gost.OID_SIGN_2012_512: gost.OID_STREEBOG_512,
    }.get(oid)
    ok, _ = _verify_raw(
        _spki_der(issuer),
        sig_alg,
        digest_oid,
        cert["tbs_certificate"].dump(),
        cert["signature_value"].native,
    )
    return ok


def _chain_status(
    cert: x509.Certificate,
    embedded: Sequence[x509.Certificate],
    roots: Sequence[x509.Certificate],
) -> tuple[ChainStatus, x509.Certificate | None]:
    """(status, the untrusted self-signed root the chain ends in, if that is the case)."""
    root_fps = {hashlib.sha256(r.dump()).hexdigest() for r in roots}
    pool = [*embedded, *roots]
    current = cert
    for _ in range(_MAX_CHAIN):
        fp = hashlib.sha256(current.dump()).hexdigest()
        if current.subject.dump() == current.issuer.dump():
            if _cert_signature_ok(current, current) is False:
                return "broken", None
            return ("trusted", None) if fp in root_fps else ("untrusted_root", current)
        if fp in root_fps:
            return "trusted", None
        issuer = next((c for c in pool if c.subject.dump() == current.issuer.dump() and c is not current), None)
        if issuer is None:
            return "incomplete", None
        if _cert_signature_ok(current, issuer) is False:
            return "broken", None
        current = issuer
    return "incomplete", None


def issuer_urls(cert: x509.Certificate) -> list[str]:
    """`caIssuers` URLs of a certificate's Authority Information Access extension."""
    urls: list[str] = []
    for ext in cert["tbs_certificate"]["extensions"] or []:
        if ext["extn_id"].native == "authority_information_access":
            urls.extend(
                str(desc["access_location"].native)
                for desc in ext["extn_value"].parsed
                if desc["access_method"].native == "ca_issuers"
            )
    return urls


def embedded_certificates(sig_bytes: bytes) -> list[x509.Certificate]:
    try:
        signed = cms.ContentInfo.load(_to_der(sig_bytes))["content"]
        return [c.chosen for c in (signed["certificates"] or []) if c.name == "certificate"]
    except Exception as exc:
        raise CmsParseError(f"cannot parse CMS: {exc}") from exc
