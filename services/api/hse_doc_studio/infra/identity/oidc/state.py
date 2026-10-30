"""Состояние входа в подписанной cookie: HMAC-SHA256 над JSON, ключи производные от связки секретов."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime

from hse_doc_studio.core.identity.oidc import OidcLoginState

OIDC_STATE_KEY_PURPOSE = "oidc-state"


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class HmacOidcStateCodec:
    """Подписывает первым ключом, проверяет любым: смена ключа не рвёт входы, начатые до неё."""

    def __init__(self, keys: list[bytes]) -> None:
        if not keys:
            msg = "для подписи состояния OIDC нужен хотя бы один ключ"
            raise ValueError(msg)
        self._keys = keys

    def seal(self, state: OidcLoginState) -> str:
        payload = json.dumps(
            {
                "p": state.provider_id,
                "s": state.state,
                "n": state.nonce,
                "v": state.code_verifier,
                "r": state.redirect_uri,
                "x": state.next_path,
                "e": int(state.expires_at.timestamp()),
                "l": state.link_user_id,
            },
            separators=(",", ":"),
        ).encode()
        body = _b64(payload)
        return f"{body}.{_b64(self._sign(self._keys[0], body))}"

    def open(self, sealed: str) -> OidcLoginState | None:
        body, _, signature = sealed.partition(".")
        if not body or not signature:
            return None
        try:
            given = _unb64(signature)
            if not any(hmac.compare_digest(given, self._sign(key, body)) for key in self._keys):
                return None
            data = json.loads(_unb64(body))
            return OidcLoginState(
                provider_id=str(data["p"]),
                state=str(data["s"]),
                nonce=str(data["n"]),
                code_verifier=str(data["v"]),
                redirect_uri=str(data["r"]),
                next_path=str(data["x"]),
                expires_at=datetime.fromtimestamp(int(data["e"]), UTC),
                link_user_id=str(data["l"]) if data.get("l") else None,
            )
        except (ValueError, KeyError, TypeError):
            return None

    @staticmethod
    def _sign(key: bytes, body: str) -> bytes:
        return hmac.new(key, body.encode("ascii"), hashlib.sha256).digest()
