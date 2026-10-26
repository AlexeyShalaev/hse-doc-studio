from __future__ import annotations

import pytest
from hse_doc_studio.core.enums import DetachedFormat, DetachedVerdict
from hse_doc_studio.core.signatures import errors
from hse_doc_studio.core.signatures.verification import VerifiedSignature, note_plate_mismatch
from hse_doc_studio.core.value_objects import SignatureSlot, SignaturesState, SignerInfo
from hse_doc_studio.infra.signatures import cms_inspector, detached_verifier, openpgp


@pytest.mark.parametrize(
    ("module", "name"),
    [
        (openpgp, "GpgError"),
        (openpgp, "GpgUnavailableError"),
        (cms_inspector, "CmsParseError"),
        (detached_verifier, "UnknownSignatureFormatError"),
        (detached_verifier, "GpgUnavailableError"),
        (detached_verifier, "VerifiedSignature"),
    ],
)
def test__errors__reexport_same_class_objects(module: object, name: str) -> None:
    source = (
        errors if hasattr(errors, name) else __import__("hse_doc_studio.core.signatures.verification", fromlist=[name])
    )

    assert getattr(module, name) is getattr(source, name)


def _verified(signer_id: str = "AAA") -> VerifiedSignature:
    return VerifiedSignature(
        format=DetachedFormat.cms,
        verdict=DetachedVerdict.valid,
        signer="Иванов Иван",
        signer_id=signer_id,
        notes=("no_revocation_check",),
    )


def _state(expected_id: str) -> SignaturesState:
    slot = SignatureSlot(None, None, None, signer=SignerInfo("x509", "Иванов Иван", signer_id=expected_id))
    return SignaturesState(slots={"sup": slot}, placements={})


def test__note_plate_mismatch__returns_new_value_and_does_not_mutate() -> None:
    original = _verified("AAA")

    result = note_plate_mismatch(_state("BBB"), "sup", original)

    assert result is not original
    assert result.notes == ("no_revocation_check", "plate_signer_mismatch")
    assert original.notes == ("no_revocation_check",)


def test__note_plate_mismatch__same_signer_or_no_expectation__returns_same_value() -> None:
    original = _verified("AAA")

    assert note_plate_mismatch(_state("AAA"), "sup", original) is original
    assert note_plate_mismatch(_state(""), "sup", original) is original
    assert note_plate_mismatch(SignaturesState(slots={}, placements={}), "sup", original) is original
