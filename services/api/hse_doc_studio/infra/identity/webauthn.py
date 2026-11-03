"""WebAuthn на py_webauthn: параметры церемоний и проверка ответов браузера.

Политика зашита здесь, а не приходит от клиента: attestation `none`, обнаруживаемый ключ (resident key) обязателен,
проверка пользователя (UV, биометрия или PIN) обязательна и проверяется сервером, а не только просится у браузера.
"""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Sequence

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import options_to_json_dict
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.parse_authentication_credential_json import parse_authentication_credential_json
from webauthn.helpers.parse_registration_credential_json import parse_registration_credential_json
from webauthn.helpers.structs import (
    AttestationConveyancePreference,
    AuthenticatorSelectionCriteria,
    AuthenticatorTransport,
    CredentialDeviceType,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from hse_doc_studio.core.identity.passkeys import (
    CEREMONY_TIMEOUT_MS,
    AssertionHeader,
    CredentialJson,
    NewCredential,
    Passkey,
    PasskeyDescriptor,
    PasskeyFailure,
    PasskeyVerificationError,
    RelyingParty,
    VerifiedAssertion,
)

_TRANSPORTS = {t.value: t for t in AuthenticatorTransport}


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _descriptors(items: Sequence[PasskeyDescriptor]) -> list[PublicKeyCredentialDescriptor]:
    return [
        PublicKeyCredentialDescriptor(
            id=_b64url_decode(item.credential_id),
            transports=[_TRANSPORTS[t] for t in item.transports if t in _TRANSPORTS] or None,
        )
        for item in items
    ]


def _client_challenge(client_data_b64: object) -> str:
    """Вызов из clientDataJSON как есть (base64url), без проверки подписи: по нему ищется одноразовый вызов."""
    if not isinstance(client_data_b64, str):
        raise PasskeyVerificationError(PasskeyFailure.malformed, "no clientDataJSON")
    try:
        data = json.loads(_b64url_decode(client_data_b64))
    except (ValueError, binascii.Error) as exc:
        raise PasskeyVerificationError(PasskeyFailure.malformed, "clientDataJSON") from exc
    challenge = data.get("challenge") if isinstance(data, dict) else None
    if not isinstance(challenge, str) or not challenge:
        raise PasskeyVerificationError(PasskeyFailure.malformed, "no challenge")
    return challenge


def _response(credential: CredentialJson) -> dict[str, object]:
    response = credential.get("response")
    if not isinstance(response, dict):
        raise PasskeyVerificationError(PasskeyFailure.malformed, "no response")
    return response


def _authentication_failure(exc: WebAuthnException) -> PasskeyVerificationError:
    text = str(exc).lower()
    if "sign count" in text:
        return PasskeyVerificationError(PasskeyFailure.sign_count, str(exc))
    if "verification is required" in text or "user verification" in text:
        return PasskeyVerificationError(PasskeyFailure.user_verification, str(exc))
    if "challenge" in text:
        return PasskeyVerificationError(PasskeyFailure.challenge, str(exc))
    return PasskeyVerificationError(PasskeyFailure.signature, str(exc))


class PyWebAuthn:
    """Реализация `IWebAuthn` на py_webauthn (версия закреплена в pyproject)."""

    def registration_options(
        self,
        party: RelyingParty,
        *,
        challenge: bytes,
        user_handle: bytes,
        user_name: str,
        display_name: str,
        exclude: Sequence[PasskeyDescriptor],
    ) -> dict[str, object]:
        options = generate_registration_options(
            rp_id=party.id,
            rp_name=party.name,
            user_id=user_handle,
            user_name=user_name,
            user_display_name=display_name,
            challenge=challenge,
            timeout=CEREMONY_TIMEOUT_MS,
            attestation=AttestationConveyancePreference.NONE,
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.REQUIRED,
                user_verification=UserVerificationRequirement.REQUIRED,
            ),
            exclude_credentials=_descriptors(exclude),
        )
        return dict(options_to_json_dict(options))

    def authentication_options(
        self, party: RelyingParty, *, challenge: bytes, allow: Sequence[PasskeyDescriptor]
    ) -> dict[str, object]:
        options = generate_authentication_options(
            rp_id=party.id,
            challenge=challenge,
            timeout=CEREMONY_TIMEOUT_MS,
            allow_credentials=_descriptors(allow),
            user_verification=UserVerificationRequirement.REQUIRED,
        )
        return dict(options_to_json_dict(options))

    def registration_challenge(self, credential: CredentialJson) -> str:
        return _client_challenge(_response(credential).get("clientDataJSON"))

    def assertion_header(self, credential: CredentialJson) -> AssertionHeader:
        response = _response(credential)
        raw_id = credential.get("rawId") or credential.get("id")
        if not isinstance(raw_id, str) or not raw_id:
            raise PasskeyVerificationError(PasskeyFailure.malformed, "no credential id")
        handle = response.get("userHandle")
        try:
            user_handle = _b64url_decode(handle) if isinstance(handle, str) and handle else None
            # Ключ ищется по каноническому base64url: клиент мог прислать с дополнением или без.
            credential_id = _b64url(_b64url_decode(raw_id))
        except (ValueError, binascii.Error) as exc:
            raise PasskeyVerificationError(PasskeyFailure.malformed, "credential id") from exc
        return AssertionHeader(
            credential_id=credential_id,
            challenge=_client_challenge(response.get("clientDataJSON")),
            user_handle=user_handle,
        )

    def verify_registration(self, party: RelyingParty, credential: CredentialJson, *, challenge: str) -> NewCredential:
        try:
            parsed = parse_registration_credential_json(dict(credential))
            verified = verify_registration_response(
                credential=parsed,
                expected_challenge=_b64url_decode(challenge),
                expected_rp_id=party.id,
                expected_origin=party.origin,
                require_user_verification=True,
            )
        except WebAuthnException as exc:
            raise PasskeyVerificationError(PasskeyFailure.signature, str(exc)) from exc
        except (ValueError, binascii.Error) as exc:
            raise PasskeyVerificationError(PasskeyFailure.malformed, str(exc)) from exc
        transports = tuple(t.value for t in parsed.response.transports or ())
        return NewCredential(
            credential_id=_b64url(verified.credential_id),
            public_key=verified.credential_public_key,
            sign_count=verified.sign_count,
            aaguid=verified.aaguid,
            transports=transports,
            backup_eligible=verified.credential_device_type is CredentialDeviceType.MULTI_DEVICE,
            backed_up=verified.credential_backed_up,
        )

    def verify_authentication(
        self, party: RelyingParty, credential: CredentialJson, *, challenge: str, passkey: Passkey
    ) -> VerifiedAssertion:
        try:
            parsed = parse_authentication_credential_json(dict(credential))
            verified = verify_authentication_response(
                credential=parsed,
                expected_challenge=_b64url_decode(challenge),
                expected_rp_id=party.id,
                expected_origin=party.origin,
                credential_public_key=passkey.public_key,
                credential_current_sign_count=passkey.sign_count,
                require_user_verification=True,
            )
        except WebAuthnException as exc:
            raise _authentication_failure(exc) from exc
        except (ValueError, binascii.Error) as exc:
            raise PasskeyVerificationError(PasskeyFailure.malformed, str(exc)) from exc
        return VerifiedAssertion(new_sign_count=verified.new_sign_count, backed_up=verified.credential_backed_up)
