from __future__ import annotations

import base64
import json

import pytest
from hse_doc_studio.infra.office.jwt import sign, verify

_SECRET = "test-secret"  # noqa: S105 — тестовый секрет


@pytest.mark.unit
def test__jwt__roundtrip() -> None:
    payload = {"document": {"key": "abc-1", "fileType": "pptx"}, "status": 2, "кириллица": "да"}

    token = sign(payload, _SECRET)

    assert token.count(".") == 2
    assert verify(token, _SECRET) == payload


@pytest.mark.unit
def test__jwt__tampered_payload_rejected() -> None:
    token = sign({"status": 2}, _SECRET)
    header_seg, _payload_seg, signature_seg = token.split(".")
    forged_payload = base64.urlsafe_b64encode(json.dumps({"status": 6}).encode()).rstrip(b"=").decode()

    with pytest.raises(ValueError, match="signature mismatch"):
        verify(f"{header_seg}.{forged_payload}.{signature_seg}", _SECRET)


@pytest.mark.unit
def test__jwt__wrong_secret_rejected() -> None:
    token = sign({"status": 2}, _SECRET)

    with pytest.raises(ValueError, match="signature mismatch"):
        verify(token, "other-secret")


@pytest.mark.unit
def test__jwt__malformed_token_rejected() -> None:
    with pytest.raises(ValueError, match="3 segments"):
        verify("not-a-jwt", _SECRET)


@pytest.mark.unit
def test__jwt__alg_none_rejected() -> None:
    # Классическая атака alg=none: заголовок подменён, подпись пустая.
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(json.dumps({"status": 2}).encode()).rstrip(b"=").decode()

    with pytest.raises(ValueError, match="algorithm"):
        verify(f"{header}.{payload}.", _SECRET)
