"""Вход по passkey (WebAuthn): ключи пользователя, проверяющая сторона (RP) и порт проверки ответов браузера.

Закрытый ключ не покидает устройство: сервер хранит открытый ключ, счётчик подписей и метаданные. Каждая церемония
идёт по одноразовому вызову (challenge), который лежит в `auth_tokens` хешем и гасится при первом же ответе.
Решения и их обоснования: docs/design/passkeys.md.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol
from urllib.parse import urlsplit

# Больше ключей человеку не нужно, а список без предела раздувал бы allowCredentials и экран профиля.
PASSKEY_LIMIT = 20
PASSKEY_NAME_MAX = 64
# Сколько живёт вызов церемонии: форма входа с автозаполнением держит его, пока человек на странице.
CHALLENGE_TTL = timedelta(minutes=10)
# Окно, в котором вход или повторное подтверждение считаются свежими для добавления и удаления ключей.
REAUTH_WINDOW = timedelta(minutes=10)
# Сколько ждёт браузер выбора ключа; подсказка, браузер может её сократить.
CEREMONY_TIMEOUT_MS = 300_000
# Предел ответа браузера: ключи и подписи укладываются в единицы килобайт.
CREDENTIAL_JSON_MAX = 64 * 1024

type CredentialJson = Mapping[str, object]


@dataclass(frozen=True)
class Passkey:
    """Зарегистрированный ключ. `credential_id` в base64url, `public_key` в COSE как прислал аутентификатор."""

    id: str
    user_id: str
    credential_id: str
    public_key: bytes
    sign_count: int
    # Домен (RP ID), к которому ключ привязан при создании: при смене адреса сервера ключ перестаёт подходить.
    rp_id: str
    name: str
    created_at: datetime
    last_used_at: datetime | None = None
    transports: tuple[str, ...] = ()
    aaguid: str = ""
    # Ключ может синхронизироваться между устройствами (backup eligible) и уже скопирован (backed up).
    backup_eligible: bool = False
    backed_up: bool = False


@dataclass(frozen=True)
class RelyingParty:
    """Проверяющая сторона: домен ключей и origin, с которого браузер вправе их использовать."""

    id: str
    name: str
    origin: str


class RelyingPartyIssue(StrEnum):
    """Почему на этом адресе passkey недоступен; админка показывает причину."""

    no_address = "no_address"
    insecure_origin = "insecure_origin"
    ip_address = "ip_address"
    rp_id_mismatch = "rp_id_mismatch"


@dataclass(frozen=True)
class RelyingPartyResolution:
    party: RelyingParty | None
    issue: RelyingPartyIssue | None = None


def _is_localhost(host: str) -> bool:
    return host == "localhost" or host.endswith(".localhost")


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return True


def resolve_relying_party(origin: str | None, *, rp_id: str | None = None, name: str) -> RelyingPartyResolution:
    """RP из origin Студии (`https://studio.example.org`) и, если задан, домена ключей (родительский домен).

    Браузер даёт WebAuthn только в защищённом контексте: HTTPS или localhost. Домен ключей не может быть IP-адресом
    и обязан совпадать с хостом origin или быть его родительским доменом.
    """
    if not origin:
        return RelyingPartyResolution(None, RelyingPartyIssue.no_address)
    parts = urlsplit(origin.strip())
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or not host:
        return RelyingPartyResolution(None, RelyingPartyIssue.no_address)
    if _is_ip(host):
        return RelyingPartyResolution(None, RelyingPartyIssue.ip_address)
    if parts.scheme == "http" and not _is_localhost(host):
        return RelyingPartyResolution(None, RelyingPartyIssue.insecure_origin)
    domain = (rp_id or host).strip().lower().rstrip(".")
    if domain != host and not host.endswith(f".{domain}"):
        return RelyingPartyResolution(None, RelyingPartyIssue.rp_id_mismatch)
    clean_origin = f"{parts.scheme}://{parts.netloc}".lower()
    return RelyingPartyResolution(RelyingParty(id=domain, name=name, origin=clean_origin))


def user_handle_of(user_id: str) -> bytes:
    """Идентификатор пользователя для аутентификатора: id аккаунта (не почта), не длиннее 64 байт по спецификации."""
    return user_id.encode("utf-8")[:64]


def clean_passkey_name(name: str | None, fallback: str) -> str:
    cleaned = " ".join((name or "").split())[:PASSKEY_NAME_MAX]
    return cleaned or fallback


@dataclass(frozen=True)
class PasskeyDescriptor:
    """Ключ в allowCredentials и excludeCredentials: id и подсказки транспорта."""

    credential_id: str
    transports: tuple[str, ...] = ()


@dataclass(frozen=True)
class AssertionHeader:
    """Что видно в ответе браузера до проверки подписи: какой ключ, чей и на какой вызов."""

    credential_id: str
    challenge: str
    user_handle: bytes | None = None


@dataclass(frozen=True)
class NewCredential:
    """Проверенный ответ регистрации."""

    credential_id: str
    public_key: bytes
    sign_count: int
    aaguid: str
    transports: tuple[str, ...]
    backup_eligible: bool
    backed_up: bool


@dataclass(frozen=True)
class VerifiedAssertion:
    new_sign_count: int
    backed_up: bool


class PasskeyFailure(StrEnum):
    """Причина отказа в журнал; человеку уходит один общий код `passkey_invalid`."""

    malformed = "malformed"
    challenge = "challenge"
    unknown_credential = "unknown_credential"
    user_handle = "user_handle"
    signature = "signature"
    sign_count = "sign_count"
    user_verification = "user_verification"
    duplicate = "duplicate"


class PasskeyVerificationError(Exception):
    def __init__(self, reason: PasskeyFailure, detail: str = "") -> None:
        super().__init__(detail or reason.value)
        self.reason = reason


class IWebAuthn(Protocol):
    """Форматы WebAuthn: параметры церемоний и проверка ответов браузера (attestation none, UV обязателен)."""

    def registration_options(
        self,
        party: RelyingParty,
        *,
        challenge: bytes,
        user_handle: bytes,
        user_name: str,
        display_name: str,
        exclude: Sequence[PasskeyDescriptor],
    ) -> dict[str, object]: ...

    def authentication_options(
        self, party: RelyingParty, *, challenge: bytes, allow: Sequence[PasskeyDescriptor]
    ) -> dict[str, object]: ...

    def registration_challenge(self, credential: CredentialJson) -> str:
        """Вызов из clientDataJSON ответа регистрации (base64url); битый ответ даёт `PasskeyVerificationError`."""
        ...

    def assertion_header(self, credential: CredentialJson) -> AssertionHeader: ...

    def verify_registration(
        self, party: RelyingParty, credential: CredentialJson, *, challenge: str
    ) -> NewCredential: ...

    def verify_authentication(
        self, party: RelyingParty, credential: CredentialJson, *, challenge: str, passkey: Passkey
    ) -> VerifiedAssertion: ...


class IPasskeyRepository(Protocol):
    async def add(self, passkey: Passkey) -> None:
        """Занятый `credential_id` даёт `PasskeyVerificationError(duplicate)`."""
        ...

    async def get_by_credential_id(self, credential_id: str) -> Passkey | None: ...
    async def list_for_user(self, user_id: str) -> list[Passkey]:
        """Ключи человека, старые первыми."""
        ...

    async def count_for_user(self, user_id: str) -> int: ...
    async def rename(self, user_id: str, passkey_id: str, name: str) -> Passkey | None: ...
    async def delete(self, user_id: str, passkey_id: str) -> bool: ...
    async def delete_for_user(self, user_id: str) -> int: ...
    async def record_use(self, passkey_id: str, *, sign_count: int, backed_up: bool, now: datetime) -> None: ...
    async def count_by_rp_id(self) -> dict[str, int]:
        """Сколько ключей установки привязано к каждому домену: для предупреждения о смене адреса."""
        ...
