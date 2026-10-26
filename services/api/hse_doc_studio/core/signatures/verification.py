"""Результат проверки открепленной подписи.

Notes are stable codes, not prose: the web app translates them.

Note codes:
  key_expired, key_revoked, signature_expired   OpenPGP key / signature state
  multiple_signers                              CMS carries more than one signer
  cert_not_valid_at_signing                     certificate window misses the signing time
  chain_untrusted_root / chain_incomplete / chain_broken
  no_revocation_check                           CMS: CRL / OCSP are never consulted
  unsupported:<reason>                          signer shown, but not checkable here
  plate_signer_mismatch                         signed by somebody else than the plate says
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from hse_doc_studio.core.enums import DetachedFormat, DetachedVerdict
from hse_doc_studio.core.value_objects import SignaturesState


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
    root_subject: str = ""
    root_fingerprint: str = ""
    # Extension of the stored signature file: ".asc", ".sig" or ".p7s".
    extension: str = ".sig"
    # OpenPGP, unknown signer: key id the user has to supply a public key for.
    missing_key_id: str | None = None
    notes: tuple[str, ...] = ()


def note_plate_mismatch(state: SignaturesState, slot_id: str, verified: VerifiedSignature) -> VerifiedSignature:
    """Flag a signature made by somebody else than the signer printed on the plate."""
    slot = state.slots.get(slot_id)
    expected = slot.signer if slot else None
    if expected and expected.signer_id and verified.signer_id and expected.signer_id != verified.signer_id:
        return replace(verified, notes=(*verified.notes, "plate_signer_mismatch"))
    return verified
