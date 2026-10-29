from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from hse_doc_studio.core.office_tokens import (
    OfficeTokenClaims,
    OfficeTokenError,
    OfficeTokenPurpose,
    OfficeTokenSigner,
    new_nonce,
)

_NOW = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)
_KEY = b"k" * 32


def _claims(purpose: OfficeTokenPurpose = OfficeTokenPurpose.callback, ttl_s: int = 600) -> OfficeTokenClaims:
    return OfficeTokenClaims(
        purpose, "p-1", "pres", "pres/a.pptx", "u-1", "editor", new_nonce(), _NOW + timedelta(seconds=ttl_s)
    )


@pytest.mark.unit
def test__office_token__roundtrip__keeps_claims() -> None:
    signer = OfficeTokenSigner([_KEY])
    claims = _claims()

    got = signer.verify(signer.sign(claims), _NOW, purpose=OfficeTokenPurpose.callback, project_id="p-1", doc_id="pres")

    assert got == claims


@pytest.mark.unit
def test__office_token__other_purpose__rejected() -> None:
    signer = OfficeTokenSigner([_KEY])
    token = signer.sign(_claims(OfficeTokenPurpose.document))

    with pytest.raises(OfficeTokenError):
        signer.verify(token, _NOW, purpose=OfficeTokenPurpose.callback)


@pytest.mark.unit
@pytest.mark.parametrize(("project_id", "doc_id"), [("p-2", "pres"), ("p-1", "other")])
def test__office_token__other_target__rejected(project_id: str, doc_id: str) -> None:
    signer = OfficeTokenSigner([_KEY])
    token = signer.sign(_claims())

    with pytest.raises(OfficeTokenError):
        signer.verify(token, _NOW, purpose=OfficeTokenPurpose.callback, project_id=project_id, doc_id=doc_id)


@pytest.mark.unit
def test__office_token__expired__rejected() -> None:
    signer = OfficeTokenSigner([_KEY])
    token = signer.sign(_claims(ttl_s=10))

    with pytest.raises(OfficeTokenError):
        signer.verify(token, _NOW + timedelta(seconds=10), purpose=OfficeTokenPurpose.callback)


@pytest.mark.unit
def test__office_token__tampered_payload_or_foreign_key__rejected() -> None:
    signer = OfficeTokenSigner([_KEY])
    token = signer.sign(_claims())
    head, payload, sig = token.split(".")

    with pytest.raises(OfficeTokenError):
        signer.verify(f"{head}.{payload[:-2]}AA.{sig}", _NOW, purpose=OfficeTokenPurpose.callback)
    with pytest.raises(OfficeTokenError):
        OfficeTokenSigner([b"x" * 32]).verify(token, _NOW, purpose=OfficeTokenPurpose.callback)
    with pytest.raises(OfficeTokenError):
        signer.verify("garbage", _NOW, purpose=OfficeTokenPurpose.callback)


@pytest.mark.unit
def test__office_token__rotated_key__old_token_still_verifies() -> None:
    old = OfficeTokenSigner([_KEY])
    rotated = OfficeTokenSigner([b"n" * 32, _KEY])

    rotated.verify(old.sign(_claims()), _NOW, purpose=OfficeTokenPurpose.callback)


@pytest.mark.unit
def test__new_nonce__is_unique() -> None:
    assert len({new_nonce() for _ in range(50)}) == 50
