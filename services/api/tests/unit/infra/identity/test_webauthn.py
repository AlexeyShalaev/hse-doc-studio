"""Адаптер py_webauthn на тестовых векторах: снятые ответы, ответы настоящих браузеров и их порча."""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.core.identity.passkeys import (
    Passkey,
    PasskeyDescriptor,
    PasskeyFailure,
    PasskeyVerificationError,
    RelyingParty,
)
from hse_doc_studio.infra.identity.webauthn import PyWebAuthn

from tests.fakes.authenticator import b64url, b64url_decode

_VECTORS: dict[str, Any] = json.loads((Path(__file__).parent / "webauthn_vectors.json").read_text(encoding="utf-8"))
RP = RelyingParty(id=_VECTORS["rp_id"], name="HSE Doc Studio", origin=_VECTORS["origin"])
T0 = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)


def _passkey(public_key: bytes, sign_count: int, credential_id: str = "x") -> Passkey:
    return Passkey(
        id="p1",
        user_id="u1",
        credential_id=credential_id,
        public_key=public_key,
        sign_count=sign_count,
        rp_id=RP.id,
        name="key",
        created_at=T0,
    )


def _registered() -> Passkey:
    expected = _VECTORS["registration"]["expected"]
    return _passkey(b64url_decode(expected["public_key"]), 0, expected["credential_id"])


@pytest.fixture
def webauthn() -> PyWebAuthn:
    return PyWebAuthn()


def test__verify_registration__vector__extracts_credential(webauthn: PyWebAuthn) -> None:
    vector = _VECTORS["registration"]

    created = webauthn.verify_registration(RP, vector["credential"], challenge=vector["challenge"])

    expected = vector["expected"]
    assert created.credential_id == expected["credential_id"]
    assert b64url(created.public_key) == expected["public_key"]
    assert created.sign_count == expected["sign_count"]
    assert created.aaguid == expected["aaguid"]
    assert list(created.transports) == expected["transports"]
    assert created.backup_eligible is False


def test__registration_challenge__read_from_client_data(webauthn: PyWebAuthn) -> None:
    vector = _VECTORS["registration"]

    assert webauthn.registration_challenge(vector["credential"]) == vector["challenge"]


@pytest.mark.parametrize(
    ("party", "challenge"),
    [
        (RP, b64url(bytes(32))),
        (RelyingParty(id="evil.example.org", name="x", origin="https://evil.example.org"), None),
        (RelyingParty(id=RP.id, name="x", origin="https://studio.example.org:8443"), None),
    ],
    ids=["other_challenge", "other_rp_id", "other_origin"],
)
def test__verify_registration__mismatch__rejected(
    webauthn: PyWebAuthn, party: RelyingParty, challenge: str | None
) -> None:
    vector = _VECTORS["registration"]

    with pytest.raises(PasskeyVerificationError) as exc:
        webauthn.verify_registration(party, vector["credential"], challenge=challenge or vector["challenge"])

    assert exc.value.reason is PasskeyFailure.signature


def test__verify_authentication__vector__new_counter(webauthn: PyWebAuthn) -> None:
    vector = _VECTORS["authentication"]

    verified = webauthn.verify_authentication(
        RP, vector["credential"], challenge=vector["challenge"], passkey=_registered()
    )

    assert verified.new_sign_count == vector["expected_sign_count"]
    assert verified.backed_up is False


def test__assertion_header__vector__credential_challenge_and_user(webauthn: PyWebAuthn) -> None:
    vector = _VECTORS["authentication"]

    header = webauthn.assertion_header(vector["credential"])

    assert header.credential_id == _registered().credential_id
    assert header.challenge == vector["challenge"]
    assert header.user_handle == b64url_decode(vector["user_handle"])


def test__verify_authentication__tampered_signature__rejected(webauthn: PyWebAuthn) -> None:
    vector = _VECTORS["authentication"]
    credential = copy.deepcopy(vector["credential"])
    signature = bytearray(b64url_decode(credential["response"]["signature"]))
    signature[-1] ^= 0x01
    credential["response"]["signature"] = b64url(bytes(signature))

    with pytest.raises(PasskeyVerificationError) as exc:
        webauthn.verify_authentication(RP, credential, challenge=vector["challenge"], passkey=_registered())

    assert exc.value.reason is PasskeyFailure.signature


def test__verify_authentication__stored_counter_ahead__clone_suspected(webauthn: PyWebAuthn) -> None:
    vector = _VECTORS["authentication"]
    passkey = _passkey(_registered().public_key, 5, _registered().credential_id)

    with pytest.raises(PasskeyVerificationError) as exc:
        webauthn.verify_authentication(RP, vector["credential"], challenge=vector["challenge"], passkey=passkey)

    assert exc.value.reason is PasskeyFailure.sign_count


def test__upstream_browser_vector__user_verified__accepted(webauthn: PyWebAuthn) -> None:
    vector = _VECTORS["upstream"]["rsa_with_uv"]
    party = RelyingParty(id=vector["rp_id"], name="x", origin=vector["origin"])

    verified = webauthn.verify_authentication(
        party,
        vector["credential"],
        challenge=vector["challenge"],
        passkey=_passkey(b64url_decode(vector["public_key"]), vector["sign_count"]),
    )

    assert verified.new_sign_count == 1


def test__upstream_browser_vector__without_user_verification__rejected(webauthn: PyWebAuthn) -> None:
    """Ключ без PIN и биометрии подписал вход: для входа без пароля этого мало."""
    vector = _VECTORS["upstream"]["ec2_without_uv"]
    party = RelyingParty(id=vector["rp_id"], name="x", origin=vector["origin"])

    with pytest.raises(PasskeyVerificationError) as exc:
        webauthn.verify_authentication(
            party,
            vector["credential"],
            challenge=vector["challenge"],
            passkey=_passkey(b64url_decode(vector["public_key"]), vector["sign_count"]),
        )

    assert exc.value.reason is PasskeyFailure.user_verification


@pytest.mark.parametrize(
    "credential",
    [
        {},
        {"response": "x"},
        {"rawId": "AQID", "response": {"clientDataJSON": "@@@"}},
        {"rawId": "AQID", "response": {}},
    ],
    ids=["empty", "response_not_object", "client_data_garbage", "no_client_data"],
)
def test__assertion_header__malformed__rejected(webauthn: PyWebAuthn, credential: dict[str, object]) -> None:
    with pytest.raises(PasskeyVerificationError) as exc:
        webauthn.assertion_header(credential)

    assert exc.value.reason is PasskeyFailure.malformed


def test__options__descriptor_transports_filtered(webauthn: PyWebAuthn) -> None:
    options = webauthn.authentication_options(
        RP, challenge=bytes(32), allow=[PasskeyDescriptor("AQID", ("internal", "smoke-signal"))]
    )

    assert options["allowCredentials"] == [{"id": "AQID", "type": "public-key", "transports": ["internal"]}]
    assert options["timeout"] == 300_000
