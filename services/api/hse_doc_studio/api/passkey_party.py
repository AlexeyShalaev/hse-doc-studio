"""Проверяющая сторона WebAuthn для запроса: домен ключей и origin из `auth.public_url` или адреса запроса."""

from __future__ import annotations

from starlette.requests import HTTPConnection

from hse_doc_studio.api.auth_cookie import public_origin
from hse_doc_studio.api.config import settings
from hse_doc_studio.core.identity.passkeys import RelyingParty, RelyingPartyResolution, resolve_relying_party

RP_NAME = "HSE Doc Studio"


def relying_party_resolution(request: HTTPConnection) -> RelyingPartyResolution:
    """`public_url` главнее: за обратным прокси адрес запроса внутренний. Без него как адрес возврата OIDC."""
    origin = public_origin(settings.auth.public_url) or public_origin(str(request.base_url))
    return resolve_relying_party(origin, rp_id=settings.auth.passkey_rp_id, name=RP_NAME)


def relying_party(request: HTTPConnection) -> RelyingParty | None:
    return relying_party_resolution(request).party
