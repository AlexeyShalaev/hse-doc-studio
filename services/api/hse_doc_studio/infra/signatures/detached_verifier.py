"""Format detection and verification of an externally produced detached signature.

Turns the raw output of the OpenPGP and CMS inspectors into one
`VerifiedSignature` the use cases store. Notes are stable codes, not prose: the
web app translates them.

Note codes:
  key_expired, key_revoked, signature_expired   OpenPGP key / signature state
  multiple_signers                              CMS carries more than one signer
  cert_not_valid_at_signing                     certificate window misses the signing time
  chain_untrusted_root / chain_incomplete / chain_broken
  no_revocation_check                           CMS: CRL / OCSP are never consulted
  unsupported:<reason>                          signer shown, but not checkable here
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import structlog

from hse_doc_studio.core.enums import DetachedFormat, DetachedVerdict
from hse_doc_studio.infra.signatures.cms_inspector import (
    CmsParseError,
    SignerReport,
    inspect_cms,
    looks_like_cms,
)
from hse_doc_studio.infra.signatures.openpgp import (
    GpgKeyring,
    GpgUnavailableError,
    GpgVerification,
    looks_like_openpgp_signature,
)

logger = structlog.get_logger()

_ROOT_SUFFIXES = {".cer", ".crt", ".pem", ".der"}


class UnknownSignatureFormatError(ValueError):
    """The file is neither an OpenPGP nor a CMS signature."""


@dataclass(frozen=True)
class VerifiedSignature:
    format: DetachedFormat
    verdict: DetachedVerdict
    signer: str
    signer_id: str
    issuer: str = ""
    algorithm: str = ""
    signed_at: str | None = None
    not_before: str | None = None
    not_after: str | None = None
    chain: str | None = None
    # Extension of the stored signature file: ".asc", ".sig" or ".p7s".
    extension: str = ".sig"
    # OpenPGP, unknown signer: key id the user has to supply a public key for.
    missing_key_id: str | None = None
    notes: list[str] = field(default_factory=list)


_PGP_STATUS: dict[str, tuple[DetachedVerdict, str | None]] = {
    "good": (DetachedVerdict.valid, None),
    "bad": (DetachedVerdict.invalid, None),
    "revoked_key": (DetachedVerdict.invalid, "key_revoked"),
    "expired_key": (DetachedVerdict.valid, "key_expired"),
    "expired_signature": (DetachedVerdict.valid, "signature_expired"),
}


def detect_format(blob: bytes) -> DetachedFormat | None:
    if looks_like_openpgp_signature(blob):
        return DetachedFormat.openpgp
    if looks_like_cms(blob):
        return DetachedFormat.cms
    return None


class DetachedSignatureVerifier:
    def __init__(self, keyring: GpgKeyring, trusted_roots_dir: Path) -> None:
        self._keyring = keyring
        self._roots_dir = trusted_roots_dir

    def trusted_roots(self) -> list[bytes]:
        if not self._roots_dir.is_dir():
            return []
        return [p.read_bytes() for p in sorted(self._roots_dir.iterdir()) if p.suffix.lower() in _ROOT_SUFFIXES]

    def verify(self, pdf_path: Path, sig_bytes: bytes) -> VerifiedSignature:
        fmt = detect_format(sig_bytes)
        if fmt is DetachedFormat.openpgp:
            return self._verify_openpgp(pdf_path, sig_bytes)
        if fmt is DetachedFormat.cms:
            return self._verify_cms(pdf_path, sig_bytes)
        raise UnknownSignatureFormatError("not an OpenPGP or CMS signature")

    # ── OpenPGP ──────────────────────────────────────────────────────────────

    def _verify_openpgp(self, pdf_path: Path, sig_bytes: bytes) -> VerifiedSignature:
        armored = sig_bytes.lstrip().startswith(b"-----BEGIN")
        ext = ".asc" if armored else ".sig"
        with tempfile.TemporaryDirectory() as tmp:
            sig_file = Path(tmp) / f"sig{ext}"
            sig_file.write_bytes(sig_bytes)
            result = self._keyring.verify_detached(sig_file, pdf_path)
        return self._map_openpgp(result, ext)

    def _map_openpgp(self, r: GpgVerification, ext: str) -> VerifiedSignature:
        if r.status == "no_pubkey":
            return VerifiedSignature(
                format=DetachedFormat.openpgp,
                verdict=DetachedVerdict.unknown_key,
                signer="",
                signer_id=r.key_id or "",
                algorithm="OpenPGP",
                extension=ext,
                missing_key_id=r.key_id,
            )
        if r.status == "error":
            raise UnknownSignatureFormatError(r.note or "gpg could not read the signature")
        verdict, note = _PGP_STATUS[r.status]
        notes = [note] if note else []
        fpr = r.primary_fingerprint or r.fingerprint or ""
        not_after = None
        if fpr:
            key = self._keyring.get_key(fpr)
            if key is not None and key.expires is not None:
                not_after = key.expires.isoformat()
        return VerifiedSignature(
            format=DetachedFormat.openpgp,
            verdict=verdict,
            signer=r.signer,
            signer_id=fpr or (r.key_id or ""),
            algorithm="OpenPGP",
            signed_at=r.signed_at.isoformat() if r.signed_at else None,
            not_after=not_after,
            extension=ext,
            notes=notes,
        )

    # ── CMS / CAdES ──────────────────────────────────────────────────────────

    def _verify_cms(self, pdf_path: Path, sig_bytes: bytes) -> VerifiedSignature:
        try:
            reports = inspect_cms(sig_bytes, pdf_path.read_bytes(), self.trusted_roots())
        except CmsParseError as exc:
            raise UnknownSignatureFormatError(str(exc)) from exc
        return _map_cms(reports)


def _map_cms(reports: list[SignerReport]) -> VerifiedSignature:
    first = reports[0]
    notes: list[str] = []
    if len(reports) > 1:
        notes.append("multiple_signers")
    if first.cert_valid_at_signing is False:
        notes.append("cert_not_valid_at_signing")
    if first.chain != "trusted":
        notes.append(f"chain_{first.chain}")
    notes.append("no_revocation_check")
    if first.signature_valid is None:
        notes.append(f"unsupported:{first.signature_note}")
    notes.extend(first.notes)

    verdict = {
        "valid": DetachedVerdict.valid,
        "invalid": DetachedVerdict.invalid,
        "unverified": DetachedVerdict.unverified,
    }[first.verdict]
    # Any signer failing fails the whole file.
    if any(r.verdict == "invalid" for r in reports):
        verdict = DetachedVerdict.invalid
    return VerifiedSignature(
        format=DetachedFormat.cms,
        verdict=verdict,
        signer=first.subject,
        signer_id=first.fingerprint_sha256,
        issuer=first.issuer,
        algorithm=f"{first.signature_algorithm} / {first.digest_algorithm}",
        signed_at=first.signed_at.isoformat() if first.signed_at else None,
        not_before=first.not_before.isoformat() if first.fingerprint_sha256 else None,
        not_after=first.not_after.isoformat() if first.fingerprint_sha256 else None,
        chain=first.chain,
        extension=".p7s",
        notes=notes,
    )


__all__ = [
    "DetachedSignatureVerifier",
    "GpgUnavailableError",
    "UnknownSignatureFormatError",
    "VerifiedSignature",
    "detect_format",
]
