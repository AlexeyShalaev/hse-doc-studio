"""Контракт входа по passkey: параметры церемоний, ответы браузера, ключи в профиле и в админке.

Параметры (`options`) и ответ браузера (`credential`) идут в формате JSON WebAuthn Level 3
(`PublicKeyCredentialCreationOptionsJSON`, `RegistrationResponseJSON` и т. д.): их разбирает библиотека WebAuthn
на сервере и `@simplewebauthn/browser` на клиенте, поэтому здесь они непрозрачны и ограничены только размером.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from pydantic import Field, field_validator, model_validator

from hse_doc_studio.api.schemas.common import StrictModel
from hse_doc_studio.api.schemas.session import PASSWORD_MAX
from hse_doc_studio.core.identity.passkeys import CREDENTIAL_JSON_MAX, PASSKEY_NAME_MAX


def _bounded(value: dict[str, Any]) -> dict[str, Any]:
    if len(json.dumps(value, ensure_ascii=False)) > CREDENTIAL_JSON_MAX:
        msg = "credential is too large"
        raise ValueError(msg)
    return value


class PasskeyOptions(StrictModel):
    """Параметры для `navigator.credentials.create()` или `.get()` (JSON WebAuthn)."""

    options: dict[str, Any]


class PasskeyLoginRequest(StrictModel):
    credential: dict[str, Any]

    @field_validator("credential")
    @classmethod
    def _credential_size(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _bounded(value)


class AccountPasskey(StrictModel):
    id: str
    name: str
    created_at: datetime
    last_used_at: datetime | None
    # Ключ синхронизируется между устройствами (менеджер паролей, связка ключей).
    synced: bool
    # Домен (RP ID), к которому ключ привязан.
    domain: str
    # Ключ подходит к текущему адресу Студии; после смены адреса старые ключи перестают работать.
    domain_matches: bool


class AccountPasskeyList(StrictModel):
    items: list[AccountPasskey]
    # Вход по passkey доступен на этом сервере и по этому адресу.
    enabled: bool
    # Домен новых ключей; null, если адрес Студии для WebAuthn не годится.
    domain: str | None
    # Личность можно подтвердить паролем (иначе passkey или новым входом через провайдера).
    has_password: bool
    limit: int


class CreatePasskeyRequest(StrictModel):
    # Пусто: имя по устройству (браузер и система из User-Agent).
    name: str | None = Field(default=None, max_length=PASSKEY_NAME_MAX)
    credential: dict[str, Any]

    @field_validator("credential")
    @classmethod
    def _credential_size(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _bounded(value)


class RenamePasskeyRequest(StrictModel):
    name: str = Field(min_length=1, max_length=PASSKEY_NAME_MAX)


class ReauthRequest(StrictModel):
    """Ровно одно: пароль или ответ passkey на вызов из `POST /account/reauth/options`."""

    password: str | None = Field(default=None, max_length=PASSWORD_MAX)
    credential: dict[str, Any] | None = None

    @field_validator("credential")
    @classmethod
    def _credential_size(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return _bounded(value) if value is not None else None

    @model_validator(mode="after")
    def _exactly_one(self) -> ReauthRequest:
        if (self.password is None) == (self.credential is None):
            msg = "exactly one of password and credential is required"
            raise ValueError(msg)
        return self


class ReauthResponse(StrictModel):
    # До какого момента можно добавлять и удалять ключи без нового подтверждения.
    reauth_until: datetime


class AdminUserPasskey(StrictModel):
    id: str
    name: str
    created_at: datetime
    last_used_at: datetime | None
    synced: bool
    domain: str


class AdminUserPasskeyList(StrictModel):
    items: list[AdminUserPasskey]


class AdminPasskeysReset(StrictModel):
    removed: int
